"""Shared helpers for local Agent Protocol HTTP gateways."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .process import ProcessTable, kill_process, launch_cli

PROTOCOL = "agentdock.agent/1.0"

__all__ = [
    "PROTOCOL",
    "ProcessTable",
    "device_id_of",
    "event",
    "fallback_work_dir",
    "kill_process",
    "launch_cli",
    "load_prompt_text",
    "make_write_event",
    "read_json_request",
    "repo_root_from",
    "resolve_request_cwd",
    "send_json",
    "voice_prompt",
    "which",
    "write_ndjson_headers",
]


def repo_root_from(here: Path) -> Path:
    # agents/<name>/gateway.py → repo root
    return here.resolve().parent.parent


def default_workspace(repo: Path) -> Path:
    return (repo / "workspace").resolve()


def fallback_work_dir(repo: Path, *, env_cwd: str = "AGENT_CWD", env_workdir: str = "AGENT_WORKDIR") -> Path:
    raw = os.environ.get(env_cwd) or os.environ.get(env_workdir)
    if raw:
        return Path(raw).expanduser().resolve()
    return default_workspace(repo)


def resolve_request_cwd(req: dict[str, Any], fallback: Path) -> Path:
    raw = req.get("workspace")
    if raw:
        path = Path(str(raw)).expanduser().resolve()
        if path.is_dir():
            return path
    return fallback


def device_id_of(req: dict[str, Any]) -> str | None:
    device = req.get("device") if isinstance(req.get("device"), dict) else {}
    did = str(device.get("id") or device.get("device_id") or "").strip()
    return did or None


def load_prompt_text(raw: str | None, *, fallback: str) -> str:
    if not raw:
        return fallback
    raw = raw.strip()
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or fallback
    return raw


def voice_prompt(here: Path, *, env_append: str, env_replace: str, default: str) -> str:
    replace = os.environ.get(env_replace)
    if replace is not None and replace.strip() != "":
        return load_prompt_text(replace, fallback=default)

    default_file = here / "voice_prompt.txt"
    file_default = (
        default_file.read_text(encoding="utf-8").strip() if default_file.is_file() else default
    )
    append = os.environ.get(env_append)
    if append is not None:
        return load_prompt_text(append, fallback=file_default)
    return file_default


def event(etype: str, session_id: str, **payload: Any) -> dict[str, Any]:
    body = {"session_id": session_id, **payload}
    return {
        "type": etype,
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "payload": body,
    }


def which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd) or shutil.which(f"{cmd}.exe")


WriteEvent = Callable[[dict[str, Any]], None]


def read_json_request(handler: Any) -> dict[str, Any] | None:
    length = int(handler.headers.get("Content-Length", "0"))
    raw_in = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw_in.decode("utf-8"))
    except json.JSONDecodeError:
        handler.send_error(400, "invalid json")
        return None


def write_ndjson_headers(handler: Any) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.send_header("X-AgentDock-Protocol", PROTOCOL)
    handler.send_header("Connection", "close")
    handler.end_headers()


def make_write_event(handler: Any) -> WriteEvent:
    def write_event(obj: dict[str, Any]) -> None:
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        handler.wfile.write(line)
        handler.wfile.flush()

    return write_event


def send_json(handler: Any, body: dict[str, Any], *, status: int = 200) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)
