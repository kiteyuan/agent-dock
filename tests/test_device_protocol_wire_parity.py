"""Clients must handle the core vocabulary via generated constants (protocol/device.schema.json).

Field-level shape is covered by test_protocol_schema.py; this guards that the desk pet
and the mobile client still reference every core type instead of dropping one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from runtime.protocol._generated import AgentEventType, DeviceMessageType

ROOT = Path(__file__).resolve().parents[1]
T = DeviceMessageType

DESK_PET_TYPES = {
    T.DEVICE_HELLO, T.USER_MESSAGE, T.AUDIO_START, T.AUDIO_END, T.SESSION_CANCEL,
    T.SESSION_RESET, T.PETS_LIST, T.SESSION_ACCEPT, T.SESSION_RESET_OK,
    T.PETS_LIST_RESULT, T.STT_FINAL, T.TTS_START, T.TTS_END, T.ERROR,
}  # fmt: skip

MOBILE_TYPES = {
    T.DEVICE_HELLO, T.USER_MESSAGE, T.AUDIO_START, T.AUDIO_END, T.SESSION_CANCEL,
    T.SESSION_RESET, T.TTS_LIST, T.TTS_SELECT, T.PETS_LIST, T.PING,
    T.SESSION_ACCEPT, T.TTS_LIST_RESULT, T.PETS_LIST_RESULT, T.STT_FINAL,
    T.TTS_START, T.TTS_END, T.PONG, T.ERROR,
}  # fmt: skip


def _camel(name: str) -> str:
    head, *rest = name.lower().split("_")
    return head + "".join(p.capitalize() for p in rest)


def _blob(root: Path, pattern: str, skip: str) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(root.rglob(pattern))
        if not p.name.endswith(skip)
    )


@pytest.fixture(scope="module")
def desk_js() -> str:
    return _blob(ROOT / "desktop" / "web" / "js", "*.js", ".gen.js")


@pytest.fixture(scope="module")
def dart() -> str:
    return _blob(ROOT / "clients" / "mobile" / "lib", "*.dart", ".gen.dart")


def test_desk_pet_uses_core_device_types(desk_js: str) -> None:
    missing = sorted(t.name for t in DESK_PET_TYPES if f"MSG.{t.name}" not in desk_js)
    assert not missing, f"desktop/web/js does not reference MSG.{missing}"


def test_desk_pet_handles_all_agent_events(desk_js: str) -> None:
    missing = sorted(e.name for e in AgentEventType if f"AGENT.{e.name}" not in desk_js)
    assert not missing, f"desktop/web/js does not reference AGENT.{missing}"


def test_mobile_uses_core_device_types(dart: str) -> None:
    missing = sorted(t.name for t in MOBILE_TYPES if f"Msg.{_camel(t.name)}" not in dart)
    assert not missing, f"clients/mobile does not reference Msg.{missing}"


def test_mobile_handles_all_agent_events(dart: str) -> None:
    missing = sorted(e.name for e in AgentEventType if f"AgentEvt.{_camel(e.name)}" not in dart)
    assert not missing, f"clients/mobile does not reference AgentEvt.{missing}"


def test_no_raw_wire_literals_left_in_clients(desk_js: str, dart: str) -> None:
    for member in [*DeviceMessageType, *AgentEventType]:
        if member.value == "error":
            continue
        for quoted in (f'"{member.value}"', f"'{member.value}'"):
            assert quoted not in desk_js, f"desk pet hard-codes {quoted}; use MSG/AGENT"
            assert quoted not in dart, f"mobile hard-codes {quoted}; use Msg/AgentEvt"
