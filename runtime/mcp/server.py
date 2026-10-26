"""Minimal Streamable HTTP JSON-RPC handler for the builtin Runtime MCP."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from runtime.mcp.tools import call_tool, initialize_result, tool_catalog

_SUPPORTED = {"2024-11-05", "2025-03-26"}


def handle_mcp_post(runtime: Any, raw: bytes) -> tuple[int, Any]:
    """JSON-RPC over POST ``/mcp``. Body ``None`` in the reply means 202 with no content.

    Streamable HTTP SSE (GET) is not offered; the HTTP layer answers GET with 405.
    """
    if not raw.strip():
        return HTTPStatus.BAD_REQUEST, {"error": "empty body"}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HTTPStatus.BAD_REQUEST, {"error": "invalid json"}

    if isinstance(payload, list):
        if not payload:
            return HTTPStatus.BAD_REQUEST, {"error": "empty batch"}
        replies = [r for item in payload if (r := _dispatch_message(runtime, item)) is not None]
        return (HTTPStatus.OK, replies) if replies else (HTTPStatus.ACCEPTED, None)

    if not isinstance(payload, dict):
        return HTTPStatus.BAD_REQUEST, {"error": "json-rpc object required"}

    reply = _dispatch_message(runtime, payload)
    return (HTTPStatus.ACCEPTED, None) if reply is None else (HTTPStatus.OK, reply)


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
