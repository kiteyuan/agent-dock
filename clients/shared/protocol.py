"""Shared Device Protocol helpers (cli / any Python device)."""

from __future__ import annotations

import importlib.util
import json
import time
import uuid
from pathlib import Path
from typing import Any


def _load_gen():
    path = Path(__file__).resolve().with_name("protocol_gen.py")
    spec = importlib.util.spec_from_file_location("clients_shared_protocol_gen", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gen = _load_gen()
Msg = _gen.Msg
AgentEvt = _gen.AgentEvt
PROTOCOL_VERSION = _gen.PROTOCOL_VERSION


def make_msg(msg_type: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {
            "type": msg_type,
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "payload": payload or {},
        }
    )


def device_hello(
    device_id: str,
    device_type: str = "device",
    token: str | None = None,
    tts_id: str | None = None,
) -> str:
    """Hello. Prefer omitting tts_id — Runtime owns TTS/pet defaults."""
    payload: dict[str, Any] = {
        "device_id": device_id,
        "device_type": device_type,
        "protocol_version": PROTOCOL_VERSION,
    }
    if token is not None:
        payload["token"] = token
    if tts_id is not None:
        payload["tts_id"] = tts_id
    return make_msg(Msg.DEVICE_HELLO, payload)


def user_message(
    session_id: str,
    text: str,
    agent_id: str | None = None,
    tts_id: str | None = None,
    tts_model: str | None = None,
    images: list[dict[str, Any]] | None = None,
) -> str:
    payload: dict[str, Any] = {"session_id": session_id, "text": text}
    if agent_id:
        payload["agent_id"] = agent_id
    if tts_id:
        payload["tts_id"] = tts_id
    if tts_model:
        payload["tts_model"] = tts_model
    if images:
        payload["images"] = list(images)
    return make_msg(Msg.USER_MESSAGE, payload)


def audio_start(session_id: str) -> str:
    return make_msg(Msg.AUDIO_START, {"session_id": session_id})


def audio_end(session_id: str) -> str:
    return make_msg(Msg.AUDIO_END, {"session_id": session_id})


def session_cancel(session_id: str) -> str:
    return make_msg(Msg.SESSION_CANCEL, {"session_id": session_id})


def session_reset(session_id: str | None = None) -> str:
    payload: dict[str, Any] = {}
    if session_id:
        payload["session_id"] = session_id
    return make_msg(Msg.SESSION_RESET, payload)


def tts_list() -> str:
    return make_msg(Msg.TTS_LIST)


def pets_list() -> str:
    return make_msg(Msg.PETS_LIST)


def tts_select(session_id: str, tts_id: str, model: str | None = None) -> str:
    payload: dict[str, Any] = {"session_id": session_id, "tts_id": tts_id}
    if model:
        payload["model"] = model
    return make_msg(Msg.TTS_SELECT, payload)


def agents_list() -> str:
    return make_msg(Msg.AGENTS_LIST)


def ping(ping_id: str | None = None) -> str:
    return make_msg(Msg.PING, {"ping_id": ping_id or uuid.uuid4().hex[:8]})


def device_status(session_id: str | None, state: str, detail: str | None = None) -> str:
    payload: dict[str, Any] = {"state": state}
    if session_id:
        payload["session_id"] = session_id
    if detail:
        payload["detail"] = detail
    return make_msg(Msg.DEVICE_STATUS, payload)
