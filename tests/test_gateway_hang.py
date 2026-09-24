"""Device gateway cancel / close budgets (anti-hang)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from runtime.device.connection import DeviceConnection
from runtime.device.gateway import (
    DeviceGateway,
    _TURN_CANCEL_TIMEOUT_S,
)
from runtime.session.models import Session


def _gateway() -> DeviceGateway:
    return DeviceGateway(
        host="127.0.0.1",
        port=8765,
        sessions=SimpleNamespace(),
        auth=SimpleNamespace(),
        pipeline=SimpleNamespace(),
        registry=SimpleNamespace(),
        tts_registry=SimpleNamespace(default_id="edge", list_dicts=lambda: [], get=lambda _: None),
    )


@pytest.mark.asyncio
async def test_await_cancelled_detaches_uncancellable_work() -> None:
    """Cancel budget must return even if the task ignores CancelledError (to_thread)."""
    gate = asyncio.Event()
    release = asyncio.Event()

    async def _slow() -> None:
        try:
            await gate.wait()
        except asyncio.CancelledError:
            await release.wait()

    task = asyncio.create_task(_slow())
    await asyncio.sleep(0)
    t0 = time.perf_counter()
    await DeviceGateway._await_cancelled(task, label="slow")
    elapsed = time.perf_counter() - t0
    assert elapsed < _TURN_CANCEL_TIMEOUT_S + 1.0
    assert not task.done()
    release.set()
    await asyncio.wait({task}, timeout=1.0)
    assert task.done()


@pytest.mark.asyncio
async def test_replace_turn_keeps_cancel_event_set() -> None:
    session = Session(session_id="s1", device_id="d1")
    assert not session.cancel_event.is_set()

    async def _hang() -> None:
        await asyncio.sleep(30)

    task = asyncio.create_task(_hang())
    await DeviceGateway._replace_turn(session, task)
    assert session.cancel_event.is_set()
    done, _ = await asyncio.wait({task}, timeout=0.5)
    assert task in done


@pytest.mark.asyncio
async def test_force_close_aborts_when_close_hangs() -> None:
    aborted = {"n": 0}

    class FakeWs:
        def __init__(self) -> None:
            self.transport = SimpleNamespace(
                abort=lambda: aborted.__setitem__("n", aborted["n"] + 1)
            )

        async def close(self) -> None:
            await asyncio.sleep(30)

    ws = FakeWs()
    t0 = time.perf_counter()
    await DeviceGateway._force_close(ws)  # type: ignore[arg-type]
    assert time.perf_counter() - t0 < 3.5
    assert aborted["n"] == 1


@pytest.mark.asyncio
async def test_stop_turn_clears_task_ref_even_if_slow() -> None:
    gw = _gateway()
    conn = DeviceConnection(ws=SimpleNamespace())
    gate = asyncio.Event()
    release = asyncio.Event()

    async def _slow() -> None:
        try:
            await gate.wait()
        except asyncio.CancelledError:
            await release.wait()

    conn.turn_task = asyncio.create_task(_slow())
    await asyncio.sleep(0)
    orphan = conn.turn_task
    await gw._stop_turn(conn)
    assert conn.turn_task is None
    assert not orphan.done()
    release.set()
    await asyncio.wait({orphan}, timeout=1.0)
