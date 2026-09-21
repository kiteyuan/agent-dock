import json

import pytest

from agents.mcp_launch import claude_args, codex_args, normalize_servers, sync_pi_mcp
from runtime.platform.mcp_config import McpConfigStore


def test_mcp_menu_roundtrip_and_launch_args(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    saved = store.replace(
        [
            {
                "name": "files",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                "env": {"ROOT": "E:/workspace"},
            },
            {"name": "docs", "url": "https://example.com/mcp"},
        ]
    )
    assert [item["name"] for item in saved["servers"]] == ["files", "docs"]

    claude = claude_args(store.path)
    assert claude[:1] == ["--mcp-config"]
    payload = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert payload["files"]["command"] == "npx"
    assert "mcpServers" not in payload

    codex = codex_args(store.path)
    assert 'mcp_servers.files.command="npx"' in codex
    assert 'mcp_servers.files.env={ROOT="E:/workspace"}' in codex
    assert 'mcp_servers.docs.url="https://example.com/mcp"' in codex
    assert "mcp_servers.files.startup_timeout_sec=20" in codex

    cwd = tmp_path / "project"
    cwd.mkdir()
    sync_pi_mcp(cwd, store.path)
    pi = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert pi["mcpServers"]["docs"]["url"] == "https://example.com/mcp"


def test_mcp_menu_rejects_a_bad_server() -> None:
    with pytest.raises(ValueError, match="名称"):
        normalize_servers([{"name": "has space", "command": "npx"}])
    with pytest.raises(ValueError, match="命令或网址"):
        normalize_servers(
            [{"name": "both", "command": "npx", "url": "https://example.com/mcp"}]
        )


def test_mcp_json_document_keeps_http_headers(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    saved = store.replace(
        {
            "mcpServers": {
                "vs-code": {
                    "url": "https://example.com/api/v1/mcp",
                    "headers": {"Authorization": "Bearer token"},
                }
            }
        }
    )
    server = saved["mcpServers"]["vs-code"]
    assert server["type"] == "http"
    assert server["headers"]["Authorization"] == "***"
    assert server["has_headers"] is True
    on_disk = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    assert on_disk["mcpServers"]["vs-code"]["headers"]["Authorization"] == "Bearer token"

    claude_args(store.path)
    claude = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert claude["vs-code"]["headers"]["Authorization"] == "Bearer token"

    codex = codex_args(store.path)
    assert 'mcp_servers."vs-code".url="https://example.com/api/v1/mcp"' in codex
    assert 'mcp_servers."vs-code".http_headers={Authorization="Bearer token"}' in codex

    cwd = tmp_path / "project"
    cwd.mkdir()
    sync_pi_mcp(cwd, store.path)
    pi = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert pi["mcpServers"]["vs-code"]["headers"]["Authorization"] == "Bearer token"


def test_mcp_admin_roundtrip_preserves_masked_secrets(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    store.replace(
        {
            "mcpServers": {
                "files": {
                    "command": "npx",
                    "args": ["-y", "server"],
                    "env": {"TOKEN": "secret-value"},
                }
            }
        }
    )
    public = store.public()
    assert public["mcpServers"]["files"]["env"]["TOKEN"] == "***"
    assert public["servers"][0]["env"]["TOKEN"] == "***"

    again = store.replace({"mcpServers": public["mcpServers"]})
    assert again["mcpServers"]["files"]["env"]["TOKEN"] == "***"
    on_disk = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    assert on_disk["mcpServers"]["files"]["env"]["TOKEN"] == "secret-value"



def test_empty_mcp_menu_adds_no_launch_args(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    store.replace([])
    assert claude_args(store.path) == []
    assert codex_args(store.path) == []


def test_disabled_mcp_is_kept_but_not_launched(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    saved = store.replace(
        {
            "mcpServers": {
                "docs": {"url": "https://example.com/mcp", "enabled": True},
                "off": {"url": "https://example.com/off", "enabled": False},
            }
        }
    )
    assert saved["servers"][0]["enabled"] is True
    assert saved["servers"][1]["enabled"] is False
    assert saved["mcpServers"]["off"]["enabled"] is False

    claude_args(store.path)
    claude = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert "docs" in claude
    assert "off" not in claude
    assert "enabled" not in claude["docs"]

    codex = codex_args(store.path)
    assert "mcp_servers.docs.url=" in "".join(codex)
    assert "mcp_servers.off" not in "".join(codex)

    cwd = tmp_path / "project"
    cwd.mkdir()
    sync_pi_mcp(cwd, store.path)
    pi = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert set(pi["mcpServers"]) == {"docs"}
    assert "enabled" not in pi["mcpServers"]["docs"]
