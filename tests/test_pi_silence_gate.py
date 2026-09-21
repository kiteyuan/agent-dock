"""SilenceGate: VAD hangover without audio hardware."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "clients" / "rpi"))

from device.listen import SilenceGate


def test_silence_after_speech() -> None:
    g = SilenceGate(min_speech_frames=2, silence_frames=3)
    assert g.feed(True) is False
    assert g.feed(True) is False
    assert g.feed(False) is False
    assert g.feed(False) is False
    assert g.feed(False) is True


def test_silence_ignored_before_speech() -> None:
    g = SilenceGate(min_speech_frames=3, silence_frames=2)
    assert g.feed(False) is False
    assert g.feed(False) is False
    assert g.feed(True) is False
    assert g.feed(True) is False
    assert g.feed(True) is False
    assert g.feed(False) is False
    assert g.feed(False) is True


def test_speech_resets_silence_run() -> None:
    g = SilenceGate(min_speech_frames=1, silence_frames=3)
    g.feed(True)
    g.feed(False)
    g.feed(False)
    g.feed(True)
    assert g.silence_run == 0
    assert g.feed(False) is False
    assert g.feed(False) is False
    assert g.feed(False) is True
