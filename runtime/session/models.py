"""Session models — conversation state and cancel tokens."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    session_id: str
    device_id: str
    device_type: str = "unknown"
    agent_id: str | None = None
    tts_id: str | None = None
    tts_model: str | None = None
    created_at: float = field(default_factory=time.time)
    context: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    turn_generation: int = 0
    # Keep last N turns (user+assistant pairs roughly); 0 = unlimited
    max_context: int = 40

    def add_turn(self, role: str, text: str) -> None:
        self.context.append({"role": role, "text": text, "ts": time.time()})
        if self.max_context > 0 and len(self.context) > self.max_context:
            self.context = self.context[-self.max_context :]

    def clear_context(self) -> None:
        self.context.clear()

    def begin_turn(self) -> tuple[int, asyncio.Event]:
        """Start a new turn with an isolated cancel token.

        Returns ``(generation, cancel_event)``. Orphaned previous turns must only
        signal cancel via ``request_cancel(generation=…)`` so they cannot poison
        the active turn's event after a timed-out detach.
        """
        self.turn_generation += 1
        self.cancel_event = asyncio.Event()
        return self.turn_generation, self.cancel_event

    def request_cancel(self, generation: int | None = None) -> None:
        """Cancel the current turn, or only if ``generation`` still matches."""
        if generation is None or generation == self.turn_generation:
            self.cancel_event.set()

    def reset_cancel(self) -> int:
        """Begin a turn and return its generation (pipeline entry helper)."""
        generation, _event = self.begin_turn()
        return generation

    def device_info(self) -> dict[str, Any]:
        return {"id": self.device_id, "type": self.device_type}
