"""Agent Protocol — event stream between Runtime and Agents / Devices."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

# Public HTTP Agent Protocol version (see docs/AGENT_PROTOCOL.md)
PROTOCOL_VERSION = "agentdock.agent/1.0"


class AgentEventType(str, Enum):
    START = "agent.start"
    THINKING = "agent.thinking"
    TOOL_CALL = "agent.tool_call"
    TOOL_RESULT = "agent.tool_result"
    MESSAGE = "agent.message"
    DONE = "agent.done"
    CANCEL = "agent.cancel"
    ERROR = "agent.error"


class AgentEvent(BaseModel):
    type: AgentEventType
    session_id: str
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: float = Field(default_factory=time.time)
    content: str | None = None
    tool: str | None = None
    args: dict[str, Any] | None = None
    status: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    # Dual-channel: speak=True → Runtime may TTS; False → terminal text only
    speak: bool = True

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"session_id": self.session_id}
        if self.content is not None:
            payload["content"] = self.content
            payload["text"] = self.content
        if self.tool is not None:
            payload["tool"] = self.tool
        if self.args is not None:
            payload["args"] = self.args
        if self.status is not None:
            payload["status"] = self.status
        if self.data:
            payload["data"] = self.data
        if self.type == AgentEventType.MESSAGE:
            payload["speak"] = self.speak
        return {
            "type": self.type.value,
            "id": self.id,
            "ts": self.ts,
            "payload": payload,
        }


class AgentRequest(BaseModel):
    session_id: str
    text: str
    context: list[dict[str, Any]] = Field(default_factory=list)
    device: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    # Absolute workspace path for tools/files (shared across agents)
    workspace: str | None = None
    # Runtime capability brief — gateways should append to system / voice prompt
    instructions: str | None = None
    cancel_event: Any = None

    model_config = {"arbitrary_types_allowed": True}


class AgentInfo(BaseModel):
    id: str
    name: str
    capabilities: list[str] = Field(default_factory=list)
    description: str = ""


def agent_start(session_id: str) -> AgentEvent:
    return AgentEvent(type=AgentEventType.START, session_id=session_id)


def agent_thinking(session_id: str, content: str) -> AgentEvent:
    return AgentEvent(type=AgentEventType.THINKING, session_id=session_id, content=content)


def agent_tool_call(session_id: str, tool: str, args: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(type=AgentEventType.TOOL_CALL, session_id=session_id, tool=tool, args=args or {})


def agent_tool_result(
    session_id: str,
    tool: str,
    status: str = "success",
    content: str | None = None,
    data: dict[str, Any] | None = None,
) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.TOOL_RESULT,
        session_id=session_id,
        tool=tool,
        status=status,
        content=content,
        data=data or {},
    )


def agent_message(session_id: str, content: str, *, speak: bool = True) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.MESSAGE,
        session_id=session_id,
        content=content,
        speak=speak,
    )


def agent_done(session_id: str) -> AgentEvent:
    return AgentEvent(type=AgentEventType.DONE, session_id=session_id)


def agent_cancel(session_id: str, content: str | None = None) -> AgentEvent:
    return AgentEvent(type=AgentEventType.CANCEL, session_id=session_id, content=content)


def agent_error(session_id: str, content: str) -> AgentEvent:
    return AgentEvent(type=AgentEventType.ERROR, session_id=session_id, content=content)


AgentEventStream = AsyncIterator[AgentEvent]
