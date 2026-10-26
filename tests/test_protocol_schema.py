"""Device Protocol: every Runtime / shared-client builder must match protocol/device.schema.json."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from runtime.protocol import agent as A
from runtime.protocol import device as D
from runtime.protocol._generated import PAYLOAD_DEFS, AgentEventType, DeviceMessageType

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "protocol" / "device.schema.json").read_text(encoding="utf-8"))
SCHEMA_ID = SCHEMA["$id"]
REGISTRY = Registry().with_resource(SCHEMA_ID, Resource.from_contents(SCHEMA))


def _validator(def_name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{SCHEMA_ID}#/$defs/{def_name}"}, registry=REGISTRY)


def assert_valid_frame(frame: dict[str, Any] | str) -> None:
    if isinstance(frame, str):
        frame = json.loads(frame)
    _validator("Envelope").validate(frame)
    def_name = PAYLOAD_DEFS.get(frame["type"])
    assert def_name, f"type {frame['type']!r} is not declared in the schema"
    errors = sorted(_validator(def_name).iter_errors(frame["payload"]), key=str)
    assert not errors, f"{frame['type']}: " + "; ".join(e.message for e in errors)


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_generated_bindings_are_up_to_date() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_protocol.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_every_enum_member_has_a_payload_schema() -> None:
    for member in [*DeviceMessageType, *AgentEventType]:
        assert member.value in PAYLOAD_DEFS


def _frame(msg: D.DeviceMessage) -> dict[str, Any]:
    return json.loads(msg.model_dump_json())


RUNTIME_BUILDERS = [
    D.device_hello("dev-1"),
    D.device_hello("dev-1", "desktop", token="t", tts_id="edge"),
    D.user_message("s", "hi"),
    D.user_message(
        "s",
        "hi",
        agent_id="pi",
        tts_id="edge",
        tts_model="m",
        images=[{"mime": "image/png", "data": "AA=="}],
    ),
    D.session_accept("s", "dev-1"),
    D.session_accept(
        "s",
        "dev-1",
        advertise_url="ws://h:8765",
        tts_id="edge",
        pet_id="demo",
        agent_id="pi",
        assets_port=8766,
        assets_base_url="http://h:8766/pets",
        messages=[{"role": "user", "text": "x"}],
    ),
    D.session_reset(),
    D.session_reset("s"),
    D.session_reset_ok("s", "dev-1"),
    D.session_reset_ok("s", "dev-1", quarantined=["a"]),
    D.agents_list_result([{"id": "pi"}]),
    D.tts_list_result([{"id": "edge"}]),
    D.tts_list_result([{"id": "edge"}], "edge"),
    D.tts_selected("s", "edge"),
    D.tts_selected("s", "edge", "m"),
    D.pets_list_result([]),
    D.pets_list_result(
        [{"id": "demo"}], default_id="demo", base_url="http://h/pets", assets_port=8766
    ),
    D.pong(),
    D.pong("p1"),
    D.stt_final("s", "hello"),
    D.tts_start("s"),
    D.tts_start("s", tts_id="edge", format="mp3", text="hi"),
    D.tts_end("s"),
    D.error_msg("boom"),
    D.error_msg("boom", "s"),
]


@pytest.mark.parametrize("msg", RUNTIME_BUILDERS, ids=lambda m: m.type.value)
def test_runtime_device_builders_match_schema(msg: D.DeviceMessage) -> None:
    assert_valid_frame(_frame(msg))


AGENT_EVENTS = [
    A.agent_start("s"),
    A.agent_thinking("s", "hmm"),
    A.agent_tool_call("s", "read", {"path": "x"}),
    A.agent_tool_result("s", "read", content="ok", data={"n": 1}),
    A.agent_message("s", "hello"),
    A.agent_message("s", "quiet", speak=False),
    A.agent_done("s"),
    A.agent_cancel("s"),
    A.agent_cancel("s", "stopped"),
    A.agent_error("s", "bad"),
]


@pytest.mark.parametrize("event", AGENT_EVENTS, ids=lambda e: e.type.value)
def test_agent_events_match_schema(event: A.AgentEvent) -> None:
    assert_valid_frame(event.to_wire())


def _shared_protocol():
    path = ROOT / "clients" / "shared" / "protocol.py"
    spec = importlib.util.spec_from_file_location("shared_protocol_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shared_python_client_builders_match_schema() -> None:
    p = _shared_protocol()
    frames = [
        p.device_hello("d"),
        p.device_hello("d", "cli", token="t", tts_id="edge"),
        p.user_message("s", "hi", agent_id="pi", images=[{"mime": "image/png", "data": "AA=="}]),
        p.audio_start("s"),
        p.audio_end("s"),
        p.session_cancel("s"),
        p.session_reset(),
        p.session_reset("s"),
        p.tts_list(),
        p.pets_list(),
        p.tts_select("s", "edge", model="m"),
        p.agents_list(),
        p.ping(),
        p.device_status("s", "idle", "ok"),
    ]
    for frame in frames:
        assert_valid_frame(frame)


def test_unknown_payload_fields_are_rejected() -> None:
    frame = _frame(D.stt_final("s", "x"))
    frame["payload"]["txt"] = "typo"
    with pytest.raises(AssertionError, match="stt.final"):
        assert_valid_frame(frame)
