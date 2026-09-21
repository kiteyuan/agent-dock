"""One shared MCP menu, stored in the workspace and read when an agent starts."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from agents.mcp_launch import (
    document,
    merge_server_secrets,
    normalize_document,
    read_servers,
    redact_servers,
    servers_for_admin,
)


class McpConfigStore:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "mcp.json"
        self._lock = threading.Lock()

    def public(self) -> dict:
        with self._lock:
            servers = read_servers(self.path)
            return {
                "mcpServers": redact_servers(servers),
                "servers": servers_for_admin(self.path),
            }

    def replace(self, raw: object) -> dict:
        incoming = normalize_document(raw)
        with self._lock:
            existing = read_servers(self.path)
            servers = merge_server_secrets(incoming, existing)
            payload = document(servers)
            text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            return {
                "mcpServers": redact_servers(servers),
                "servers": servers_for_admin(self.path),
            }
