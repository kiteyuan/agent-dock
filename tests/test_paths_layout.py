"""Path resolution and layout migration (layout v2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.layout_migrate import migrate_layout
from runtime.paths import (
    LAYOUT_VERSION,
    resolve_catalog_path,
    resolve_home,
    resolve_installs,
    resolve_logs,
    resolve_pets,
    resolve_state,
    resolve_vault,
    resolve_voices,
    resolve_workspace,
)
from runtime.platform.catalog import ModuleCatalog


def test_default_home_is_repo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTDOCK_HOME", raising=False)
    home = resolve_home({})
    assert home.name == "data"


def test_agentdock_home_env_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENTDOCK_HOME", str(tmp_path / "home"))
    home = resolve_home({}, ensure=True)
    assert home == (tmp_path / "home").resolve()
    assert resolve_state({}, ensure=True) == home / "state"
    assert resolve_vault({}, ensure=True) == home / "vault"


def test_paths_block_children(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENTDOCK_HOME", raising=False)
    cfg = {
        "paths": {
            "home": str(tmp_path / "ad"),
            "vault": "vault",
            "state": "state",
            "installs": "installs",
        }
    }
    assert resolve_home(cfg, ensure=True) == (tmp_path / "ad").resolve()
    assert resolve_vault(cfg, ensure=True) == (tmp_path / "ad" / "vault").resolve()
    assert resolve_workspace(cfg) == resolve_vault(cfg)
    assert resolve_state(cfg, ensure=True) == (tmp_path / "ad" / "state").resolve()
    assert resolve_installs(cfg, ensure=True) == (tmp_path / "ad" / "installs").resolve()


def test_catalog_and_assets_defaults() -> None:
    catalog = resolve_catalog_path({})
    assert catalog.name == "catalog.yaml"
    assert catalog.parent.name == "catalog"
    pets = resolve_pets({})
    assert pets.name == "pets"
    assert "assets" in pets.parts
    voices = resolve_voices({})
    assert voices.name == "voices"
    assert "assets" in voices.parts
    # Voice/pet packs are host personalization and are gitignored — do not
    # require any pack files to exist in a clean checkout.


def test_module_catalog_loads_and_vault_in_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENTDOCK_HOME", str(tmp_path))
    catalog = ModuleCatalog.load({})
    assert catalog.module("pi") is not None
    ctx = catalog.context({})
    assert Path(ctx["workspace"]) == resolve_vault({})


def test_migrate_workspace_to_data_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENTDOCK_HOME", str(tmp_path / "data"))
    old_ws = tmp_path / "old-workspace"
    old_ws.mkdir()
    (old_ws / "runtime-state.json").write_text('{"defaults":{}}', encoding="utf-8")
    (old_ws / "logs").mkdir()
    (old_ws / "logs" / "pi.log").write_text("hi", encoding="utf-8")
    (old_ws / "modules" / "gpt-sovits").mkdir(parents=True)
    (old_ws / "modules" / "gpt-sovits" / "marker").write_text("x", encoding="utf-8")
    (old_ws / "Notes").mkdir()
    (old_ws / "Notes" / "a.md").write_text("note", encoding="utf-8")

    cfg = {"workspace": {"root": str(old_ws)}}
    report = migrate_layout(cfg)
    assert report["to"] == LAYOUT_VERSION

    state = resolve_state(cfg)
    assert (state / "runtime-state.json").is_file()
    assert (resolve_logs(cfg) / "pi.log").is_file()
    assert (resolve_installs(cfg) / "gpt-sovits" / "marker").is_file()
    assert (resolve_vault(cfg) / "Notes" / "a.md").is_file()
    version = json.loads((state / "layout-version.json").read_text(encoding="utf-8"))
    assert version["version"] == LAYOUT_VERSION

    report2 = migrate_layout(cfg)
    assert report2["from"] >= LAYOUT_VERSION
    assert report2["actions"] == []
