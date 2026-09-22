"""Builtin Runtime MCP (fixed control plane for agents)."""

from __future__ import annotations

from runtime.mcp.builtin import (
    BUILTIN_NAME,
    builtin_entry,
    builtin_url,
    is_builtin_name,
    merge_builtin,
)
from runtime.mcp.server import handle_mcp_http

__all__ = [
    "BUILTIN_NAME",
    "builtin_entry",
    "builtin_url",
    "handle_mcp_http",
    "is_builtin_name",
    "merge_builtin",
]
