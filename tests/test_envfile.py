"""Unit tests for runtime.envfile."""

from __future__ import annotations

import os
from pathlib import Path

from runtime.envfile import load_env_file


def test_load_env_file_sets_missing_only(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "FOO=bar\n"
        "export BAZ=qux\n"
        "QUOTED=\"hi there\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FOO", "from-shell")
    monkeypatch.delenv("BAZ", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)

    assert load_env_file(path) is True
    assert os.environ["FOO"] == "from-shell"
    assert os.environ["BAZ"] == "qux"
    assert os.environ["QUOTED"] == "hi there"


def test_load_env_file_missing(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nope.env") is False
