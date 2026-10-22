"""First-boot seeds from examples/."""

from __future__ import annotations

from pathlib import Path

from runtime.seed import seed_defaults, seed_demo_pet, seed_notes


def test_seed_notes_into_empty_vault(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTDOCK_HOME", str(home))
    actions = seed_notes({})
    notes = home / "vault" / "notes"
    assert (notes / "Welcome.md").is_file()
    assert (notes / "AgentDock.md").is_file()
    assert any(a.startswith("seed:notes:") for a in actions)
    # Idempotent
    assert seed_notes({}) == []


def test_seed_demo_pet_when_no_pets(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    pets = tmp_path / "pets-root"
    pets.mkdir()
    monkeypatch.setenv("AGENTDOCK_HOME", str(home))
    cfg = {"paths": {"pets": str(pets)}}
    actions = seed_demo_pet(cfg)
    sheet = pets / "demo" / "spritesheet.webp"
    assert sheet.is_file()
    assert actions == ["seed:pet:demo"]
    assert seed_demo_pet(cfg) == []


def test_seed_defaults_combined(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    pets = tmp_path / "pets-root"
    pets.mkdir()
    monkeypatch.setenv("AGENTDOCK_HOME", str(home))
    actions = seed_defaults({"paths": {"pets": str(pets)}})
    assert any(a.startswith("seed:notes:") for a in actions)
    assert "seed:pet:demo" in actions
