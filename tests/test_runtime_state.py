from __future__ import annotations

import json

import pytest

from runtime.platform.module_state import ModuleState
from runtime.platform.state import RuntimeState


def test_runtime_state_persists_defaults_atomically(tmp_path) -> None:
    state = RuntimeState(tmp_path)
    state.set_default("agent", "pi")
    state.set_default("tts", "edge")

    loaded = RuntimeState(tmp_path)
    assert loaded.default("agent") == "pi"
    assert loaded.default("tts") == "edge"
    assert json.loads((tmp_path / "runtime-state.json").read_text())["schema_version"] == 1
    assert not (tmp_path / "runtime-state.json.tmp").exists()


def test_runtime_state_rejects_unknown_default(tmp_path) -> None:
    with pytest.raises(ValueError):
        RuntimeState(tmp_path).set_default("pet", "arona")


def test_module_state_separates_receipts_and_licenses(tmp_path) -> None:
    state = ModuleState(tmp_path)
    state.accept_license("gpt-sovits", "mit", accepted=True)
    state.set_receipt("gpt-sovits", {"version": "external"})

    loaded = ModuleState(tmp_path)
    assert loaded.accepted("gpt-sovits", "mit")
    assert loaded.receipt("gpt-sovits")["version"] == "external"
