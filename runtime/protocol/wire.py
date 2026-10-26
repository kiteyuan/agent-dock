"""Wire helpers — JSON encode/decode for Device Protocol frames."""

from __future__ import annotations

import json
from typing import Any

from runtime.protocol.device import DeviceMessage, DeviceMessageType


def encode_message(msg: DeviceMessage) -> str:
    return msg.model_dump_json()


def encode_dict(msg_type: str, payload: dict[str, Any] | None = None) -> str:
    import time
    import uuid

    return json.dumps(
        {
            "type": msg_type,
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "payload": payload or {},
        }
    )


def decode_message(raw: str | bytes) -> DeviceMessage:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    # Accept agent.* events that are already wire-shaped from EventBus
    mtype = data.get("type", "")
    if mtype.startswith("agent."):
        # Pass through as opaque DeviceMessage-compatible dict via ERROR? No —
        # callers that receive agent events use json.loads directly.
        # For inbound device messages only:
        pass
    try:
        data["type"] = DeviceMessageType(data["type"])
    except ValueError as exc:
        raise ValueError(f"unknown message type: {data.get('type')}") from exc
    return DeviceMessage.model_validate(data)
