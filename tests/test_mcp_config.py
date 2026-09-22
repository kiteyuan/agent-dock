import json

import pytest

from agents.mcp_launch import claude_args, codex_args, launch_servers, normalize_servers, sync_pi_mcp
from runtime.mcp.builtin import BUILTIN_NAME, builtin_url
from runtime.mcp.server import _dispatch_message
from runtime.mcp.tools import call_tool, tool_catalog
from runtime.platform.mcp_config import McpConfigStore


def test_mcp_menu_roundtrip_and_launch_args(tmp_path) -> None:
    store = McpConfigStore(tmp_path, admin_port=8766)
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
    names = [item["name"] for item in saved["servers"]]
    assert BUILTIN_NAME in names
    assert "files" in names and "docs" in names
    assert saved["mcpServers"][BUILTIN_NAME]["builtin"] is True
    assert saved["mcpServers"][BUILTIN_NAME]["url"] == builtin_url(8766)

    claude = claude_args(store.path)
    assert claude[:1] == ["--mcp-config"]
    payload = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert payload["files"]["command"] == "npx"
    assert payload[BUILTIN_NAME]["url"] == builtin_url(8766)
    assert "mcpServers" not in payload

    codex = codex_args(store.path)
    assert 'mcp_servers.files.command="npx"' in codex
    assert 'mcp_servers.files.env={ROOT="E:/workspace"}' in codex
    assert 'mcp_servers.docs.url="https://example.com/mcp"' in codex
    assert f'mcp_servers.{BUILTIN_NAME}.url="{builtin_url(8766)}"' in codex
    assert "mcp_servers.files.startup_timeout_sec=20" in codex

    cwd = tmp_path / "project"
    cwd.mkdir()
    sync_pi_mcp(cwd, store.path)
    pi = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert pi["mcpServers"]["docs"]["url"] == "https://example.com/mcp"
    assert pi["mcpServers"][BUILTIN_NAME]["url"] == builtin_url(8766)


def test_builtin_mcp_cannot_be_deleted_or_rewritten(tmp_path) -> None:
    store = McpConfigStore(tmp_path, admin_port=9001)
    store.ensure_builtin()
    wiped = store.replace([])
    assert BUILTIN_NAME in wiped["mcpServers"]
    assert wiped["mcpServers"][BUILTIN_NAME]["url"] == builtin_url(9001)

    hijack = store.replace(
        {
            "mcpServers": {
                BUILTIN_NAME: {
                    "url": "https://evil.example/mcp",
                    "enabled": False,
                },
                "docs": {"url": "https://example.com/mcp"},
            }
        }
    )
    assert hijack["mcpServers"][BUILTIN_NAME]["url"] == builtin_url(9001)
    assert hijack["mcpServers"][BUILTIN_NAME]["enabled"] is False
    assert hijack["mcpServers"][BUILTIN_NAME]["builtin"] is True
    assert "docs" in hijack["mcpServers"]

    on_disk = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    assert on_disk["mcpServers"][BUILTIN_NAME]["url"] == builtin_url(9001)
    assert "builtin" not in on_disk["mcpServers"][BUILTIN_NAME]


def test_disabled_builtin_is_kept_but_not_launched(tmp_path) -> None:
    store = McpConfigStore(tmp_path, admin_port=8766)
    store.replace(
        {
            "mcpServers": {
                BUILTIN_NAME: {"url": "http://ignored", "enabled": False},
                "docs": {"url": "https://example.com/mcp", "enabled": True},
            }
        }
    )
    active = launch_servers(store.path)
    assert BUILTIN_NAME not in active
    assert "docs" in active


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
    assert public["servers"][0]["env"]["TOKEN"] == "***" or any(
        row["name"] == "files" and row["env"]["TOKEN"] == "***" for row in public["servers"]
    )

    again = store.replace({"mcpServers": public["mcpServers"]})
    assert again["mcpServers"]["files"]["env"]["TOKEN"] == "***"
    on_disk = json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8"))
    assert on_disk["mcpServers"]["files"]["env"]["TOKEN"] == "secret-value"


def test_empty_mcp_menu_still_ships_builtin(tmp_path) -> None:
    store = McpConfigStore(tmp_path, admin_port=8766)
    store.replace([])
    active = launch_servers(store.path)
    assert set(active) == {BUILTIN_NAME}
    claude = claude_args(store.path)
    assert claude[:1] == ["--mcp-config"]
    codex = codex_args(store.path)
    assert f"mcp_servers.{BUILTIN_NAME}.url=" in "".join(codex)


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
    assert saved["mcpServers"]["docs"]["enabled"] is True
    assert saved["mcpServers"]["off"]["enabled"] is False

    claude_args(store.path)
    claude = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert "docs" in claude
    assert "off" not in claude
    assert BUILTIN_NAME in claude
    assert "enabled" not in claude["docs"]

    codex = codex_args(store.path)
    joined = "".join(codex)
    assert "mcp_servers.docs.url=" in joined
    assert "mcp_servers.off" not in joined

    cwd = tmp_path / "project"
    cwd.mkdir()
    sync_pi_mcp(cwd, store.path)
    pi = json.loads((cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert set(pi["mcpServers"]) == {"docs", BUILTIN_NAME}
    assert "enabled" not in pi["mcpServers"]["docs"]


def test_mcp_label_is_kept_for_admin_but_stripped_on_launch(tmp_path) -> None:
    store = McpConfigStore(tmp_path)
    saved = store.replace(
        {
            "mcpServers": {
                "docs": {
                    "url": "https://example.com/mcp",
                    "enabled": True,
                    "label": "文档检索",
                },
            }
        }
    )
    assert saved["mcpServers"]["docs"]["label"] == "文档检索"
    assert saved["servers"][0]["label"] == "文档检索" or any(
        row.get("name") == "docs" and row.get("label") == "文档检索"
        for row in saved["servers"]
    )

    claude_args(store.path)
    claude = json.loads((tmp_path / "mcp.claude.json").read_text(encoding="utf-8"))
    assert "docs" in claude
    assert "label" not in claude["docs"]
    assert "enabled" not in claude["docs"]


class _FakeLifecycle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def submit(self, action: str, target: str, options=None):
        self.calls.append((action, target))

        class Result:
            ok = True

            def model_dump(self, mode="json"):
                return {"ok": True, "job_id": "job-1", "action": action, "target": target}

        return Result()

    def jobs(self):
        return []

    def cancel(self, job_id: str) -> bool:
        return job_id == "job-1"


class _FakeSnapshot:
    def build(self):
        class Snap:
            def model_dump(self, mode="json"):
                return {
                    "defaults": {"agent": "pi-coding", "tts": "edge", "stt": "whisper", "pet": "furina"},
                    "counts": {"devices_online": 0, "sessions_active": 0},
                    "meta": {"workspace": "E:/ws"},
                    "modules": {
                        "agents": [
                            {
                                "id": "pi-coding",
                                "name": "Pi",
                                "is_default": True,
                                "ready": True,
                            }
                        ],
                        "tts": {
                            "default": "edge",
                            "engines": [
                                {
                                    "id": "edge",
                                    "name": "Edge",
                                    "selected": True,
                                    "ready": True,
                                    "status": "ready",
                                }
                            ],
                            "voices": [
                                {
                                    "id": "edge",
                                    "name": "Edge",
                                    "engine": "edge",
                                    "selected": True,
                                    "ready": True,
                                }
                            ],
                        },
                        "stt": {
                            "id": "whisper",
                            "ready": True,
                            "status": "ready",
                            "providers": [
                                {
                                    "id": "whisper",
                                    "name": "Whisper",
                                    "selected": True,
                                    "installed": True,
                                }
                            ],
                        },
                        "pets": {
                            "default": "miku",
                            "ready": True,
                            "pets": [
                                {"id": "miku", "name": "Miku", "present": True, "is_default": True},
                                {
                                    "id": "furina",
                                    "name": "Furina",
                                    "present": True,
                                    "is_default": False,
                                },
                            ],
                        },
                    },
                    "services": [],
                }

        return Snap()

    def set_default(self, kind: str, value: str) -> None:
        if kind == "agent" and value == "missing":
            raise ValueError("unknown agent")
        self.last = (kind, value)


class _FakeRuntime:
    def __init__(self, tmp_path) -> None:
        self.assets_port = 8766
        self.mcp = McpConfigStore(tmp_path, admin_port=8766)
        self.mcp.ensure_builtin()
        self.lifecycle = _FakeLifecycle()
        self.snapshot = _FakeSnapshot()


def test_list_modules_unwraps_nested_snapshot_shapes(tmp_path) -> None:
    runtime = _FakeRuntime(tmp_path)
    result = call_tool(runtime, "list_modules", {"kind": "all"})
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["agents"][0]["id"] == "pi-coding"
    assert payload["tts"]["default"] == "edge"
    assert payload["tts"]["engines"][0]["id"] == "edge"
    assert payload["tts"]["voices"][0]["id"] == "edge"
    assert payload["stt"]["default"] == "whisper"
    assert payload["stt"]["providers"][0]["id"] == "whisper"
    assert payload["pets"]["default"] == "miku"
    assert [item["id"] for item in payload["pets"]["pets"]] == ["miku", "furina"]

    pets_only = call_tool(runtime, "list_modules", {"kind": "pet"})
    pets_payload = json.loads(pets_only["content"][0]["text"])
    assert pets_payload["pets"]["pets"][0]["is_default"] is True


def test_builtin_mcp_tools_and_jsonrpc(tmp_path) -> None:
    runtime = _FakeRuntime(tmp_path)
    names = {tool["name"] for tool in tool_catalog()}
    assert "runtime_status" in names
    assert "set_default" in names
    assert "mcp_upsert" in names

    status = call_tool(runtime, "runtime_status", {})
    assert status["isError"] is False
    payload = json.loads(status["content"][0]["text"])
    assert payload["defaults"]["agent"] == "pi-coding"
    assert payload["mcp_url"].endswith("/mcp")

    switched = call_tool(runtime, "set_default", {"kind": "agent", "id": "pi-coding"})
    assert switched["isError"] is False
    assert runtime.snapshot.last == ("agent", "pi-coding")

    blocked = call_tool(
        runtime,
        "mcp_upsert",
        {"name": BUILTIN_NAME, "url": "https://evil.example/mcp"},
    )
    assert blocked["isError"] is True

    added = call_tool(
        runtime,
        "mcp_upsert",
        {"name": "docs", "url": "https://example.com/mcp"},
    )
    assert added["isError"] is False
    assert "docs" in runtime.mcp.public()["mcpServers"]

    removed = call_tool(runtime, "mcp_remove", {"name": BUILTIN_NAME})
    assert removed["isError"] is True

    init = _dispatch_message(
        runtime,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
        },
    )
    assert init["result"]["serverInfo"]["name"] == BUILTIN_NAME

    listed = _dispatch_message(
        runtime,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert len(listed["result"]["tools"]) >= 8

    note = _dispatch_message(
        runtime,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert note is None


def _disk_token(store: McpConfigStore, name: str = "secret-stdio") -> str | None:
    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    env = (on_disk.get("mcpServers") or {}).get(name, {}).get("env") or {}
    return env.get("TOKEN")


def test_mcp_tool_mutations_preserve_secrets_via_public_roundtrip(tmp_path) -> None:
    """Mutations must not wipe secrets when round-tripping public() redacted mcpServers."""
    from runtime.mcp import tools as mcp_tools

    store = McpConfigStore(tmp_path, admin_port=8766)
    store.replace(
        {
            "mcpServers": {
                "secret-stdio": {
                    "command": "npx",
                    "args": ["-y", "secret-server"],
                    "env": {"TOKEN": "secret-value"},
                }
            }
        }
    )
    assert BUILTIN_NAME in store.public()["mcpServers"]
    assert _disk_token(store) == "secret-value"

    # 1) mcp_set_enabled via the same public() → replace pattern tools use
    class _Rt:
        mcp = store

    mcp_tools._mcp_set_enabled(_Rt(), "secret-stdio", False)
    assert _disk_token(store) == "secret-value", "FATAL: set_enabled wiped TOKEN"

    # 2) mcp_upsert a DIFFERENT server — other servers' secrets must survive
    mcp_tools._mcp_upsert(
        _Rt(),
        {"name": "other-http", "url": "https://example.com/other"},
    )
    assert _disk_token(store) == "secret-value", "FATAL: upsert(other) wiped TOKEN"

    # 3) mcp_upsert SAME server with only command (no env) — must keep prior env
    mcp_tools._mcp_upsert(
        _Rt(),
        {"name": "secret-stdio", "command": "npx", "args": ["-y", "secret-server"]},
    )
    assert _disk_token(store) == "secret-value", (
        "FATAL: same-server upsert without env wiped TOKEN "
        "(omitting optional env must preserve on-disk secrets)"
    )

    # 4) Re-seed and confirm upsert of a brand-new http server does not wipe others
    store.replace(
        {
            "mcpServers": {
                "secret-stdio": {
                    "command": "npx",
                    "args": ["-y", "secret-server"],
                    "env": {"TOKEN": "secret-value"},
                }
            }
        }
    )
    mcp_tools._mcp_upsert(
        _Rt(),
        {"name": "brand-new", "url": "https://example.com/brand-new"},
    )
    assert _disk_token(store) == "secret-value", "FATAL: upsert(new http) wiped TOKEN"
