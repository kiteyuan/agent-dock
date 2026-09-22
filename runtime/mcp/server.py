"""Minimal Streamable HTTP JSON-RPC handler for the builtin Runtime MCP."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from runtime.mcp.tools import call_tool, initialize_result, tool_catalog

_SUPPORTED = {"2024-11-05", "2025-03-26"}


def handle_mcp_http(host: Any, *, method: str, body: bytes | None = None) -> None:
    """Serve ``/mcp`` for MCP clients. Uses the same Admin access gates as ``/api``."""
    if method == "GET":
        # Streamable HTTP may open SSE; we only speak request/response JSON.
        host.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        host.send_header("Allow", "POST, OPTIONS")
        host.send_header("Content-Type", "application/json; charset=utf-8")
        host.end_headers()
        host.wfile.write(b'{"error":"use POST JSON-RPC"}')
        return
    if method == "OPTIONS":
        host.send_response(HTTPStatus.NO_CONTENT)
        host.send_header("Allow", "POST, OPTIONS")
        host.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Mcp-Session-Id")
        host.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        host.end_headers()
        return
    if method != "POST":
        host.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
        return

    runtime = host._runtime()
    if runtime is None:
        return

    raw = body if body is not None else b""
    if not raw.strip():
        host._json(HTTPStatus.BAD_REQUEST, {"error": "empty body"})
        return
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        host._json(HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
        return

    if isinstance(payload, list):
        if not payload:
            host._json(HTTPStatus.BAD_REQUEST, {"error": "empty batch"})
            return
        replies = []
        for item in payload:
            reply = _dispatch_message(runtime, item)
            if reply is not None:
                replies.append(reply)
        if not replies:
            host.send_response(HTTPStatus.ACCEPTED)
            host.send_header("Content-Type", "application/json; charset=utf-8")
            host.send_header("Content-Length", "0")
            host.end_headers()
            return
        host._json(HTTPStatus.OK, replies)
        return

    if not isinstance(payload, dict):
        host._json(HTTPStatus.BAD_REQUEST, {"error": "json-rpc object required"})
        return

    reply = _dispatch_message(runtime, payload)
    if reply is None:
        host.send_response(HTTPStatus.ACCEPTED)
        host.send_header("Content-Type", "application/json; charset=utf-8")
        host.send_header("Content-Length", "0")
        host.end_headers()
        return
    host._json(HTTPStatus.OK, reply)


def _dispatch_message(runtime: Any, message: object) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return _rpc_error(None, -32600, "Invalid Request")
    msg_id = message.get("id", None)
    method = message.get("method")
    # Notifications have no id (or id is omitted). JSON-RPC allows null id for requests too;
    # treat missing id as notification.
    is_notification = "id" not in message

    if not isinstance(method, str) or not method:
        if is_notification:
            return None
        return _rpc_error(msg_id, -32600, "Invalid Request")

    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None

    if method == "ping":
        return _rpc_result(msg_id, {})

    if method == "initialize":
        requested = str(params.get("protocolVersion") or _SUPPORTED_DEFAULT)
        version = requested if requested in _SUPPORTED else _SUPPORTED_DEFAULT
        result = initialize_result()
        result["protocolVersion"] = version
        return _rpc_result(msg_id, result)

    if method == "tools/list":
        return _rpc_result(msg_id, {"tools": tool_catalog()})

    if method == "tools/call":
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if not name:
            return _rpc_error(msg_id, -32602, "tool name required")
        return _rpc_result(msg_id, call_tool(runtime, name, arguments))

    if is_notification:
        return None
    return _rpc_error(msg_id, -32601, f"Method not found: {method}")


_SUPPORTED_DEFAULT = "2025-03-26"


def _rpc_result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
