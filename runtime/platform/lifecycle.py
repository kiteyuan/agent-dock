"""Unified non-blocking module lifecycle operations."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from runtime.pets.installer import PetInstaller
from runtime.platform.catalog import ModuleCatalog
from runtime.platform.health import HealthStore
from runtime.platform.installer import InstallManager
from runtime.platform.presence import agent_installed
from runtime.platform.types import ActionResult, JobState
from runtime.services.supervisor import ServiceSupervisor


class ModuleLifecycle:
    def __init__(
        self,
        *,
        catalog: ModuleCatalog,
        supervisor: ServiceSupervisor,
        health: HealthStore,
        pet_installer: PetInstaller,
        installer: InstallManager | None = None,
        asset_invalidate: Callable[[], None] | None = None,
        receipt_lookup: Callable[[str], bool] | None = None,
    ) -> None:
        self.catalog = catalog
        self.supervisor = supervisor
        self.health = health
        self.pet_installer = pet_installer
        self.installer = installer
        self.asset_invalidate = asset_invalidate or (lambda: None)
        self.receipt_lookup = receipt_lookup or (lambda _module_id: False)
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="module-action",
        )
        self._jobs: dict[str, JobState] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._target_jobs: dict[str, str] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            for event in self._cancellations.values():
                event.set()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def submit(
        self,
        action: str,
        target: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> ActionResult:
        handler = self._handler(action)
        if handler is None:
            return ActionResult(
                ok=False,
                action=action,
                target=target,
                error=f"unsupported action: {action}",
            )
        job_id = uuid.uuid4().hex[:12]
        job = JobState(id=job_id, action=action, target=target)
        with self._lock:
            active = self._target_jobs.get(target)
            if active:
                existing = self._jobs.get(active)
                if existing is not None and existing.state in ("queued", "running"):
                    return ActionResult(
                        ok=False,
                        action=action,
                        target=target,
                        error=f"{target} already has an active job ({active})",
                    )
            self._jobs[job_id] = job
            self._cancellations[job_id] = threading.Event()
            self._target_jobs[target] = job_id
        self._executor.submit(self._run_job, job_id, handler, target, options or {})
        return ActionResult(
            ok=True,
            action=action,
            target=target,
            job_id=job_id,
            detail="queued",
        )

    def job(self, job_id: str) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def jobs(self, *, limit: int = 20) -> list[JobState]:
        with self._lock:
            values = list(self._jobs.values())[-limit:]
            return [item.model_copy(deep=True) for item in values]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancellations.get(job_id)
            if not job or not event or job.state in ("done", "error", "cancelled"):
                return False
            job.cancel_requested = True
            job.message = "cancelling"
            event.set()
            return True

    def _handler(
        self, action: str
    ) -> Callable[[str, dict[str, Any]], ActionResult] | None:
        return {
            "prepare": self._prepare,
            "start": self._start,
            "stop": self._stop,
            "uninstall": self._uninstall,
            "import_pet": self._import_pet,
        }.get(action)

    def _run_job(
        self,
        job_id: str,
        handler: Callable[[str, dict[str, Any]], ActionResult],
        target: str,
        options: dict[str, Any],
    ) -> None:
        with self._lock:
            self._jobs[job_id].state = "running"
            cancel = self._cancellations[job_id]
        options = {
            **options,
            "_cancel": cancel,
            "_progress": lambda value, message: self._set_progress(
                job_id, value, message
            ),
        }
        try:
            result = handler(target, options)
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(
                ok=False,
                action=self._jobs[job_id].action,
                target=target,
                error=str(exc),
            )
        with self._lock:
            job = self._jobs[job_id]
            job.result = result
            job.state = (
                "cancelled"
                if job.cancel_requested and not result.ok
                else ("done" if result.ok else "error")
            )
            job.completed_at = time.time()
            job.progress = 1 if result.ok else job.progress
            job.message = result.detail or result.error or job.message
            self._cancellations.pop(job_id, None)
            if self._target_jobs.get(target) == job_id:
                self._target_jobs.pop(target, None)
            if len(self._jobs) > 100:
                completed = [
                    key
                    for key, value in self._jobs.items()
                    if value.state in ("done", "error", "cancelled") and key != job_id
                ]
                for key in completed[: len(self._jobs) - 100]:
                    self._jobs.pop(key, None)
        self.health.invalidate(target)

    def _set_progress(self, job_id: str, value: float, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = max(0, min(1, float(value)))
                job.message = str(message)

    def _prepare(self, target: str, options: dict[str, Any]) -> ActionResult:
        spec = self.catalog.module(target)
        if spec is None:
            return self._result(False, "prepare", target, error="unknown module")
        if spec.kind == "agent":
            return self._result(
                False,
                "prepare",
                target,
                error="official CLI is not installed",
                hint=spec.homepage or "Install the official CLI, then refresh Admin",
            )
        if self.installer is not None:
            self.installer.check_allowed(target)
        if spec.install.kind == "steps":
            if self.installer is None:
                return self._result(
                    False, "prepare", target, error="isolated installer unavailable"
                )
            receipt = self.installer.install(
                target,
                cancel=options.get("_cancel"),
                progress=options.get("_progress"),
                force=bool(options.get("force")),
            )
            return self._result(
                True,
                "prepare",
                target,
                detail=f"installed {receipt.get('version') or target}",
            )
        if spec.install.kind == "none":
            command = spec.health.command if spec.health.kind == "command" else None
            if command and not shutil.which(command):
                return self._result(
                    False,
                    "prepare",
                    target,
                    error=f"{command} not found on PATH",
                    hint=f"Install and authenticate the {spec.name} CLI",
                )
            return self._result(True, "prepare", target, detail="already prepared")
        if spec.install.kind == "npm":
            if not spec.install.cwd:
                return self._result(
                    False, "prepare", target, error="npm install cwd missing"
                )
            cwd = self.catalog.root / spec.install.cwd
            if not cwd.is_dir():
                return self._result(
                    False, "prepare", target, error=f"missing directory: {cwd}"
                )
            if (cwd / "node_modules").is_dir() and not options.get("force"):
                return self._result(
                    True, "prepare", target, detail="node_modules already present"
                )
            npm = shutil.which("npm")
            if not npm:
                return self._result(
                    False,
                    "prepare",
                    target,
                    error="npm not found on PATH",
                    hint="Install Node.js LTS",
                )
            process = subprocess.run(
                [npm, "install"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                return self._result(
                    False,
                    "prepare",
                    target,
                    error=(process.stderr or process.stdout or "npm install failed")[
                        -1000:
                    ],
                )
            return self._result(True, "prepare", target, detail="npm install done")
        return self._result(
            False, "prepare", target, error=f"unsupported installer: {spec.install.kind}"
        )

    def _start(self, target: str, options: dict[str, Any]) -> ActionResult:
        spec = self.catalog.module(target)
        sidecar_id = spec.sidecar_id if spec else target
        if spec and spec.kind == "agent":
            workspace = getattr(self.supervisor, "workspace", None)
            installed, detail = agent_installed(
                spec,
                root=self.catalog.root,
                workspace=workspace,
                has_receipt=self.receipt_lookup(spec.id),
            )
            if not installed:
                return self._result(
                    False,
                    "start",
                    target,
                    error=detail,
                    hint=spec.homepage or "Install the official CLI, then refresh Admin",
                )
        if spec and spec.kind != "agent" and spec.install.kind != "none":
            prepared = self._prepare(target, options)
            if not prepared.ok:
                return ActionResult(
                    **prepared.model_dump(exclude={"action"}),
                    action="start",
                )
        if not sidecar_id:
            return self._result(False, "start", target, error="module has no sidecar")
        raw = self.supervisor.start(sidecar_id)
        return self._result(
            bool(raw.get("ok")),
            "start",
            target,
            detail=raw.get("note") or (
                f"pid={raw.get('pid')}" if raw.get("pid") else "started"
            ),
            error=raw.get("error"),
        )

    def _stop(self, target: str, options: dict[str, Any]) -> ActionResult:
        spec = self.catalog.module(target)
        sidecar_id = spec.sidecar_id if spec else target
        if not sidecar_id:
            return self._result(False, "stop", target, error="module has no sidecar")
        raw = self.supervisor.stop(sidecar_id)
        return self._result(
            bool(raw.get("ok")),
            "stop",
            target,
            detail=raw.get("note") or "stopped",
            error=raw.get("error"),
        )

    def _uninstall(self, target: str, options: dict[str, Any]) -> ActionResult:
        if self.installer is None:
            return self._result(
                False, "uninstall", target, error="isolated installer unavailable"
            )
        spec = self.catalog.module(target)
        if spec and spec.sidecar_id:
            stopped = self.supervisor.stop(spec.sidecar_id)
            if not stopped.get("ok"):
                return self._result(
                    False,
                    "uninstall",
                    target,
                    error=stopped.get("error") or "failed to stop sidecar",
                )
        self.installer.uninstall(target)
        return self._result(True, "uninstall", target, detail="uninstalled")

    def _import_pet(self, target: str, options: dict[str, Any]) -> ActionResult:
        url = str(options.get("url") or "").strip()
        label = str(options.get("label") or target).strip()
        if not target or not url:
            return self._result(
                False, "import_pet", target, error="pet id and url are required"
            )
        path = self.pet_installer.install(pet_id=target, url=url, label=label)
        self.asset_invalidate()
        return self._result(
            True,
            "import_pet",
            target,
            detail=f"installed at {path}",
        )

    @staticmethod
    def _result(
        ok: bool,
        action: str,
        target: str,
        *,
        detail: str | None = None,
        error: str | None = None,
        hint: str | None = None,
    ) -> ActionResult:
        return ActionResult(
            ok=ok,
            action=action,
            target=target,
            detail=detail,
            error=error,
            hint=hint,
        )
