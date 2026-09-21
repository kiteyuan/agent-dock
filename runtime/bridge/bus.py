"""Event bus — push AgentEvents to a Device connection sender."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import websockets

from runtime.protocol.agent import AgentEvent

SendFn = Callable[[str | bytes], Awaitable[None]]


def client_disconnected(exc: BaseException) -> bool:
    """Peer already gone. Callers must not dump this on the event loop."""
    if isinstance(
        exc,
        (
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
            TimeoutError,
            asyncio.TimeoutError,
        ),
    ):
        return True
    return isinstance(exc, websockets.ConnectionClosed)


class EventBus:
    """Forwards agent events to the connected device as wire JSON."""

    def __init__(self, send: SendFn) -> None:
        self._send = send

    async def publish(self, event: AgentEvent) -> None:
        await self._send(json.dumps(event.to_wire()))
