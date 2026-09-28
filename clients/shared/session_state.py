"""Client-side session states shared across Device terminals."""

from __future__ import annotations

from enum import Enum


class ClientState(str, Enum):
    OFFLINE = "offline"
    CONNECTING = "connecting"
    IDLE = "idle"
    LISTENING = "listening"
    BUSY = "busy"
    SPEAKING = "speaking"
    ERROR = "error"


# Events that typically move idle/listening → busy (turn in progress).
BUSY_EVENTS = frozenset({
    "stt.partial",
    "stt.final",
    "agent.thinking",
    "agent.tool_call",
    "agent.tool_result",
    "agent.message",
})

# Talk / mic: idle+listening start/stop STT; busy/speaking/error also accept
# a tap to cancel / barge-in (aligned with STATE_MACHINE.md + Web/Mobile).
CAN_TOGGLE_TALK = frozenset({
    ClientState.IDLE,
    ClientState.LISTENING,
    ClientState.BUSY,
    ClientState.SPEAKING,
    ClientState.ERROR,
})
