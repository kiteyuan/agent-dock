"""Deferred TTS/agent defaults when a device turn is in flight."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from runtime.device.connection import DeviceConnection
from runtime.device.gateway import DeviceGateway
from runtime.session.models import Session


def _gateway(*, default_tts: str = "edge", default_agent: str = "pi") -> DeviceGateway:
    registry = SimpleNamespace(
        default_id=default_tts,
        list_dicts=lambda: [{"id": default_tts}],
        get=lambda tts_id: object() if tts_id else None,
    )
    return DeviceGateway(
        host="127.0.0.1",
        port=8765,
        sessions=SimpleNamespace(),
        auth=SimpleNamespace(),
        pipeline=SimpleNamespace(),
        registry=SimpleNamespace(),
        tts_registry=registry,
        default_agent_id=default_agent,
    )


def _conn(*, tts_id: str = "haibara", agent_id: str = "pi") -> DeviceConnection:
    conn = DeviceConnection(ws=SimpleNamespace())
    conn.device_id = "mobile-test"
    conn.session = Session(
        session_id="s1",
        device_id="mobile-test",
        tts_id=tts_id,
        agent_id=agent_id,
    )
    conn.send = AsyncMock()  # type: ignore[method-assign]
    return conn


@pytest.mark.asyncio
async def test_broadcast_tts_applies_immediately_when_idle() -> None:
    gw = _gateway(default_tts="edge")
    conn = _conn(tts_id="haibara")
    gw._connections["mobile-test"] = conn

    await gw.broadcast_defaults("tts")

    assert conn.session is not None
    assert conn.session.tts_id == "edge"
    assert conn.pending_default_kinds == set()
    assert conn.send.await_count >= 1


@pytest.mark.asyncio
async def test_broadcast_tts_defers_while_busy_then_flushes() -> None:
    gw = _gateway(default_tts="edge")
    conn = _conn(tts_id="haibara")
    loop = asyncio.get_running_loop()
    busy = loop.create_future()
    conn.turn_task = busy  # type: ignore[assignment]
    gw._connections["mobile-test"] = conn

    await gw.broadcast_defaults("tts")

    assert conn.session is not None
    assert conn.session.tts_id == "haibara"
    assert conn.pending_default_kinds == {"tts"}

    tracked = gw._track_turn(conn, busy)  # type: ignore[arg-type]
    assert tracked is busy
    busy.set_result(None)
    await asyncio.sleep(0)

    assert conn.session.tts_id == "edge"
    assert conn.pending_default_kinds == set()
    assert conn.turn_task is None


@pytest.mark.asyncio
async def test_tts_select_cancels_deferred_default() -> None:
    gw = _gateway(default_tts="edge")
    conn = _conn(tts_id="haibara")
    conn.pending_default_kinds.add("tts")
    gw._connections["mobile-test"] = conn

    # Simulate dispatch TTS_SELECT path's discard.
    conn.pending_default_kinds.discard("tts")
    conn.session.tts_id = "haibara"  # type: ignore[union-attr]
    gw._flush_pending_defaults(conn)
    assert conn.session.tts_id == "haibara"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_flush_skips_if_new_turn_already_running() -> None:
    gw = _gateway(default_tts="edge")
    conn = _conn(tts_id="haibara")
    conn.pending_default_kinds.add("tts")
    loop = asyncio.get_running_loop()
    conn.turn_task = loop.create_future()  # type: ignore[assignment]
    gw._flush_pending_defaults(conn)
    assert conn.session.tts_id == "haibara"  # type: ignore[union-attr]
    assert conn.pending_default_kinds == {"tts"}
