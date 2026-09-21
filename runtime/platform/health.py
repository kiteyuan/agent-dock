"""Background health probing with a lock-free read path for Admin requests."""

from __future__ import annotations

import json
import shutil
import socket
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from loguru import logger

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.types import HealthState, ProbeSpec


def tcp_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_target(spec: ProbeSpec) -> tuple[str, int]:
    parsed = urlparse(spec.url or "")
    host = parsed.hostname or spec.host
    if parsed.port:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = spec.port or 80
    return host, port


def _down_detail(exc: BaseException) -> str:
    text = str(getattr(exc, "reason", exc)).lower()
    if "timed out" in text or "timeout" in text:
        return "无响应"
    return "未监听"


class HealthProbe:
    def check(self, target_id: str, spec: ProbeSpec, *, root: Path) -> HealthState:
        started = time.perf_counter()
        healthy = False
        detail = ""
        data: dict[str, object] = {}
        status = "stopped"
        try:
            if spec.kind == "none":
                healthy, detail, status = True, "无需探测", "ready"
            elif spec.kind == "tcp":
                if spec.port is None:
                    raise ValueError("TCP probe requires port")
                if tcp_open(spec.host, spec.port, spec.timeout):
                    healthy, detail, status = True, "正常", "ready"
                else:
                    healthy, detail, status = False, "未监听", "stopped"
            elif spec.kind == "http":
                if not spec.url:
                    raise ValueError("HTTP probe requires url")
                host, port = _http_target(spec)
                if not tcp_open(host, port, min(spec.timeout, 0.2)):
                    healthy, detail, status = False, "未监听", "stopped"
                else:
                    req = Request(spec.url, method="GET")
                    with urlopen(req, timeout=spec.timeout) as response:
                        code = int(getattr(response, "status", 200))
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            raw = response.read(64 * 1024)
                            value = json.loads(raw)
                            if isinstance(value, dict):
                                data = value
                    healthy = 200 <= code < 500
                    detail = "正常" if healthy else f"HTTP {code}"
                    status = "ready" if healthy else "degraded"
            elif spec.kind == "file":
                if not spec.path:
                    raise ValueError("file probe requires path")
                path = Path(spec.path).expanduser()
                if not path.is_absolute():
                    path = root / path
                healthy = path.exists()
                detail = str(path)
                status = "ready" if healthy else "missing"
            elif spec.kind == "command":
                if not spec.command:
                    raise ValueError("command probe requires command")
                found = shutil.which(spec.command)
                healthy = found is not None
                detail = found or f"{spec.command} not on PATH"
                status = "ready" if healthy else "missing"
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            if spec.kind in ("tcp", "http"):
                detail = _down_detail(exc)
                status = "stopped"
            else:
                detail = str(exc)
                status = "error"
        return HealthState(
            id=target_id,
            status=status,  # type: ignore[arg-type]
            healthy=healthy,
            detail=detail,
            data=data,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )


class HealthStore:
    """Refresh probes out of band; API reads immutable copies from memory."""

    def __init__(
        self,
        catalog: ModuleCatalog,
        *,
        interval_seconds: float = 3.0,
        probe: HealthProbe | None = None,
    ) -> None:
        self.catalog = catalog
        self.interval_seconds = max(0.5, float(interval_seconds))
        self.probe = probe or HealthProbe()
        self._states: dict[str, HealthState] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.set()
        self._thread = threading.Thread(
            target=self._run,
            name="health-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def invalidate(self, target_id: str | None = None) -> None:
        if target_id:
            keys = {target_id, f"service:{target_id}", f"module:{target_id}"}
            module = self.catalog.module(target_id)
            if module and module.sidecar_id:
                keys.add(f"service:{module.sidecar_id}")
            with self._lock:
                for key in keys:
                    self._states.pop(key, None)
        self._wake.set()

    def get(self, target_id: str) -> HealthState:
        with self._lock:
            state = self._states.get(target_id)
            if state is None:
                return HealthState(id=target_id)
            return state.model_copy(deep=True)

    def snapshot(self) -> dict[str, HealthState]:
        with self._lock:
            return {
                key: value.model_copy(deep=True)
                for key, value in self._states.items()
            }

    def refresh(self, target_ids: Iterable[str] | None = None) -> None:
        wanted = set(target_ids or [])
        candidates: list[tuple[str, ProbeSpec]] = [
            (f"service:{spec.id}", spec.health)
            for spec in self.catalog.sidecars
        ]
        candidates.extend(
            (f"module:{spec.id}", spec.health)
            for spec in self.catalog.modules
            if spec.health.kind != "none"
        )
        if wanted:
            candidates = [
                item
                for item in candidates
                if item[0] in wanted or item[0].split(":", 1)[-1] in wanted
            ]
        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(candidates))),
            thread_name_prefix="health-probe",
        ) as executor:
            futures = {
                key: executor.submit(
                    self.probe.check,
                    key,
                    probe,
                    root=self.catalog.root,
                )
                for key, probe in candidates
            }
            updates = {key: future.result() for key, future in futures.items()}
        with self._lock:
            self._states.update(updates)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.interval_seconds)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.refresh()
            except Exception:  # noqa: BLE001
                logger.exception("health refresh failed")
