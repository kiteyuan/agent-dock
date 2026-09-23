#!/usr/bin/env python3
"""
HTTP gateway: AgentDock Agent Protocol ↔ Pi Coding Agent (--mode json).

  python agents/pi-coding/gateway.py
  → http://127.0.0.1:9000/v1/agent/run

Requires: npm deps in agents/pi-coding (npx pi).

Env:
  PI_GATEWAY_PORT=9001
  PI_CWD=E:\\path\\to\\project   # fallback cwd when request has no workspace (default: <repo>/data/vault)
  PI_NO_TOOLS=1
  PI_NO_SESSION=1               # ephemeral turns (no Pi session files)
  PI_SESSION_DIR=...            # Pi session files (default: <repo>/data/sessions/pi-coding)
  PI_SESSION_KEY=device         # device (default) | session — what keys Pi --session-id
  PI_APPEND_SYSTEM_PROMPT=...   # append voice style prompt (default: agents/pi-coding/voice_prompt.txt)
  PI_SYSTEM_PROMPT=...          # replace system prompt entirely (path or literal)

"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROTOCOL = "agentdock.agent/1.0"
HOST = os.environ.get("PI_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("PI_GATEWAY_PORT", "9000"))
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
DEFAULT_WORKSPACE = REPO_ROOT / "data" / "vault"
# Fallback cwd when Runtime does not send workspace (default: <repo>/data/vault). Override: PI_CWD=
FALLBACK_WORK_DIR = Path(
    os.environ.get("PI_CWD") or os.environ.get("PI_WORKDIR") or DEFAULT_WORKSPACE
).expanduser().resolve()
_AGENTS = HERE.parent
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))
from mcp_launch import sync_pi_mcp  # noqa: E402

PROVIDER = os.environ.get("PI_PROVIDER")  # optional override
MODEL = os.environ.get("PI_MODEL")
NO_TOOLS = os.environ.get("PI_NO_TOOLS", "0") == "1"
# Default: reuse Pi session files keyed by device. Set PI_NO_SESSION=1 for one-shot.
NO_SESSION = os.environ.get("PI_NO_SESSION", "0") == "1"
_DEFAULT_SESSIONS = REPO_ROOT / "data" / "sessions" / "pi-coding"
SESSION_DIR = Path(
    os.environ.get("PI_SESSION_DIR") or _DEFAULT_SESSIONS
).expanduser().resolve()
# Key Pi memory by stable device id (survives WS reconnect). Use "session" for WS-scoped.
SESSION_KEY = (os.environ.get("PI_SESSION_KEY") or "device").strip().lower()
# DeepSeek V4 Flash writes its plan into the reply when thinking is disabled.
# Keep it on so that plan stays in the thinking channel. Not a user setting.
THINKING = "high"

# Voice / short-reply system prompt (appended to Pi's default). Override with
# PI_APPEND_SYSTEM_PROMPT=path|text  or PI_SYSTEM_PROMPT=... to replace entirely.
_DEFAULT_VOICE_PROMPT = (
    "你是通过麦克风/扬声器使用的快捷终端助手，回复会被 TTS 直接读给用户听。"
    "尽量简短口语化；纯文本不要 Markdown；先说结论。"
)


def _load_prompt_text(raw: str | None, *, fallback: str) -> str:
    if not raw:
        return fallback
    raw = raw.strip()
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or fallback
    return raw


def _system_prompt_args(*, extra: str = "") -> list[str]:
    """CLI flags for system prompt injection."""
    replace = os.environ.get("PI_SYSTEM_PROMPT")
    if replace is not None and replace.strip() != "":
        text = _load_prompt_text(replace, fallback=_DEFAULT_VOICE_PROMPT)
    else:
        default_file = HERE / "voice_prompt.txt"
        default = (
            default_file.read_text(encoding="utf-8").strip()
            if default_file.is_file()
            else _DEFAULT_VOICE_PROMPT
        )
        append = os.environ.get("PI_APPEND_SYSTEM_PROMPT")
        text = _load_prompt_text(append, fallback=default) if append is not None else default
    if extra.strip():
        text = f"{(text or '').rstrip()}\n\n{extra.strip()}" if text else extra.strip()
    if not text:
        return []
    if replace is not None and replace.strip() != "":
        return ["--system-prompt", text]
    return ["--append-system-prompt", text]


def _resolve_pi_cmd() -> list[str]:
    """Return argv prefix that launches `pi` on this machine."""
    override = os.environ.get("PI_BIN")
    if override:
        # Allow: PI_BIN="node path/to/cli.js" style via shlex? keep simple single path or node+script
        return [override]

    cli_candidates = [
        HERE
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "bundle"
        / "cli.js",
        HERE
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "cli.js",
    ]
    import shutil

    node = shutil.which("node") or shutil.which("node.exe")
    for cli in cli_candidates:
        if cli.is_file() and node:
            return [node, str(cli)]

    for name in ("pi.cmd", "pi.exe", "pi"):
        local = HERE / "node_modules" / ".bin" / name
        if local.is_file():
            # .cmd needs shell on Windows; prefer node+cli.js above
            return [str(local)]

    for name in ("pi.cmd", "pi", "npx.cmd", "npx"):
        found = shutil.which(name)
        if not found:
            continue
        if name.startswith("npx"):
            return [found, "--yes", "pi"]
        return [found]

    raise FileNotFoundError(
        "pi not found; run: cd agents/pi-coding && npm install "
        "(or set PI_BIN / ensure node is on PATH)"
    )


def _event(etype: str, session_id: str, **payload: object) -> dict:
    return {
        "type": etype,
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "payload": {"session_id": session_id, **payload},
    }


def _text_from_message(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def spoken_reply(message: dict, *, streamed_text: str = "") -> str:
    """Return the reply text to speak. Thinking is never read aloud.

    A thinking-only message is not a reply. Tool turns emit one before the
    real answer; speaking a placeholder there would block the later text.
    """
    return _text_from_message(message).strip() or streamed_text.strip()


def _safe_session_id(session_id: str) -> str:
    """Filesystem-safe id for Pi --session-id (create-if-missing)."""
    cleaned = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return cleaned[:64] or uuid.uuid4().hex[:12]


def _pi_memory_key(*, session_id: str, device_id: str | None) -> str:
    """Choose Pi session file key. Prefer device so reconnect keeps memory."""
    if NO_SESSION:
        return session_id
    mode = SESSION_KEY
    did = (device_id or "").strip()
    if mode == "session" or not did:
        return _safe_session_id(session_id)
    # Prefix avoids colliding with short AgentDock WS session ids.
    return _safe_session_id(f"dev-{did}")


def _resolve_request_cwd(req: dict) -> Path:
    """Prefer Runtime-provided workspace; else PI_CWD / <repo>/workspace."""
    raw = req.get("workspace")
    if raw:
        path = Path(str(raw)).expanduser().resolve()
        if path.is_dir():
            return path
    return FALLBACK_WORK_DIR


def _mcp_extension_args(root: Path | None = None) -> list[str]:
    """Load the adapter shipped by ``npm install`` in this directory."""
    entry = (root or HERE) / "node_modules" / "pi-mcp-adapter" / "index.ts"
    if not entry.is_file():
        return []
    return ["-e", str(entry)]


def _build_pi_cmd(prompt: str, *, pi_key: str, instructions: str = "") -> list[str]:
    cmd = [*_resolve_pi_cmd(), "--mode", "json", "--print"]
    if NO_SESSION:
        cmd.append("--no-session")
    else:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        cmd += [
            "--session-dir",
            str(SESSION_DIR),
            "--session-id",
            pi_key,
        ]
    if PROVIDER:
        cmd += ["--provider", PROVIDER]
    if MODEL:
        cmd += ["--model", MODEL]
    if NO_TOOLS:
        cmd += ["--no-tools"]
    cmd += _system_prompt_args(extra=instructions)
    if THINKING:
        cmd += ["--thinking", THINKING]
    cmd += _mcp_extension_args()
    cmd.append(prompt)
    return cmd



class ClientGone(Exception):
    """Runtime closed the NDJSON stream; stop writing and kill Pi."""


_CLIENT_GONE_ERRORS = (
    BrokenPipeError,
    ConnectionAbortedError,
    ConnectionResetError,
)


def _kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _iter_stdout_lines(proc: subprocess.Popen[str]):
    """Yield stdout lines, and return once Pi has exited.

    A tool can inherit Pi's stdout and exit without closing it. A plain
    ``for line in proc.stdout`` then blocks forever, so the phone never
    receives ``agent.done``.
    """
    lines: queue.Queue[str | None] = queue.Queue()

    def _read() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=_read, name="pi-stdout", daemon=True).start()
    while True:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            if proc.poll() is None:
                continue
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                if proc.stdout is not None:
                    try:
                        proc.stdout.close()
                    except Exception:  # noqa: BLE001
                        pass
                return
        if line is None:
            return
        yield line


def run_pi_turn(
    session_id: str,
    text: str,
    write_event,
    *,
    device_id: str | None = None,
    cwd: Path | None = None,
    instructions: str = "",
) -> None:
    work_dir = (cwd or FALLBACK_WORK_DIR).resolve()
    if not work_dir.is_dir():
        write_event(
            _event(
                "agent.error",
                session_id,
                content=f"workspace is not a directory: {work_dir}",
            )
        )
        return
    pi_key = _pi_memory_key(session_id=session_id, device_id=device_id)
    sync_pi_mcp(work_dir)
    cmd = _build_pi_cmd(text, pi_key=pi_key, instructions=instructions)
    sid_note = "ephemeral" if NO_SESSION else pi_key
    write_event(
        _event(
            "agent.thinking",
            session_id,
            content=f"pi[{sid_note}] cwd={work_dir}: {' '.join(cmd[:6])} …",
        )
    )
    try:
        # stderr to DEVNULL avoids stdout/stderr pipe deadlock when Pi logs heavily.
        proc = subprocess.Popen(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        write_event(_event("agent.error", session_id, content=f"cannot start pi: {exc}"))
        return

    assistant_text = ""
    streamed_text = ""
    saw_done = False
    assert proc.stdout is not None

    def emit_reply(text: str) -> None:
        nonlocal assistant_text
        cleaned = text.strip()
        if not cleaned:
            return
        assistant_text = cleaned
        write_event(
            _event(
                "agent.message",
                session_id,
                content=cleaned,
                speak=True,
            )
        )

    try:
        for line in _iter_stdout_lines(proc):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = raw.get("type")
            if et == "agent_start":
                write_event(_event("agent.start", session_id))
            elif et == "message_update":
                ame = raw.get("assistantMessageEvent") or {}
                if ame.get("type") == "text_delta" and ame.get("delta"):
                    streamed_text += str(ame.get("delta"))
                elif ame.get("type") == "thinking_delta" and ame.get("delta"):
                    write_event(
                        _event(
                            "agent.thinking",
                            session_id,
                            content=str(ame.get("delta"))[:200],
                        )
                    )
            elif et == "tool_execution_start":
                write_event(
                    _event(
                        "agent.tool_call",
                        session_id,
                        tool=str(raw.get("toolName") or raw.get("tool") or "tool"),
                        args=raw.get("args") if isinstance(raw.get("args"), dict) else {},
                    )
                )
            elif et == "tool_execution_end":
                write_event(
                    _event(
                        "agent.tool_result",
                        session_id,
                        tool=str(raw.get("toolName") or raw.get("tool") or "tool"),
                        status="error" if raw.get("isError") else "success",
                        content=str(raw.get("result") or raw.get("error") or "")[:500],
                    )
                )
            elif et == "message_end":
                msg = raw.get("message") or {}
                if msg.get("role") == "assistant":
                    err = msg.get("errorMessage")
                    if not err and msg.get("stopReason") == "error":
                        err = msg.get("error") or "model error"
                    if err:
                        write_event(
                            _event("agent.error", session_id, content=str(err)[:800])
                        )
                        saw_done = True
                        break
                    emit_reply(spoken_reply(msg, streamed_text=streamed_text))
                    streamed_text = ""
            elif et == "agent_end":
                if not assistant_text:
                    for m in reversed(raw.get("messages") or []):
                        if isinstance(m, dict) and m.get("role") == "assistant":
                            emit_reply(spoken_reply(m, streamed_text=streamed_text))
                            if assistant_text:
                                break
                write_event(_event("agent.done", session_id))
                saw_done = True
                break
            elif et == "error":
                write_event(
                    _event(
                        "agent.error",
                        session_id,
                        content=str(raw.get("message") or raw.get("error") or raw),
                    )
                )
                saw_done = True
                break

        if not saw_done:
            code = proc.wait(timeout=10)
            if code != 0:
                write_event(
                    _event("agent.error", session_id, content=f"pi exited {code}")
                )
            else:
                emit_reply(assistant_text or streamed_text)
                write_event(_event("agent.done", session_id))
    except ClientGone:
        _kill_proc(proc)
        raise
    finally:
        _kill_proc(proc)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[pi-gateway] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/agent":
            body = {
                "protocol": PROTOCOL,
                "id": "pi",
                "name": "Pi Coding Agent",
                "capabilities": ["coding", "bash", "filesystem"],
                "description": (
                    "Gateway over @earendil-works/pi-coding-agent "
                    "(--mode json, Pi memory by device_id)"
                ),
            }
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw_in = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw_in.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return

        path = self.path.rstrip("/")
        if path == "/v1/agent/cancel":
            out = json.dumps(
                {
                    "ok": True,
                    "note": "print-mode cancel is best-effort; Pi session file is kept for reuse",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return

        if path != "/v1/agent/run":
            self.send_error(404)
            return

        sid = str(req.get("session_id") or uuid.uuid4().hex[:12])
        text = str(req.get("text") or "")
        device = req.get("device") if isinstance(req.get("device"), dict) else {}
        device_id = str(device.get("id") or device.get("device_id") or "").strip() or None
        cwd = _resolve_request_cwd(req)

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("X-AgentDock-Protocol", PROTOCOL)
        self.send_header("Connection", "close")
        self.end_headers()

        def write_event(obj: dict) -> None:
            try:
                line = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
                self.wfile.write(line)
                self.wfile.flush()
            except _CLIENT_GONE_ERRORS as exc:
                raise ClientGone(str(exc)) from exc

        try:
            run_pi_turn(
                sid,
                text,
                write_event,
                device_id=device_id,
                cwd=cwd,
                instructions=str(req.get("instructions") or ""),
            )
        except ClientGone:
            print(f"[pi-gateway] client gone mid-turn session={sid}", flush=True)
        except Exception as exc:  # noqa: BLE001
            try:
                write_event(_event("agent.error", sid, content=str(exc)))
            except ClientGone:
                print(
                    f"[pi-gateway] client gone while sending error session={sid}",
                    flush=True,
                )



def main() -> None:
    bin_dir = HERE / "node_modules" / ".bin"
    if bin_dir.is_dir():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

    try:
        prefix = _resolve_pi_cmd()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    # Line-buffer logs when piped
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    if not FALLBACK_WORK_DIR.is_dir():
        if FALLBACK_WORK_DIR == DEFAULT_WORKSPACE.resolve():
            FALLBACK_WORK_DIR.mkdir(parents=True, exist_ok=True)
        else:
            print(f"PI_CWD is not a directory: {FALLBACK_WORK_DIR}", file=sys.stderr)
            raise SystemExit(1)
    print(f"Pi Agent gateway on http://{HOST}:{PORT}", flush=True)
    print(f"  fallback cwd={FALLBACK_WORK_DIR} (request.workspace overrides)", flush=True)
    print(f"  pi cmd: {prefix}", flush=True)
    if NO_SESSION:
        print("  sessions: ephemeral (--no-session)", flush=True)
    else:
        print(
            f"  sessions: key={SESSION_KEY} under {SESSION_DIR}",
            flush=True,
        )
    sp = _system_prompt_args()
    if sp:
        kind = "replace" if sp[0] == "--system-prompt" else "append"
        preview = (sp[1][:60] + "…") if len(sp[1]) > 60 else sp[1]
        print(f"  system_prompt ({kind}): {preview}", flush=True)
    if PROVIDER:
        print(f"  provider={PROVIDER} model={MODEL or '(default)'}", flush=True)
    print(f"  thinking={THINKING}", flush=True)
    if NO_TOOLS:
        print("  flags: --no-tools", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
