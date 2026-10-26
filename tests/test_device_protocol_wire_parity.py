"""Golden wire-name parity: Runtime DeviceMessageType vs desk-pet JS + mobile Dart.

Not full codegen — fails CI when a client drops or renames a core type string.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from runtime.protocol.device import DeviceMessageType

ROOT = Path(__file__).resolve().parents[1]

# Host desk pet: turn + pets vocabulary (TTS list/select/ping are optional there).
DESK_PET_TYPES = frozenset(
    {
        DeviceMessageType.DEVICE_HELLO.value,
        DeviceMessageType.USER_MESSAGE.value,
        DeviceMessageType.AUDIO_START.value,
        DeviceMessageType.AUDIO_END.value,
        DeviceMessageType.SESSION_CANCEL.value,
        DeviceMessageType.SESSION_RESET.value,
        DeviceMessageType.PETS_LIST.value,
        DeviceMessageType.SESSION_ACCEPT.value,
        DeviceMessageType.STT_FINAL.value,
        DeviceMessageType.TTS_START.value,
        DeviceMessageType.TTS_END.value,
        DeviceMessageType.ERROR.value,
    }
)

# Agent events are not DeviceMessageType but clients handle them as type strings.
CORE_AGENT_TYPES = frozenset(
    {
        "agent.start",
        "agent.thinking",
        "agent.tool_call",
        "agent.tool_result",
        "agent.message",
        "agent.done",
        "agent.cancel",
        "agent.error",
    }
)


def _quoted_strings(text: str) -> set[str]:
    return set(re.findall(r"""['"]([a-z][a-z0-9_.]+)['"]""", text))


@pytest.fixture(scope="module")
def desk_js_blob() -> str:
    js_dir = ROOT / "desktop" / "web" / "js"
    parts = [p.read_text(encoding="utf-8") for p in sorted(js_dir.glob("*.js"))]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def dart_blob() -> str:
    dart_root = ROOT / "clients" / "mobile" / "lib"
    parts = [p.read_text(encoding="utf-8") for p in sorted(dart_root.rglob("*.dart"))]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def shared_py_blob() -> str:
    return (ROOT / "clients" / "shared" / "protocol.py").read_text(encoding="utf-8")


def test_device_message_type_enum_values_are_unique() -> None:
    values = [m.value for m in DeviceMessageType]
    assert len(values) == len(set(values))


def test_desk_pet_js_mentions_core_device_types(desk_js_blob: str) -> None:
    found = _quoted_strings(desk_js_blob)
    missing = sorted(DESK_PET_TYPES - found)
    assert not missing, f"desktop/web/js missing wire types: {missing}"


def test_desk_pet_js_mentions_core_agent_types(desk_js_blob: str) -> None:
    found = _quoted_strings(desk_js_blob)
    missing = sorted(CORE_AGENT_TYPES - found)
    assert not missing, f"desktop/web/js missing agent wire types: {missing}"


def test_mobile_dart_mentions_core_outbound_types(dart_blob: str) -> None:
    """Mobile must send the same hello/turn/cancel vocabulary as Runtime expects."""
    outbound = {
        DeviceMessageType.DEVICE_HELLO.value,
        DeviceMessageType.USER_MESSAGE.value,
        DeviceMessageType.AUDIO_START.value,
        DeviceMessageType.AUDIO_END.value,
        DeviceMessageType.SESSION_CANCEL.value,
        DeviceMessageType.SESSION_RESET.value,
        DeviceMessageType.TTS_LIST.value,
        DeviceMessageType.TTS_SELECT.value,
        DeviceMessageType.PETS_LIST.value,
        DeviceMessageType.PING.value,
    }
    found = _quoted_strings(dart_blob)
    missing = sorted(outbound - found)
    assert not missing, f"clients/mobile missing outbound wire types: {missing}"


def test_shared_python_protocol_mentions_core_outbound(shared_py_blob: str) -> None:
    outbound = {
        DeviceMessageType.DEVICE_HELLO.value,
        DeviceMessageType.USER_MESSAGE.value,
        DeviceMessageType.AUDIO_START.value,
        DeviceMessageType.AUDIO_END.value,
        DeviceMessageType.SESSION_CANCEL.value,
        DeviceMessageType.PING.value,
    }
    found = _quoted_strings(shared_py_blob)
    missing = sorted(outbound - found)
    assert not missing, f"clients/shared/protocol.py missing wire types: {missing}"
