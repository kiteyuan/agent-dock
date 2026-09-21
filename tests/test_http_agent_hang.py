"""Regression: HTTP agent must not wedge the event loop after a terminal event."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from runtime.agent.adapters.http import HTTPAgent
from runtime.protocol.agent import AgentEventType, AgentRequest


class _SlowAfterErrorHandler(BaseHTTPRequestHandler):
    """Emit agent.error then block forever so a naive readline waiter would hang."""

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        line = (
            json.dumps(
                {
                    "type": "agent.error",
                    "payload": {"session_id": "s1", "content": "Request timed out."},
                }
            )
            + "\n"
        ).encode()
        self.wfile.write(line)
        self.wfile.flush()
        # Hold the connection open; Runtime must force-close and finish the turn.
        threading.Event().wait(30)


@pytest.fixture()
def slow_error_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowAfterErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}/v1/agent/run"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_agent_releases_after_terminal_error(slow_error_server: str) -> None:
    agent = HTTPAgent(slow_error_server, agent_id="test", mode="stream", timeout=5)
    request = AgentRequest(session_id="s1", text="hi")

    async def consume() -> list[AgentEventType]:
        types: list[AgentEventType] = []
        async for event in agent.run(request):
            types.append(event.type)
            if event.type in (
                AgentEventType.DONE,
                AgentEventType.CANCEL,
                AgentEventType.ERROR,
            ):
                break
        return types

    types = asyncio.run(asyncio.wait_for(consume(), timeout=5.0))
    assert AgentEventType.ERROR in types
