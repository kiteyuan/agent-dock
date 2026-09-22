"""Tests for vault path helpers."""

from __future__ import annotations

from pathlib import Path

from runtime.paths import repo_root, resolve_vault, resolve_workspace


def test_default_vault_under_data(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDOCK_HOME", raising=False)
    path = resolve_workspace({})
    assert path == (repo_root() / "data" / "vault").resolve()
    assert path == resolve_vault({})


def test_absolute_legacy_workspace_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGENTDOCK_HOME", raising=False)
    abs_path = tmp_path / "ws"
    abs_path.mkdir()
    path = resolve_workspace({"workspace": {"root": str(abs_path)}})
    assert path == abs_path.resolve()


def test_relative_legacy_workspace_root(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDOCK_HOME", raising=False)
    path = resolve_workspace({"workspace": {"root": "workspace"}})
    assert path == (repo_root() / "workspace").resolve()
