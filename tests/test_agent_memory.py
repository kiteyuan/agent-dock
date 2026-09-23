"""Agent session file quarantine (device-keyed Pi memory)."""

from pathlib import Path

from runtime.session.agent_memory import quarantine_device_sessions


def test_quarantine_moves_device_files(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    agent = root / "pi-coding"
    agent.mkdir(parents=True)
    keep = agent / "dev-other-device.jsonl"
    keep.write_text("keep", encoding="utf-8")
    target = agent / "dev-mobile-abc.jsonl"
    target.write_text("poison", encoding="utf-8")

    moved = quarantine_device_sessions(root, "mobile-abc", reason="reset")

    assert len(moved) == 1
    assert "dev-mobile-abc.jsonl" in moved[0]
    assert not target.exists()
    assert keep.exists()
    assert (root / "_quarantine").is_dir()
    assert any((root / "_quarantine").iterdir())


def test_quarantine_empty_device_id(tmp_path: Path) -> None:
    assert quarantine_device_sessions(tmp_path, "") == []
