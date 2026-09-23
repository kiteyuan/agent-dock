"""Unit tests for public Agent Protocol codec + HTTP parsing helpers."""

from __future__ import annotations

import json

from runtime.protocol.agent import PROTOCOL_VERSION, AgentEventType, AgentRequest
from runtime.protocol.agent_codec import (
    iter_json_body_events,
    iter_ndjson_events,
    iter_sse_events,
    parse_event,
    request_to_http_body,
)


def test_protocol_version() -> None:
    assert PROTOCOL_VERSION == "agentdock.agent/1.0"


def test_request_body_shape() -> None:
    req = AgentRequest(
        session_id="s1",
        text="hi",
        context=[],
        device={"device_id": "d1"},
        workspace=r"E:\Projects\AgentDock\workspace",
        instructions="【AgentDock Runtime】test",
    )
    body = request_to_http_body(req, stream=True)
    assert body["protocol"] == PROTOCOL_VERSION
    assert body["session_id"] == "s1"
    assert body["text"] == "hi"
    assert body["stream"] is True
    assert body["device"]["device_id"] == "d1"
    assert body["workspace"] == r"E:\Projects\AgentDock\workspace"
    assert body["instructions"].startswith("【AgentDock Runtime】")


def test_request_body_omits_empty_workspace() -> None:
    req = AgentRequest(session_id="s1", text="hi")
    body = request_to_http_body(req)
    assert "workspace" not in body
    assert "instructions" not in body


def test_agent_brief_mentions_mcp_and_notes() -> None:
    from runtime.bridge.agent_brief import build_agent_instructions

    text = build_agent_instructions(
        workspace="/tmp/vault",
        notes_root="/tmp/vault/notes",
        assets_port=8766,
    )
    assert "agentdock" in text
    assert "notes_search" in text
    assert "/tmp/vault" in text


def test_parse_canonical_message_speak() -> None:
    ev = parse_event(
        "s1",
        {
            "type": "agent.message",
            "payload": {"session_id": "s1", "content": "你好", "speak": False},
        },
    )
    assert ev is not None
    assert ev.type == AgentEventType.MESSAGE
    assert ev.content == "你好"
    assert ev.speak is False


def test_parse_shorthand() -> None:
    ev = parse_event("s1", {"type": "thinking", "content": "规划中"})
    assert ev is not None
    assert ev.type == AgentEventType.THINKING
    assert ev.content == "规划中"


def test_ndjson_stream() -> None:
    blob = "\n".join(
        [
            json.dumps({"type": "agent.message", "payload": {"content": "a", "speak": True}}),
            json.dumps({"type": "agent.done", "payload": {}}),
        ]
    )
    events = list(iter_ndjson_events("s1", blob))
    assert [e.type for e in events] == [AgentEventType.MESSAGE, AgentEventType.DONE]
    assert events[0].speak is True


def test_sse_stream() -> None:
    blob = (
        'data: {"type":"agent.message","payload":{"content":"ok","speak":true}}\n'
        "\n"
        'data: {"type":"agent.done","payload":{}}\n'
        "\n"
    )
    events = list(iter_sse_events("s1", blob))
    assert events[0].type == AgentEventType.MESSAGE
    assert events[-1].type == AgentEventType.DONE


def test_batch_json_events() -> None:
    data = {
        "protocol": PROTOCOL_VERSION,
        "events": [
            {"type": "tool_call", "tool": "x", "args": {"a": 1}},
            {"type": "message", "content": "done", "speak": True},
        ],
    }
    events = list(iter_json_body_events("s1", data))
    assert events[0].type == AgentEventType.TOOL_CALL
    assert events[0].tool == "x"
    assert events[1].type == AgentEventType.MESSAGE
    assert events[-1].type == AgentEventType.DONE


def test_legacy_text_reply() -> None:
    events = list(iter_json_body_events("s1", {"text": "hello"}))
    assert events[0].type == AgentEventType.MESSAGE
    assert events[0].content == "hello"
    assert events[0].speak is True
    assert events[1].type == AgentEventType.DONE
