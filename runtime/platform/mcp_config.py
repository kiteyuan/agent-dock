"""One shared MCP menu, stored in the workspace and read when an agent starts."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from runtime.platform.mcp_launch import (
    document,
    merge_server_secrets,
    normalize_document,
    read_servers,
    redact_servers,
)
from runtime.mcp.builtin import (
    BUILTIN_NAME,
    annotate_builtin,
    builtin_url,
    merge_builtin,
)


class McpConfigStore:
    def __init__(self, workspace: Path, *, admin_port: int = 8766) -> None:
        self.path = workspace / "mcp.json"
        self._lock = threading.Lock()
        self._admin_port = int(admin_port)

    def set_admin_port(self, port: int) -> None:
        self._admin_port = int(port)

    def ensure_builtin(self) -> dict:
        """Make sure the fixed Runtime MCP is on disk with the current Admin URL."""
        with self._lock:
            existing = read_servers(self.path)
            enabled = True
            prior = existing.get(BUILTIN_NAME)
            if isinstance(prior, dict):
                enabled = prior.get("enabled", True) is not False
            servers = merge_builtin(
                existing,
                url=builtin_url(self._admin_port),
                enabled=enabled,
            )
            self._write(servers)
            return self._public_unlocked(servers)

    def public(self) -> dict:
        with self._lock:
            servers = merge_builtin(
                read_servers(self.path),
                url=builtin_url(self._admin_port),
            )
            return self._public_unlocked(servers)

    def replace(self, raw: object) -> dict:
        incoming = normalize_document(raw)
        with self._lock:
            existing = read_servers(self.path)
            # Preserve builtin enabled toggle from the incoming document when present.
            enabled = None
            if BUILTIN_NAME in incoming:
                enabled = incoming[BUILTIN_NAME].get("enabled", True) is not False
            elif BUILTIN_NAME in existing:
                enabled = existing[BUILTIN_NAME].get("enabled", True) is not False
            # Drop any attempt to redefine the builtin transport before merge.
            incoming.pop(BUILTIN_NAME, None)
            servers = merge_server_secrets(incoming, existing)
            servers = merge_builtin(
                servers,
                url=builtin_url(self._admin_port),
                enabled=enabled,
            )
            self._write(servers)
            return self._public_unlocked(servers)

    def _write(self, servers: dict[str, dict]) -> None:
        payload = document(servers)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)

    def _public_unlocked(self, servers: dict[str, dict]) -> dict:
        redacted = annotate_builtin(redact_servers(servers))
        rows = []
        for name, entry in redacted.items():
            env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
            headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
            row = {
                "name": name,
                "enabled": entry.get("enabled", True) is not False,
                "command": str(entry.get("command") or ""),
                "args": [str(item) for item in entry.get("args") or []],
                "env": env,
                "has_env": bool(entry.get("has_env") or env),
                "url": str(entry.get("url") or ""),
                "headers": headers,
                "has_headers": bool(entry.get("has_headers") or headers),
            }
            label = str(entry.get("label") or "").strip()
            if label:
                row["label"] = label
            if entry.get("builtin"):
                row["builtin"] = True
            rows.append(row)
        return {"mcpServers": redacted, "servers": rows}
