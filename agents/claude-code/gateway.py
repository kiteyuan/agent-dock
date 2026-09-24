#!/usr/bin/env python3
"""
HTTP gateway: AgentDock Agent Protocol ↔ Claude Code CLI (`claude -p` stream-json).

  python agents/claude-code/gateway.py
  → http://127.0.0.1:9003/v1/agent/run

Requires: `claude` on PATH (https://code.claude.com) and auth configured.

Env:
  CLAUDE_GATEWAY_PORT=9003
  CLAUDE_CWD=...                      # fallback cwd (default: <repo>/data/vault)
  CLAUDE_BIN=claude
  CLAUDE_MODEL=...
  CLAUDE_PERMISSION_MODE=acceptEdits  # or bypassPermissions / default / plan
  CLAUDE_ALLOWED_TOOLS=...            # optional comma list
  CLAUDE_APPEND_SYSTEM_PROMPT=... / CLAUDE_SYSTEM_PROMPT=...
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AGENTS = _HERE.parent
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from mcp_launch import claude_args  # noqa: E402
from common import (  # noqa: E402
    PROTOCOL,
    ProcessTable,
    assert_loopback_or_token,
    device_id_of,
    event,
    fallback_work_dir,
    kill_process,
    launch_cli,
    make_write_event,
    merge_runtime_instructions,
    read_json_request,
    repo_root_from,
    require_gateway_bearer,
    resolve_request_cwd,
    send_json,
    voice_prompt,
    which,
    write_ndjson_headers,
)

HOST = os.environ.get("CLAUDE_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLAUDE_GATEWAY_PORT", "9003"))
HERE = _HERE
REPO_ROOT = repo_root_from(HERE)
FALLBACK_WORK_DIR = fallback_work_dir(
    REPO_ROOT, env_cwd="CLAUDE_CWD", env_workdir="CLAUDE_WORKDIR"
)
BIN = os.environ.get("CLAUDE_BIN") or which("claude") or "claude"
MODEL = os.environ.get("CLAUDE_MODEL")
PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "acceptEdits")
_DEFAULT_ALLOWED = "Bash,Read,Edit,Write"
_allowed_raw = os.environ.get("CLAUDE_ALLOWED_TOOLS", _DEFAULT_ALLOWED)
ALLOWED_TOOLS = [t.strip() for t in _allowed_raw.split(",") if t.strip()]

_DEFAULT_VOICE = (
    "你是通过麦克风/扬声器使用的快捷终端助手，回复会被 TTS 朗读。"
    "尽量简短口语化；纯文本不要 Markdown；先说结论。"
)

_PROCESSES = ProcessTable()


def _system_prompt() -> str:
    return voice_prompt(
        HERE,
        env_append="CLAUDE_APPEND_SYSTEM_PROMPT",
        env_replace="CLAUDE_SYSTEM_PROMPT",
        default=_DEFAULT_VOICE,
    )


def _build_cmd(prompt: str, *, instructions: str = "") -> list[str]:
    cmd = [
        BIN,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode",
        PERMISSION_MODE,
    ]
    if MODEL:
        cmd += ["--model", MODEL]
    if ALLOWED_TOOLS:
        cmd += ["--allowedTools", ",".join(ALLOWED_TOOLS)]
    sp = merge_runtime_instructions(_system_prompt(), {"instructions": instructions}).strip()
    if sp:
        cmd += ["--append-system-prompt", sp]
    cmd += claude_args()
    return cmd


def _delta_text(raw: dict) -> str:
    ev = raw.get("event") if isinstance(raw.get("event"), dict) else {}
    delta = ev.get("delta") if isinstance(ev.get("delta"), dict) else {}
    if delta.get("type") and delta.get("type") != "text_delta":
        return ""
    if isinstance(delta.get("text"), str):
        return delta["text"]
    return ""


def _result_text(raw: dict) -> str:
    for key in ("result", "content", "text"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def run_claude_turn(
    session_id: str,
    text: str,
    write_event,
    *,
    cwd: Path,
    instructions: str = "",
) -> None:
    if not cwd.is_dir():
        write_event(event("agent.error", session_id, content=f"workspace is not a directory: {cwd}"))
        return
    cmd = _build_cmd(text, instructions=instructions)
    write_event(
        event(
            "agent.thinking",
            session_id,
            content=f"claude cwd={cwd}: {' '.join(cmd[:6])} …",
        )
    )
    try:
        proc, error_log = launch_cli(cmd, cwd=str(cwd))
    except FileNotFoundError as exc:
        write_event(event("agent.error", session_id, content=f"cannot start claude: {exc}"))
        return

    _PROCESSES.register(session_id, proc)
    assistant_parts: list[str] = []
    final_text = ""
    saw_done = False
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = str(raw.get("type") or "")
            if et == "system":
                write_event(event("agent.start", session_id))
            elif et == "assistant":
                content = (
                    raw.get("message", {}).get("content")
                    if isinstance(raw.get("message"), dict)
                    else raw.get("content")
                )
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            write_event(
                                event(
                                    "agent.tool_call",
                                    session_id,
                                    tool=str(block.get("name") or "tool"),
                                    args=block.get("input")
                                    if isinstance(block.get("input"), dict)
                                    else {},
                                )
                            )
                        elif block.get("type") == "text" and block.get("text"):
                            assistant_parts.append(str(block["text"]))
            elif et == "stream_event":
                chunk = _delta_text(raw)
                if chunk:
                    assistant_parts.append(chunk)
                    write_event(event("agent.thinking", session_id, content=chunk[:120]))
            elif et in ("tool_use", "tool_call"):
                write_event(
                    event(
                        "agent.tool_call",
                        session_id,
                        tool=str(raw.get("name") or raw.get("tool") or "tool"),
                        args=raw.get("input") if isinstance(raw.get("input"), dict) else {},
                    )
                )
            elif et in ("tool_result",):
                write_event(
                    event(
                        "agent.tool_result",
                        session_id,
                        tool=str(raw.get("name") or "tool"),
                        status="error" if raw.get("is_error") else "success",
                        content=str(raw.get("content") or "")[:500],
                    )
                )
            elif et == "result":
                final_text = _result_text(raw) or "".join(assistant_parts).strip()
                if final_text:
                    write_event(
                        event("agent.message", session_id, content=final_text, speak=True)
                    )
                if raw.get("is_error"):
                    write_event(
                        event(
                            "agent.error",
                            session_id,
                            content=str(raw.get("result") or raw.get("error") or "claude error")[
                                :800
                            ],
                        )
                    )
                else:
                    write_event(event("agent.done", session_id))
                saw_done = True

        code = proc.wait(timeout=30)
        cancelled = _PROCESSES.release(session_id, proc)
        if cancelled:
            write_event(event("agent.cancel", session_id))
            return
        error_log.seek(0)
        stderr = error_log.read()[-2000:].strip()
        if not saw_done:
            text_out = final_text or "".join(assistant_parts).strip()
            if code != 0 and not text_out:
                write_event(
                    event(
                        "agent.error",
                        session_id,
                        content=(stderr or f"claude exited {code}")[:800],
                    )
                )
            else:
                if text_out:
                    write_event(
                        event("agent.message", session_id, content=text_out, speak=True)
                    )
                write_event(event("agent.done", session_id))
    except BrokenPipeError:
        kill_process(proc)
        _PROCESSES.release(session_id, proc)
        raise
    finally:
        if proc.poll() is None:
            kill_process(proc)
        _PROCESSES.release(session_id, proc)
        error_log.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[claude-gateway] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if require_gateway_bearer(self):
            return
        if self.path.rstrip("/") == "/v1/agent":
            send_json(
                self,
                {
                    "protocol": PROTOCOL,
                    "id": "claude",
                    "name": "Claude Code",
                    "capabilities": ["coding", "bash", "filesystem"],
                    "description": "Gateway over `claude -p --output-format stream-json`",
                },
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if require_gateway_bearer(self):
            return
        req = read_json_request(self)
        if req is None:
            return
        path = self.path.rstrip("/")
        if path == "/v1/agent/cancel":
            sid = str(req.get("session_id") or "")
            send_json(self, {"ok": _PROCESSES.cancel(sid)})
            return
        if path != "/v1/agent/run":
            self.send_error(404)
            return

        sid = str(req.get("session_id") or uuid.uuid4().hex[:12])
        text = str(req.get("text") or "")
        cwd = resolve_request_cwd(req, FALLBACK_WORK_DIR)
        _ = device_id_of(req)

        write_ndjson_headers(self)
        write_event = make_write_event(self)
        try:
            run_claude_turn(
                sid,
                text,
                write_event,
                cwd=cwd,
                instructions=str(req.get("instructions") or ""),
            )
        except BrokenPipeError:
            _PROCESSES.cancel(sid)
        except Exception as exc:  # noqa: BLE001
            write_event(event("agent.error", sid, content=str(exc)))


def main() -> None:
    if which(BIN) is None and not Path(BIN).exists():
        print(
            f"claude not found ({BIN!r}); install Claude Code CLI and ensure it is on PATH",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not FALLBACK_WORK_DIR.is_dir():
        FALLBACK_WORK_DIR.mkdir(parents=True, exist_ok=True)
    assert_loopback_or_token(HOST)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Claude Code gateway on http://{HOST}:{PORT}", flush=True)
    print(f"  fallback cwd={FALLBACK_WORK_DIR} (request.workspace overrides)", flush=True)
    print(f"  bin={BIN} permission-mode={PERMISSION_MODE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
