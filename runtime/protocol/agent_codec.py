"""Encode / decode public Agent Protocol wire formats (agentdock.agent/1.0)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterator

from runtime.protocol.agent import (
    PROTOCOL_VERSION,
    AgentEvent,
    AgentEventType,
    AgentRequest,
    agent_done,
    agent_message,
)


def request_to_http_body(request: AgentRequest, *, stream: bool = True) -> dict[str, Any]:
    """Canonical POST body Runtime sends to a public Agent."""
    body: dict[str, Any] = {
        "protocol": PROTOCOL_VERSION,
        "session_id": request.session_id,
        "text": request.text,
        "context": list(request.context),
        "device": dict(request.device or {}),
        "agent_id": request.agent_id,
        "stream": stream,
    }
    if request.workspace:
        body["workspace"] = request.workspace
    if request.instructions:
        body["instructions"] = request.instructions
    return body


def parse_event(session_id: str, item: Any) -> AgentEvent | None:
    """Parse one event object (canonical wire or shorthand). Returns None if unknown type."""
    if not isinstance(item, dict):
        return agent_message(session_id, str(item))

    mtype = item.get("type")
    if isinstance(mtype, str) and mtype.startswith("agent."):
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        return _from_parts(session_id, mtype, payload, item)

    ev_name = item.get("event") or item.get("type")
    if ev_name:
        if not str(ev_name).startswith("agent."):
            ev_name = f"agent.{ev_name}"
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item
        return _from_parts(session_id, str(ev_name), payload, item)

    content = item.get("content") or item.get("text")
    if content is not None:
        return agent_message(session_id, str(content), speak=_speak_of(item))

    return agent_message(session_id, json.dumps(item, ensure_ascii=False))


def _speak_of(obj: dict[str, Any]) -> bool:
    if "speak" in obj:
        return bool(obj["speak"])
    payload = obj.get("payload")
    if isinstance(payload, dict) and "speak" in payload:
        return bool(payload["speak"])
    return True


def _from_parts(
    session_id: str,
    mtype: str,
    payload: dict[str, Any],
    raw: dict[str, Any],
) -> AgentEvent | None:
    try:
        et = AgentEventType(mtype)
    except ValueError:
        return None

    content = payload.get("content")
    if content is None:
        content = payload.get("text")

    speak = True
    if et == AgentEventType.MESSAGE:
        speak = _speak_of(payload if "speak" in payload else raw)

    return AgentEvent(
        type=et,
        session_id=str(payload.get("session_id") or session_id),
        id=str(raw.get("id") or uuid.uuid4().hex[:12]),
        content=None if content is None else str(content),
        tool=payload.get("tool"),
        args=payload.get("args") if isinstance(payload.get("args"), dict) else None,
        status=payload.get("status"),
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        speak=speak,
    )


def iter_ndjson_events(session_id: str, text: str) -> Iterator[AgentEvent]:
    saw_terminal = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        ev = parse_event(session_id, item)
        if ev:
            yield ev
            if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                saw_terminal = True
    if not saw_terminal:
        yield agent_done(session_id)


def iter_sse_events(session_id: str, text: str) -> Iterator[AgentEvent]:
    """Parse a complete SSE buffer into events."""
    saw_terminal = False
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        if line == "":
            if data_lines:
                blob = "\n".join(data_lines)
                data_lines = []
                if not blob.strip():
                    continue
                item = json.loads(blob)
                ev = parse_event(session_id, item)
                if ev:
                    yield ev
                    if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                        saw_terminal = True
            continue
    if data_lines:
        item = json.loads("\n".join(data_lines))
        ev = parse_event(session_id, item)
        if ev:
            yield ev
            if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                saw_terminal = True
    if not saw_terminal:
        yield agent_done(session_id)


def iter_json_body_events(session_id: str, data: Any) -> Iterator[AgentEvent]:
    if isinstance(data, str):
        yield agent_message(session_id, data)
        yield agent_done(session_id)
        return

    if not isinstance(data, dict):
        yield agent_message(session_id, str(data))
        yield agent_done(session_id)
        return

    events = data.get("events")
    if isinstance(events, list):
        saw_terminal = False
        for item in events:
            ev = parse_event(session_id, item)
            if ev:
                yield ev
                if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                    saw_terminal = True
        if not saw_terminal:
            yield agent_done(session_id)
        return

    text = data.get("text") or data.get("reply") or data.get("content")
    if text is None:
        text = json.dumps(data, ensure_ascii=False)
    speak = bool(data["speak"]) if "speak" in data else True
    yield agent_message(session_id, str(text), speak=speak)
    yield agent_done(session_id)


def parse_sse_data_line(session_id: str, data_payload: str) -> AgentEvent | None:
    data_payload = data_payload.strip()
    if not data_payload:
        return None
    return parse_event(session_id, json.loads(data_payload))
