"""Generic AgentDock HTTP gateway for supported CLI coding agents."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common import (
    PROTOCOL,
    ProcessTable,
    event,
    fallback_work_dir,
    kill_process,
    launch_cli,
    make_write_event,
    read_json_request,
    send_json,
    write_ndjson_headers,
)
from agents.drivers import CLIDriver, create_driver

_PROCESSES = ProcessTable()


def _redact_secrets(value: str) -> str:
    result = value
    suffixes = ("_API_KEY", "_AUTH_TOKEN", "_ACCESS_TOKEN", "_PERSONAL_ACCESS_TOKEN")
    for key, secret in os.environ.items():
        if key.upper().endswith(suffixes) and len(secret) >= 4:
            result = result.replace(secret, "[redacted]")
    return result


def _safe_workspace(request: dict[str, Any], fallback: Path) -> Path:
    raw = request.get("workspace")
    if not raw:
        return fallback
    candidate = Path(str(raw)).expanduser().resolve()
    try:
        candidate.relative_to(fallback)
    except ValueError:
        return fallback
    return candidate if candidate.is_dir() else fallback


def _run_turn(
    driver: CLIDriver,
    session_id: str,
    text: str,
    *,
    cwd: Path,
    write_event: Any,
) -> None:
    command = driver.command(text)
    write_event(event("agent.start", session_id))
    process, error_log = launch_cli(command, cwd=str(cwd))
    _PROCESSES.register(session_id, process)
    wrote = False
    buffered = ""
    try:
        assert process.stdout is not None
        for line in process.stdout:
            content = driver.decode_line(line)
            if not content:
                continue
            if driver.spec.buffer_output:
                buffered = content
                continue
            wrote = True
            write_event(
                event("agent.message", session_id, content=content, speak=True)
            )
        code = process.wait()
        error_log.seek(0)
        error_detail = error_log.read()[-2000:].strip()
        cancelled = _PROCESSES.release(session_id, process)
        if cancelled:
            write_event(event("agent.cancel", session_id))
            return
        if code:
            write_event(
                event(
                    "agent.error",
                    session_id,
                    content=_redact_secrets(error_detail)
                    or f"{driver.spec.name} exited with code {code}",
                )
            )
            return
        if buffered:
            wrote = True
            write_event(
                event(
                    "agent.message",
                    session_id,
                    content=buffered,
                    speak=True,
                )
            )
        if not wrote:
            write_event(
                event(
                    "agent.message",
                    session_id,
                    content=f"{driver.spec.name} completed without text output",
                    speak=True,
                )
            )
        write_event(event("agent.done", session_id))
    finally:
        if process.poll() is None:
            kill_process(process)
        _PROCESSES.release(session_id, process)
        error_log.close()


def handler_for(driver: CLIDriver, workspace: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path.rstrip("/") != "/v1/agent":
                self.send_error(404)
                return
            send_json(
                self,
                {
                    "protocol": PROTOCOL,
                    "id": driver.spec.id,
                    "name": driver.spec.name,
                    "capabilities": ["coding", "bash", "filesystem"],
                    "installed": driver.installed(),
                    "authenticated": driver.authenticated(),
                },
            )

        def do_POST(self) -> None:
            request = read_json_request(self)
            if request is None:
                return
            path = self.path.rstrip("/")
            if path == "/v1/agent/cancel":
                session_id = str(request.get("session_id") or "")
                send_json(self, {"ok": _PROCESSES.cancel(session_id)})
                return
            if path != "/v1/agent/run":
                self.send_error(404)
                return
            session_id = str(request.get("session_id") or uuid.uuid4().hex[:12])
            text = str(request.get("text") or "").strip()
            if not text:
                send_json(self, {"error": "text is required"}, status=400)
                return
            write_ndjson_headers(self)
            write_event = make_write_event(self)
            try:
                _run_turn(
                    driver,
                    session_id,
                    text,
                    cwd=_safe_workspace(request, workspace),
                    write_event=write_event,
                )
            except Exception as exc:  # noqa: BLE001
                write_event(event("agent.error", session_id, content=str(exc)))

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    driver = create_driver(args.driver)
    workspace = fallback_work_dir(ROOT)
    workspace.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        handler_for(driver, workspace),
    )
    print(
        f"{driver.spec.name} AgentDock gateway on "
        f"http://{args.host}:{args.port}/v1/agent"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
