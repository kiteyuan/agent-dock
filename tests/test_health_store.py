from __future__ import annotations

import socket
import time
from pathlib import Path

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.health import HealthProbe, HealthStore
from runtime.platform.types import HealthState, ProbeSpec


class FakeProbe:
    def __init__(self) -> None:
        self.calls = 0

    def check(self, target_id, spec, *, root):
        self.calls += 1
        return HealthState(id=target_id, status="ready", healthy=True)


def test_snapshot_reads_cache_without_probing() -> None:
    probe = FakeProbe()
    store = HealthStore(ModuleCatalog.load({}), probe=probe)
    store.refresh(["runtime"])
    calls = probe.calls
    assert store.get("service:runtime").healthy
    assert store.snapshot()["service:runtime"].healthy
    assert probe.calls == calls


def test_invalidate_only_removes_requested_item() -> None:
    probe = FakeProbe()
    store = HealthStore(ModuleCatalog.load({}), probe=probe)
    store.refresh(["runtime", "admin"])
    store.invalidate("service:runtime")
    assert store.get("service:runtime").status == "unknown"
    assert store.get("service:admin").healthy


def test_http_probe_does_not_wait_on_closed_port() -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    spec = ProbeSpec(kind="http", url=f"http://127.0.0.1:{port}/v1/agent", timeout=2)
    started = time.perf_counter()
    state = HealthProbe().check("service:closed", spec, root=Path("."))
    assert state.healthy is False
    assert state.detail == "未监听"
    assert "<" not in state.detail
    assert time.perf_counter() - started < 1.0
