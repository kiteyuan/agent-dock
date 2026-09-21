"""Device Protocol — messages between Device and Runtime."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceMessageType(str, Enum):
    # Device -> Runtime
    DEVICE_HELLO = "device.hello"
    USER_MESSAGE = "user.message"
    AUDIO_START = "audio.start"
    # Deprecated: audio frames are raw WebSocket binary between audio.start/end.
    AUDIO_CHUNK = "audio.chunk"
    AUDIO_END = "audio.end"
    SESSION_CANCEL = "session.cancel"
    DEVICE_STATUS = "device.status"  # reserved; Runtime does not emit/consume
    AGENTS_LIST = "agents.list"
    TTS_LIST = "tts.list"
    TTS_SELECT = "tts.select"
    PETS_LIST = "pets.list"
    PING = "device.ping"

    # Runtime -> Device
    SESSION_ACCEPT = "session.accept"
    AGENTS_LIST_RESULT = "agents.list.result"
    TTS_LIST_RESULT = "tts.list.result"
    TTS_SELECTED = "tts.selected"
    PETS_LIST_RESULT = "pets.list.result"
    PONG = "device.pong"
    STT_PARTIAL = "stt.partial"  # reserved; Runtime emits stt.final only
    STT_FINAL = "stt.final"
    TTS_START = "tts.start"
    # Deprecated: TTS payload is raw WebSocket binary between tts.start/end.
    TTS_AUDIO = "tts.audio"
    TTS_END = "tts.end"
    ERROR = "error"
    # Agent events (agent.*) are published via AgentEvent.to_wire(), not this enum.


class DeviceMessage(BaseModel):
    type: DeviceMessageType
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)


def device_hello(
    device_id: str,
    device_type: str = "unknown",
    token: str | None = None,
    tts_id: str | None = None,
) -> DeviceMessage:
    payload: dict[str, Any] = {
        "device_id": device_id,
        "device_type": device_type,
        "protocol_version": "1.0",
    }
    if token is not None:
        payload["token"] = token
    if tts_id is not None:
        payload["tts_id"] = tts_id
    return DeviceMessage(type=DeviceMessageType.DEVICE_HELLO, payload=payload)


def user_message(
    session_id: str,
    text: str,
    agent_id: str | None = None,
    tts_id: str | None = None,
    tts_model: str | None = None,
) -> DeviceMessage:
    payload: dict[str, Any] = {"session_id": session_id, "text": text}
    if agent_id:
        payload["agent_id"] = agent_id
    if tts_id:
        payload["tts_id"] = tts_id
    if tts_model:
        payload["tts_model"] = tts_model
    return DeviceMessage(type=DeviceMessageType.USER_MESSAGE, payload=payload)


def session_accept(
    session_id: str,
    device_id: str,
    *,
    advertise_url: str | None = None,
    tts_id: str | None = None,
    pet_id: str | None = None,
    agent_id: str | None = None,
    assets_port: int | None = None,
    assets_base_url: str | None = None,
) -> DeviceMessage:
    """Runtime-owned session defaults — clients are shells and should not configure these."""
    payload: dict[str, Any] = {"session_id": session_id, "device_id": device_id}
    if advertise_url:
        payload["advertise_url"] = advertise_url
    if tts_id:
        payload["tts_id"] = tts_id
    if pet_id:
        payload["pet_id"] = pet_id
    if agent_id:
        payload["agent_id"] = agent_id
    if assets_port is not None:
        payload["assets_port"] = int(assets_port)
    if assets_base_url:
        payload["assets_base_url"] = assets_base_url
    return DeviceMessage(type=DeviceMessageType.SESSION_ACCEPT, payload=payload)


def agents_list_result(agents: list[dict[str, Any]]) -> DeviceMessage:
    return DeviceMessage(type=DeviceMessageType.AGENTS_LIST_RESULT, payload={"agents": agents})


def tts_list_result(providers: list[dict[str, Any]], default_id: str | None = None) -> DeviceMessage:
    return DeviceMessage(
        type=DeviceMessageType.TTS_LIST_RESULT,
        payload={"providers": providers, "default": default_id},
    )


def tts_selected(session_id: str, tts_id: str, model: str | None = None) -> DeviceMessage:
    payload: dict[str, Any] = {"session_id": session_id, "tts_id": tts_id}
    if model:
        payload["model"] = model
    return DeviceMessage(type=DeviceMessageType.TTS_SELECTED, payload=payload)


def pets_list_result(
    pets: list[dict[str, Any]],
    *,
    default_id: str | None = None,
    base_url: str | None = None,
    assets_port: int | None = None,
) -> DeviceMessage:
    payload: dict[str, Any] = {"pets": pets, "default": default_id}
    if base_url:
        payload["base_url"] = base_url
    if assets_port is not None:
        payload["assets_port"] = int(assets_port)
    return DeviceMessage(type=DeviceMessageType.PETS_LIST_RESULT, payload=payload)


def pong(ping_id: str | None = None) -> DeviceMessage:
    return DeviceMessage(type=DeviceMessageType.PONG, payload={"ping_id": ping_id})


def stt_final(session_id: str, text: str) -> DeviceMessage:
    return DeviceMessage(type=DeviceMessageType.STT_FINAL, payload={"session_id": session_id, "text": text})


def tts_start(
    session_id: str,
    tts_id: str | None = None,
    format: str | None = None,
    text: str | None = None,
) -> DeviceMessage:
    payload: dict[str, Any] = {"session_id": session_id}
    if tts_id:
        payload["tts_id"] = tts_id
    if format:
        payload["format"] = format
    if text:
        payload["text"] = text
    return DeviceMessage(type=DeviceMessageType.TTS_START, payload=payload)


def tts_end(session_id: str) -> DeviceMessage:
    return DeviceMessage(type=DeviceMessageType.TTS_END, payload={"session_id": session_id})


def error_msg(detail: str, session_id: str | None = None) -> DeviceMessage:
    return DeviceMessage(type=DeviceMessageType.ERROR, payload={"detail": detail, "session_id": session_id})
