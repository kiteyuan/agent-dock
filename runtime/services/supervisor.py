"""Generic sidecar process supervisor driven by :mod:`runtime.platform.catalog`."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.environment import running_in_docker
from runtime.platform.health import tcp_open
from runtime.platform.types import SidecarSpec
from runtime.paths import resolve_installs, resolve_logs, resolve_workspace


@dataclass
class ManagedProcess:
    popen: subprocess.Popen[Any]
    started_at: float = field(default_factory=time.time)
    log_path: Path | None = None
    log_file: Any = None


class ServiceSupervisor:
    """Own child processes; discovery and health belong to other services."""

    def __init__(
        self,
        cfg: dict[str, Any] | None = None,
        *,
        catalog: ModuleCatalog | None = None,
        environment_resolver: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        self.cfg = dict(cfg or {})
        self.catalog = catalog or ModuleCatalog.load(self.cfg)
        self.root = self.catalog.root
        self._context = self.catalog.context(self.cfg)
        self.workspace = resolve_workspace(self.cfg, ensure=True)
        self.installs_root = resolve_installs(self.cfg, ensure=True)
        self.logs_root = resolve_logs(self.cfg, ensure=True)
        self.environment_resolver = environment_resolver or (lambda _module_id: {})
        self._lock = threading.RLock()
        self._processes: dict[str, ManagedProcess] = {}
        atexit.register(self.stop_all)

    def specs(self) -> list[SidecarSpec]:
        return list(self.catalog.sidecars)

    def process_state(self, service_id: str) -> dict[str, Any]:
        """Cheap process metadata. No network probe is performed here."""
        with self._lock:
            process = self._processes.get(service_id)
            if process and process.popen.poll() is not None:
                self._close_log(process)
                self._processes.pop(service_id, None)
                process = None
            alive = bool(process and process.popen.poll() is None)
            return {
                "owned": alive,
                "pid": process.popen.pid if alive and process else None,
                "log": str(process.log_path) if process and process.log_path else None,
                "started_at": process.started_at if process else None,
            }

    def start(self, service_id: str) -> dict[str, Any]:
        spec = self.catalog.sidecar(service_id)
        if spec is None:
            return {"ok": False, "error": f"unknown service: {service_id}"}
        if not spec.managed or spec.spawn is None:
            return {"ok": False, "error": f"{service_id} is not managed"}
        blocked = self._docker_spawn_blocked(service_id)
        if blocked:
            return {"ok": False, "error": blocked, "id": service_id}
        with self._lock:
            state = self.process_state(service_id)
            if state["owned"]:
                return {"ok": True, "already": True, "id": service_id, **state}
            if tcp_open("127.0.0.1", spec.port):
                return {
                    "ok": False,
                    "id": service_id,
                    "port": spec.port,
                    "error": "port already in use by a process Runtime did not start",
                }
            try:
                executable, args, cwd, env = self._render_spawn(spec)
            except ValueError as exc:
                return {"ok": False, "error": str(exc), "id": service_id}
            result = self._spawn(
                spec,
                executable=executable,
                args=args,
                cwd=cwd,
                env=env,
            )
        if not result.get("ok"):
            return result
        time.sleep(0.4)
        with self._lock:
            process = self._processes.get(service_id)
            if process is None or process.popen.poll() is None:
                return result
            code = process.popen.returncode
            self._processes.pop(service_id, None)
            tail = ""
            if process.log_path is not None:
                try:
                    tail = process.log_path.read_text(encoding="utf-8", errors="replace")[-800:].strip()
                except OSError:
                    tail = ""
            self._close_log(process)
            return {"ok": False, "error": tail or f"exited {code}", "id": service_id}

    def ensure_listening(self, service_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
        """Start a managed sidecar if needed and wait until its port accepts TCP."""
        spec = self.catalog.sidecar(service_id)
        if spec is None or not spec.managed or spec.spawn is None:
            return {"ok": True, "id": service_id}
        if tcp_open("127.0.0.1", spec.port):
            return {"ok": True, "already": True, "id": service_id}
        blocked = self._docker_spawn_blocked(service_id)
        if blocked:
            # Agent gateways are expected on the host (host.docker.internal).
            if self._is_agent_sidecar(service_id):
                return {"ok": True, "id": service_id, "external": True}
            return {"ok": False, "error": blocked, "id": service_id}
        started = self.start(service_id)
        if tcp_open("127.0.0.1", spec.port):
            return {"ok": True, "already": True, "id": service_id}
        if not started.get("ok"):
            return started
        deadline = time.time() + timeout
        while time.time() < deadline:
            if tcp_open("127.0.0.1", spec.port):
                return {"ok": True, "id": service_id}
            time.sleep(0.2)
        return {
            "ok": False,
            "id": service_id,
            "error": f"{service_id} did not listen on {spec.port}",
        }

    def _is_agent_sidecar(self, service_id: str) -> bool:
        return any(
            module.sidecar_id == service_id and module.kind == "agent"
            for module in self.catalog.modules
        )

    def _docker_spawn_blocked(self, service_id: str) -> str | None:
        if not running_in_docker():
            return None
        if service_id == "web":
            return (
                "Web preview cannot run inside the Runtime container; "
                "open clients/web on the host instead"
            )
        if self._is_agent_sidecar(service_id):
            return (
                "Agent gateways cannot be spawned inside the Runtime container. "
                "Install the CLI on the host, run agents/*/gateway.py there, "
                "and point agent URL at host.docker.internal"
            )
        spec = self.catalog.sidecar(service_id)
        if spec is not None and spec.spawn is not None:
            blob = " ".join([spec.spawn.executable, *spec.spawn.args])
            if "agents/" in blob or "clients/" in blob:
                return (
                    f"{service_id} spawn needs repo paths that are not in the "
                    "Runtime image; run it on the host"
                )
        return None

    def stop(self, service_id: str) -> dict[str, Any]:
        spec = self.catalog.sidecar(service_id)
        if spec is None:
            return {"ok": False, "error": f"unknown service: {service_id}"}
        if not spec.managed:
            return {"ok": False, "error": f"{service_id} is not managed"}
        with self._lock:
            process = self._processes.pop(service_id, None)
            if process is None:
                if tcp_open("127.0.0.1", spec.port):
                    return {
                        "ok": False,
                        "id": service_id,
                        "error": "port is in use by a process Runtime did not start",
                    }
                return {
                    "ok": True,
                    "already": True,
                    "id": service_id,
                    "note": "not running",
                }
            if process.popen.poll() is not None:
                self._close_log(process)
                return {
                    "ok": True,
                    "already": True,
                    "id": service_id,
                    "note": "not running",
                }
            killed = self._terminate(process.popen)
            self._close_log(process)
            return {"ok": killed, "id": service_id, "killed": killed}

    def refresh_context(self) -> None:
        with self._lock:
            self._context = self.catalog.context(self.cfg)

    def stop_all(self) -> None:
        with self._lock:
            for service_id in list(self._processes):
                self.stop(service_id)

    def _render_spawn(
        self, spec: SidecarSpec
    ) -> tuple[str, list[str], Path, dict[str, str]]:
        assert spec.spawn is not None
        module = next(
            (item for item in self.catalog.modules if item.sidecar_id == spec.id),
            None,
        )
        module_id = module.id if module else spec.id
        module_dir = self.installs_root / module_id
        scripts = module_dir / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
        module_python = scripts / ("python.exe" if sys.platform == "win32" else "python")
        module_bin = module_dir / "node_modules" / ".bin"
        context = {
            **self._context,
            "port": str(spec.port),
            "workspace": str(self.workspace),
            "module_dir": str(module_dir),
            "module_bin": str(module_bin),
            "module_python": str(module_python),
        }

        def render(value: str) -> str:
            for key, resolved in context.items():
                if f"{{{key}}}" in str(value) and not str(resolved).strip():
                    raise ValueError(
                        f"missing spawn setting for {spec.id}: {key}; "
                        f"configure services.{spec.id}"
                    )
            try:
                return str(value).format_map(context)
            except KeyError as exc:
                raise ValueError(
                    f"missing spawn setting for {spec.id}: {exc.args[0]}"
                ) from exc

        executable = render(spec.spawn.executable)
        args = [render(item) for item in spec.spawn.args]
        cwd_raw = render(spec.spawn.cwd)
        cwd = Path(cwd_raw).expanduser()
        if not cwd.is_absolute():
            cwd = self.root / cwd
        cwd = cwd.resolve()
        if not executable.strip():
            raise ValueError(f"missing executable for {spec.id}")
        if not cwd.is_dir():
            raise ValueError(
                f"missing working directory for {spec.id}: {cwd}; configure services.{spec.id}"
            )
        env = {key: render(value) for key, value in spec.spawn.env.items()}
        env.setdefault("AGENTDOCK_MODULE_DIR", str(module_dir))
        env.update(self.environment_resolver(module_id))
        if module and module.kind == "agent":
            env["AGENTDOCK_AGENT_ID"] = module.id
        return executable, args, cwd, env

    def _spawn(
        self,
        spec: SidecarSpec,
        *,
        executable: str,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
    ) -> dict[str, Any]:
        log_dir = self.logs_root
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{spec.id}.log"
        log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
        log_file.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_file.flush()
        child_env = self._child_environment(env)
        child_env["PYTHONUNBUFFERED"] = "1"
        kwargs: dict[str, Any] = {
            "args": [executable, *args],
            "cwd": str(cwd),
            "env": child_env,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        try:
            popen = subprocess.Popen(**kwargs)
        except Exception as exc:  # noqa: BLE001
            log_file.close()
            return {"ok": False, "error": str(exc), "id": spec.id}
        self._processes[spec.id] = ManagedProcess(
            popen=popen,
            log_path=log_path,
            log_file=log_file,
        )
        logger.info(
            "started service {} pid={} port={} log={}",
            spec.id,
            popen.pid,
            spec.port,
            log_path,
        )
        return {
            "ok": True,
            "id": spec.id,
            "pid": popen.pid,
            "port": spec.port,
            "log": str(log_path),
        }

    @staticmethod
    def _child_environment(overrides: dict[str, str]) -> dict[str, str]:
        child_env = os.environ.copy()
        if overrides.get("AGENTDOCK_AGENT_ID"):
            sensitive_suffixes = (
                "_API_KEY",
                "_AUTH_TOKEN",
                "_ACCESS_TOKEN",
                "_PERSONAL_ACCESS_TOKEN",
            )
            child_env = {
                key: value
                for key, value in child_env.items()
                if not key.upper().endswith(sensitive_suffixes)
            }
        child_env.update(overrides)
        return child_env

    @staticmethod
    def _terminate(popen: subprocess.Popen[Any]) -> bool:
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["taskkill", "/PID", str(popen.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
                if popen.poll() is not None:
                    return True
                return result.returncode == 0
            try:
                os.killpg(popen.pid, signal.SIGTERM)
            except ProcessLookupError:
                return True
            try:
                popen.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(popen.pid, signal.SIGKILL)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("terminate failed pid={}: {}", popen.pid, exc)
            return False

    @staticmethod
    def _close_log(process: ManagedProcess) -> None:
        if process.log_file:
            try:
                process.log_file.close()
            except OSError:
                pass
