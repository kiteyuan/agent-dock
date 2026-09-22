"""Fixed ``agentdock`` MCP entry: always present, never user-deletable."""

from __future__ import annotations

BUILTIN_NAME = "agentdock"


def is_builtin_name(name: str) -> bool:
    return str(name or "").strip() == BUILTIN_NAME


def builtin_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}/mcp"


def builtin_entry(url: str, *, enabled: bool = True) -> dict:
    return {
        "type": "http",
        "url": str(url).strip(),
        "enabled": bool(enabled),
    }


def merge_builtin(
    servers: dict[str, dict],
    *,
    url: str,
    enabled: bool | None = None,
) -> dict[str, dict]:
    """Force-inject the builtin server; keep only its ``enabled`` toggle from callers."""
    previous = servers.get(BUILTIN_NAME) if isinstance(servers.get(BUILTIN_NAME), dict) else {}
    if enabled is None:
        enabled = previous.get("enabled", True) is not False
    out = {
        name: dict(entry)
        for name, entry in servers.items()
        if name != BUILTIN_NAME and isinstance(entry, dict)
    }
    out[BUILTIN_NAME] = builtin_entry(url, enabled=bool(enabled))
    return out


def annotate_builtin(servers: dict[str, dict]) -> dict[str, dict]:
    """Admin view helper: mark the fixed server so the UI can lock edit/delete."""
    out: dict[str, dict] = {}
    for name, entry in servers.items():
        row = dict(entry)
        if is_builtin_name(name):
            row["builtin"] = True
        out[name] = row
    return out
