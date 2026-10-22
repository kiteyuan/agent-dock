"""config.yaml + config.local.yaml merge."""

from __future__ import annotations

from pathlib import Path

import yaml
from runtime.config import deep_merge, load_config


def test_deep_merge_nested() -> None:
    base = {"stt": {"whisper": {"model": "small", "device": "cpu"}}, "a": 1}
    overlay = {"stt": {"whisper": {"device": "cuda"}}, "b": 2}
    assert deep_merge(base, overlay) == {
        "stt": {"whisper": {"model": "small", "device": "cuda"}},
        "a": 1,
        "b": 2,
    }


def test_load_config_merges_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.dump({"stt": {"whisper": {"model": "small", "device": "cpu"}}, "x": 1}),
        encoding="utf-8",
    )
    (tmp_path / "config.local.yaml").write_text(
        yaml.dump({"stt": {"whisper": {"device": "cuda"}}, "y": 2}),
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path / "config.yaml"))
    assert cfg["stt"]["whisper"]["model"] == "small"
    assert cfg["stt"]["whisper"]["device"] == "cuda"
    assert cfg["x"] == 1
    assert cfg["y"] == 2


def test_load_config_without_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump({"server": {"port": 8765}}), encoding="utf-8")
    cfg = load_config(str(path))
    assert cfg["server"]["port"] == 8765
