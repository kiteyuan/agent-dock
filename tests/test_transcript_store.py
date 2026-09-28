"""Unit tests for completed-turn transcript store."""

from __future__ import annotations

from pathlib import Path

from runtime.session.transcript import TranscriptStore


def test_append_and_load(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path, max_messages=50)
    store.append_completed(
        "web-1",
        user_text="你好",
        assistant_texts=["在的"],
    )
    msgs = store.load("web-1")
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "text": "你好", "ts": msgs[0]["ts"]}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["text"] == "在的"


def test_skips_empty_assistant(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.append_completed("d1", user_text="hi", assistant_texts=["", "  "])
    assert store.load("d1") == []


def test_clear(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.append_completed("d1", user_text="a", assistant_texts=["b"])
    store.clear("d1")
    assert store.load("d1") == []


def test_max_messages_trims(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path, max_messages=4)
    for i in range(3):
        store.append_completed("d1", user_text=f"u{i}", assistant_texts=[f"a{i}"])
    msgs = store.load("d1")
    assert len(msgs) == 4
    assert msgs[0]["text"] == "u1"
    assert msgs[-1]["text"] == "a2"
