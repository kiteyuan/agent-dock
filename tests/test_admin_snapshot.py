from __future__ import annotations

import socket
from pathlib import Path

from runtime.platform.catalog import ModuleCatalog
from runtime.runtime import Runtime


def test_snapshot_does_not_perform_network_probe(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTDOCK_HOME", str(tmp_path / "home"))
    cfg = {
        "paths": {"home": str(tmp_path / "home")},
        "pets": {"root": str(tmp_path / "pets")},
        "stt": {"provider": "none"},
        "agent": {
            "default": "pi",
            "agents": {
                "pi": {
                    "type": "http",
                    "url": "http://127.0.0.1:9001/v1/agent/run",
                }
            },
        },
        "tts": {
            "default": "edge",
            "providers": {"edge": {"type": "edge", "name": "Edge TTS"}},
        },
        "server": {"host": "127.0.0.1"},
        "security": {"require_token": False},
    }
    runtime = Runtime(cfg)

    def forbidden(*args, **kwargs):
        raise AssertionError("snapshot attempted a network probe")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    snapshot = runtime.snapshot.build()
    assert snapshot.defaults == {"agent": "pi", "tts": "edge", "stt": "none"}
    assert snapshot.counts["devices_online"] == 0
    assert snapshot.recommendations["tts"] == "edge"
    assert snapshot.modules["llm"]["shared"]["configured"] is False
    assert "openai" in {
        item["id"] for item in snapshot.modules["llm"]["shared"]["providers"]
    }
    for agent in snapshot.modules["agents"]:
        assert agent["installable"] is False
        assert agent["can_prepare"] is False
    codex = next(item for item in snapshot.services if item["id"] == "codex")
    assert codex["group"] == "agent"
    assert "<" not in codex["detail"]
    runtime_svc = next(item for item in snapshot.services if item["id"] == "runtime")
    assert runtime_svc["group"] == "core"
    assert "web" not in {item["id"] for item in snapshot.services}
    runtime.lifecycle.close()


def test_admin_ui_uses_one_fetch_path_and_visibility_guard() -> None:
    root = Path(__file__).resolve().parents[1] / "runtime" / "admin" / "ui" / "src"
    api = (root / "api.ts").read_text(encoding="utf-8")
    hook = (root / "hooks" / "useSnapshot.ts").read_text(encoding="utf-8")
    assert api.count("fetch(") == 1
    assert hook.count("api<Snapshot>(") == 1
    assert '"/api/v1/snapshot?discover=1"' in hook
    assert '"/api/v1/snapshot"' in hook
    assert "if (inFlight.current)" in hook
    assert "document.hidden" in hook
    assert 'document.addEventListener("visibilitychange"' in hook


def test_admin_ui_separates_beginner_and_advanced_information() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "runtime" / "admin" / "ui" / "src"
    app = (src / "App.tsx").read_text(encoding="utf-8")
    shell = (src / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    chrome = app + shell
    pages = "\n".join(
        path.read_text(encoding="utf-8") for path in src.rglob("*.tsx")
    ) + "\n".join(path.read_text(encoding="utf-8") for path in src.rglob("*.ts"))
    index = (root / "runtime" / "admin" / "ui" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "智能助手" in chrome
    assert "声音" in chrome
    assert "高级设置" in chrome
    assert 'data-tab="tts"' not in pages
    assert 'data-tab="stt"' not in pages
    assert "renderWizard" not in pages
    assert "/api/v1/wizard" not in pages
    assert "不用理解模型、端口或进程" not in pages
    assert "日常使用不需要修改" not in pages
    assert "让设备拥有智能" not in index
    assert "/admin/icons/" in pages
    assert "统一模型" in pages
    assert "统一配置" in pages
    assert "自定义模型名" in pages
    assert "/api/v1/llm/shared" in pages
    assert "/api/v1/agents/" in pages
    assert "去官网安装" in pages
    assert "recheck" in pages
    assert "需要独立模型设置" not in pages
    assert "我已安装，重新检测" not in pages
    assert "Runtime 不会代为安装" not in pages
    assert "当前系统不可用" not in pages
    assert "各助手可在模型设置" not in pages


def test_admin_ships_local_icons_for_every_agent() -> None:
    root = Path(__file__).resolve().parents[1]
    icons = root / "runtime" / "admin" / "ui" / "public" / "icons"
    for spec in ModuleCatalog.load({}).modules_by_kind("agent"):
        path = icons / ("pi.svg" if spec.id == "pi" else f"{spec.id}.png")
        assert path.is_file(), f"missing icon for {spec.id}"
        assert path.stat().st_size > 200
