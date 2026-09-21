"""Shared Device Protocol helpers (rpi / cli / any Python device)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def make_msg(msg_type: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps({
        "type": msg_type,
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "payload": payload or {},
    })


def device_hello(
    device_id: str,
    device_type: str = "pi",
    token: str | None = None,
    tts_id: str | None = None,
) -> str:
    """Hello. Prefer omitting tts_id — Runtime owns TTS/pet defaults."""
    payload: dict[str, Any] = {
        "device_id": device_id,
        "device_type": device_type,
        "protocol_version": "1.0",
    }
    if token is not None:
        payload["token"] = token
    if tts_id is not None:
        payload["tts_id"] = tts_id
    return make_msg("device.hello", payload)


def user_message(
    session_id: str,
    text: str,
    agent_id: str | None = None,
    tts_id: str | None = None,
    tts_model: str | None = None,
) -> str:
    payload: dict[str, Any] = {"session_id": session_id, "text": text}
    if agent_id:
        payload["agent_id"] = agent_id
    if tts_id:
        payload["tts_id"] = tts_id
    if tts_model:
        payload["tts_model"] = tts_model
    return make_msg("user.message", payload)


def audio_start(session_id: str) -> str:
    return make_msg("audio.start", {"session_id": session_id})


def audio_end(session_id: str) -> str:
    return make_msg("audio.end", {"session_id": session_id})


def session_cancel(session_id: str) -> str:
    return make_msg("session.cancel", {"session_id": session_id})


def tts_list() -> str:
    return make_msg("tts.list")


def pets_list() -> str:
    return make_msg("pets.list")


def tts_select(session_id: str, tts_id: str, model: str | None = None) -> str:
    payload: dict[str, Any] = {"session_id": session_id, "tts_id": tts_id}
    if model:
        payload["model"] = model
    return make_msg("tts.select", payload)


def agents_list() -> str:
    return make_msg("agents.list")


def ping(ping_id: str | None = None) -> str:
    return make_msg("device.ping", {"ping_id": ping_id or uuid.uuid4().hex[:8]})


def device_status(session_id: str | None, state: str, detail: str | None = None) -> str:
    payload: dict[str, Any] = {"state": state}
    if session_id:
        payload["session_id"] = session_id
    if detail:
        payload["detail"] = detail
    return make_msg("device.status", payload)
