"""Per-connection device state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import asyncio
import time

import websockets

from runtime.session.models import Session

# Half-closed / stalled mobile clients must not wedge the Runtime event loop.
_WS_SEND_TIMEOUT_S = 15.0


@dataclass
class DeviceConnection:
    ws: websockets.WebSocketServerProtocol
    device_id: str | None = None
    device_type: str = "unknown"
    session: Session | None = None
    audio_buf: bytearray = field(default_factory=bytearray)
    audio_overflow: bool = False
    recording: bool = False
    turn_task: asyncio.Task | None = None
    connected_at: float = field(default_factory=time.time)

    async def send(self, data: str | bytes) -> None:
        await asyncio.wait_for(self.ws.send(data), timeout=_WS_SEND_TIMEOUT_S)

    async def send_json(self, obj: dict[str, Any]) -> None:
        import json

        await self.send(json.dumps(obj))

    def snapshot(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "session_id": self.session.session_id if self.session else None,
            "agent_id": self.session.agent_id if self.session else None,
            "tts_id": self.session.tts_id if self.session else None,
            "connected_at": self.connected_at,
            "busy": bool(self.turn_task and not self.turn_task.done()),
            "recording": self.recording,
        }
