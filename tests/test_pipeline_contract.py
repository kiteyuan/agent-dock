"""Pipeline turn contract: context, terminal events, TTS model sticky clear."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from runtime.agent.base import AgentAdapter
from runtime.agent.registry import AgentRegistry
from runtime.agent.router import AgentRouter
from runtime.bridge.bus import EventBus
from runtime.bridge.pipeline import BridgePipeline
from runtime.protocol.agent import AgentEvent, AgentEventType, AgentInfo, AgentRequest
from runtime.session.models import Session
from runtime.transport.speech.registry import TTSRegistry


class _ScriptedAgent(AgentAdapter):
    def __init__(self, events: list[AgentEvent]) -> None:
        self._info = AgentInfo(id="mock", name="Mock")
        self._events = events
        self.last_request: AgentRequest | None = None

    @property
    def info(self) -> AgentInfo:
        return self._info

    async def run(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        self.last_request = request
        for event in self._events:
            yield event


class _CollectBus:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def send(self, data: str | bytes) -> None:
        self.messages.append(data)


def _pipeline(agent: AgentAdapter) -> BridgePipeline:
    registry = AgentRegistry()
    registry.register(agent)
    router = AgentRouter(registry, default_agent_id=agent.info.id)
    return BridgePipeline(router, tts_registry=TTSRegistry())


def test_run_turn_excludes_current_user_from_context() -> None:
    agent = _ScriptedAgent(
        [
            AgentEvent(
                type=AgentEventType.MESSAGE, session_id="s", content="hi", speak=False
            ),
            AgentEvent(type=AgentEventType.DONE, session_id="s"),
        ]
    )
    pipeline = _pipeline(agent)
    session = Session(session_id="s", device_id="d")
    session.add_turn("user", "earlier")
    bus = EventBus(_CollectBus().send)

    asyncio.run(pipeline.run_turn(session, "current", bus))

    assert agent.last_request is not None
    assert agent.last_request.text == "current"
    assert [item["text"] for item in agent.last_request.context] == ["earlier"]
    assert [item["text"] for item in session.context] == ["earlier", "current", "hi"]


def test_run_turn_emits_error_when_agent_omits_terminal() -> None:
    agent = _ScriptedAgent(
        [
            AgentEvent(
                type=AgentEventType.MESSAGE,
                session_id="s",
                content="partial",
                speak=False,
            ),
        ]
    )
    pipeline = _pipeline(agent)
    session = Session(session_id="s", device_id="d")
    collector = _CollectBus()
    bus = EventBus(collector.send)

    asyncio.run(pipeline.run_turn(session, "go", bus))

    types = []
    for item in collector.messages:
        if isinstance(item, str):
            types.append(json.loads(item).get("type"))
    assert "agent.error" in types


def test_run_turn_persists_completed_transcript(tmp_path) -> None:
    from runtime.session.transcript import TranscriptStore

    agent = _ScriptedAgent(
        [
            AgentEvent(
                type=AgentEventType.MESSAGE, session_id="s", content="答", speak=False
            ),
            AgentEvent(type=AgentEventType.DONE, session_id="s"),
        ]
    )
    store = TranscriptStore(tmp_path)
    registry = AgentRegistry()
    registry.register(agent)
    router = AgentRouter(registry, default_agent_id=agent.info.id)
    pipeline = BridgePipeline(router, tts_registry=TTSRegistry(), transcript=store)
    session = Session(session_id="s", device_id="dev-x")
    bus = EventBus(_CollectBus().send)

    asyncio.run(pipeline.run_turn(session, "问", bus))

    msgs = store.load("dev-x")
    assert [m["text"] for m in msgs] == ["问", "答"]


def test_run_turn_skips_persist_on_cancel(tmp_path) -> None:
    from runtime.session.transcript import TranscriptStore

    agent = _ScriptedAgent(
        [
            AgentEvent(
                type=AgentEventType.MESSAGE, session_id="s", content="半截", speak=False
            ),
            AgentEvent(type=AgentEventType.CANCEL, session_id="s"),
        ]
    )
    store = TranscriptStore(tmp_path)
    registry = AgentRegistry()
    registry.register(agent)
    router = AgentRouter(registry, default_agent_id=agent.info.id)
    pipeline = BridgePipeline(router, tts_registry=TTSRegistry(), transcript=store)
    session = Session(session_id="s", device_id="dev-y")
    bus = EventBus(_CollectBus().send)

    asyncio.run(pipeline.run_turn(session, "问", bus))

    assert store.load("dev-y") == []


def test_tts_model_clears_when_provider_changes() -> None:
    pipeline = _pipeline(
        _ScriptedAgent([AgentEvent(type=AgentEventType.DONE, session_id="s")])
    )
    session = Session(session_id="s", device_id="d", tts_id="edge", tts_model="zh-CN-X")
    pipeline._apply_tts_selection(session, tts_id="Haibara", tts_model=None)
    assert session.tts_id == "Haibara"
    assert session.tts_model is None
