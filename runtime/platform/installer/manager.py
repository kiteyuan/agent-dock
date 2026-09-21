"""Transactional, manifest-driven installer for isolated provider environments."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlparse

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.module_state import ModuleState
from runtime.platform.types import InstallStep, ModuleSpec

Progress = Callable[[float, str], None]


class InstallError(RuntimeError):
    pass


class InstallCancelled(InstallError):
    pass


class InstallManager:
    def __init__(
        self,
        *,
        catalog: ModuleCatalog,
        workspace: Path,
        state: ModuleState,
        proxy: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.workspace = workspace.resolve()
        self.state = state
        self.proxy = proxy
        self.modules_root = self.workspace / "modules"

    def install(
        self,
        module_id: str,
        *,
        cancel: Event | None = None,
        progress: Progress | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        module = self._module(module_id)
        self._check_licenses(module)
        self._check_platform(module)
        self._check_disk(module)
        cancel_event = cancel or Event()
        report = progress or (lambda _value, _message: None)

        target = self._safe_module_dir(module.id)
        existing_receipt = self.state.receipt(module.id)
        if existing_receipt and target.is_dir() and not force:
            return existing_receipt
        if target.exists() and not existing_receipt:
            raise InstallError(
                f"refusing to overwrite unmanaged module directory: {target}"
            )
        self.modules_root.mkdir(parents=True, exist_ok=True)
        backup = self.modules_root / f".backup-{module.id}-{uuid.uuid4().hex[:8]}"
        if target.exists():
            target.replace(backup)
        target.mkdir(parents=True)
        steps = list(module.install.steps)
        if module.install.kind == "npm" and module.install.cwd:
            steps = [
                InstallStep(
                    kind="npm",
                    packages=[],
                    cwd=module.install.cwd,
                )
            ]
        steps.extend(
            InstallStep(
                kind="model",
                url=asset.url,
                destination=asset.destination,
                sha256=asset.sha256,
            )
            for asset in module.models
        )
        artifacts: list[dict[str, Any]] = []
        try:
            for index, step in enumerate(steps):
                self._cancelled(cancel_event)
                start = index / max(1, len(steps))
                span = 1 / max(1, len(steps))
                report(start, f"{module.name}: {step.kind}")
                artifact = self._run_step(
                    module,
                    step,
                    target,
                    cancel_event,
                    lambda value, message, s=start, width=span: report(
                        min(0.99, s + value * width), message
                    ),
                )
                if artifact:
                    artifacts.append(artifact)
            shutil.rmtree(backup, ignore_errors=True)
            receipt = {
                "module_id": module.id,
                "version": module.version,
                "source": module.homepage,
                "artifacts": artifacts,
                "licenses": [
                    {
                        "id": license.id,
                        "url": license.url,
                        "accepted": self.state.accepted(module.id, license.id),
                    }
                    for license in module.licenses
                ],
                "installed_at": time.time(),
            }
            self.state.set_receipt(module.id, receipt)
            report(1, f"{module.name}: installed")
            return receipt
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            if backup.exists():
                backup.replace(target)
            raise

    def uninstall(self, module_id: str) -> None:
        self._module(module_id)
        target = self._safe_module_dir(module_id)
        if self.state.receipt(module_id) is None:
            raise InstallError("refusing to remove an unmanaged module directory")
        if target.exists():
            shutil.rmtree(target, ignore_errors=False)
        self.state.remove_receipt(module_id)

    def check_allowed(self, module_id: str) -> None:
        module = self._module(module_id)
        self._check_licenses(module)
        self._check_platform(module)

    def _run_step(
        self,
        module: ModuleSpec,
        step: InstallStep,
        module_dir: Path,
        cancel: Event,
        progress: Progress,
    ) -> dict[str, Any] | None:
        context = self._context(module_dir)
        if step.kind == "venv":
            uv = shutil.which("uv")
            if step.manager in ("auto", "uv") and uv:
                command = [uv, "venv"]
                if step.executable:
                    command.extend(["--python", step.executable])
                command.append(str(module_dir / ".venv"))
            elif step.manager == "uv":
                raise InstallError("uv not found on PATH")
            else:
                python = self._python_command(step.executable)
                command = [*python, "-m", "venv", str(module_dir / ".venv")]
            self._run(
                command,
                cwd=self.catalog.root,
                cancel=cancel,
            )
            return {
                "kind": "venv",
                "python": step.executable or sys.version,
                "manager": "uv" if uv and step.manager in ("auto", "uv") else "venv",
            }
        if step.kind == "pip":
            python = self._venv_python(module_dir)
            packages = [self._render(value, context) for value in step.packages]
            uv = shutil.which("uv")
            command = (
                [uv, "pip", "install", "--python", str(python), *packages]
                if uv
                else [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    *packages,
                ]
            )
            self._run(
                command,
                cwd=self._cwd(step.cwd, context, module_dir),
                cancel=cancel,
            )
            return {"kind": "pip", "packages": packages}
        if step.kind == "npm":
            npm = shutil.which("npm")
            if not npm:
                raise InstallError("npm not found; install Node.js LTS")
            packages = [self._render(value, context) for value in step.packages]
            cwd = self._cwd(step.cwd, context, module_dir)
            command = [npm, "install"]
            if packages:
                command.extend(["--prefix", str(module_dir), *packages])
            self._run(command, cwd=cwd, cancel=cancel, secure_node=True)
            return {"kind": "npm", "packages": packages}
        if step.kind in ("binary", "model"):
            if not step.url or not step.destination:
                raise InstallError(f"{step.kind} step requires url and destination")
            destination = self._safe_destination(
                module_dir, self._render(step.destination, context)
            )
            digest = self._download(
                step.url,
                destination,
                expected_sha256=step.sha256,
                cancel=cancel,
                progress=progress,
            )
            if step.extract:
                self._extract_zip(destination, module_dir)
                destination.unlink(missing_ok=True)
            return {
                "kind": step.kind,
                "url": step.url,
                "path": str(destination.relative_to(module_dir)),
                "sha256": digest,
                "extracted": step.extract,
            }
        if step.kind == "git":
            if not step.url or not step.destination or not step.ref:
                raise InstallError("git step requires url, destination and immutable ref")
            git = shutil.which("git")
            if not git:
                raise InstallError("git not found on PATH")
            destination = self._safe_destination(module_dir, step.destination)
            self._run(
                [
                    git,
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    "--recurse-submodules",
                    step.url,
                    str(destination),
                ],
                cwd=module_dir,
                cancel=cancel,
            )
            self._run(
                [git, "-C", str(destination), "checkout", "--detach", step.ref],
                cwd=module_dir,
                cancel=cancel,
            )
            self._run(
                [
                    git,
                    "-C",
                    str(destination),
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                ],
                cwd=module_dir,
                cancel=cancel,
            )
            return {"kind": "git", "url": step.url, "ref": step.ref}
        if step.kind == "command":
            executable = self._render(step.executable or "", context)
            if not executable:
                raise InstallError("command step requires executable")
            resolved = shutil.which(executable) or executable
            args = [self._render(value, context) for value in step.args]
            self._run(
                [resolved, *args],
                cwd=self._cwd(step.cwd, context, module_dir),
                cancel=cancel,
            )
            return {"kind": "command", "executable": executable, "args": args}
        raise InstallError(f"unsupported install step: {step.kind}")

    def _download(
        self,
        url: str,
        destination: Path,
        *,
        expected_sha256: str | None,
        cancel: Event,
        progress: Progress,
    ) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise InstallError("downloads must use an absolute HTTPS URL")
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "AgentDock/1.0"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        digest = hashlib.sha256()
        if existing:
            with partial.open("rb") as current:
                for chunk in iter(lambda: current.read(1024 * 1024), b""):
                    digest.update(chunk)
        opener = (
            urllib.request.build_opener(
                urllib.request.ProxyHandler(
                    {"http": self.proxy, "https": self.proxy}
                )
            )
            if self.proxy
            else urllib.request.build_opener()
        )
        with opener.open(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0) + existing
            free = shutil.disk_usage(destination.parent).free
            if total and total > free:
                raise InstallError("not enough disk space for download")
            if total > 50 * 1024**3:
                raise InstallError("single module download exceeds 50 GiB")
            mode = "ab" if existing and getattr(response, "status", 200) == 206 else "wb"
            if mode == "wb":
                existing = 0
                digest = hashlib.sha256()
            with partial.open(mode) as output:
                downloaded = existing
                while True:
                    self._cancelled(cancel)
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if downloaded > 50 * 1024**3:
                        raise InstallError("single module download exceeds 50 GiB")
                    if total:
                        progress(downloaded / total, f"download {downloaded // 1048576}/{total // 1048576} MiB")
        actual = digest.hexdigest()
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            partial.unlink(missing_ok=True)
            raise InstallError("download checksum mismatch")
        partial.replace(destination)
        return actual

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        cancel: Event,
        secure_node: bool = False,
    ) -> None:
        self._cancelled(cancel)
        env = os.environ.copy()
        if secure_node:
            env.pop("NODE_TLS_REJECT_UNAUTHORIZED", None)
        process_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            process_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            process_kwargs["start_new_session"] = True
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                stdin=subprocess.DEVNULL,
                **process_kwargs,
            )
            while process.poll() is None:
                if cancel.wait(0.1):
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True,
                            check=False,
                        )
                    else:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                    raise InstallCancelled("installation cancelled")
            log.seek(0)
            output = log.read()
        if process.returncode:
            raise InstallError((output or f"command failed: {command[0]}")[-2000:])

    @staticmethod
    def _extract_zip(archive: Path, target: Path) -> None:
        if not zipfile.is_zipfile(archive):
            raise InstallError("only zip archives are supported for managed extraction")
        root = target.resolve()
        with zipfile.ZipFile(archive) as bundle:
            total = 0
            for member in bundle.infolist():
                total += member.file_size
                if total > 50 * 1024**3:
                    raise InstallError("module archive expands beyond 50 GiB")
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise InstallError("module archive may not contain symlinks")
                destination = (root / member.filename).resolve()
                try:
                    destination.relative_to(root)
                except ValueError as exc:
                    raise InstallError("unsafe path in module archive") from exc
            bundle.extractall(root)

    def _check_licenses(self, module: ModuleSpec) -> None:
        missing = [
            item.id
            for item in module.licenses
            if item.requires_acceptance and not self.state.accepted(module.id, item.id)
        ]
        if missing:
            raise InstallError(
                f"license acceptance required for {module.id}: {', '.join(missing)}"
            )

    @staticmethod
    def _check_platform(module: ModuleSpec) -> None:
        platform = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(
            sys.platform, sys.platform
        )
        if platform not in module.hardware.platforms:
            raise InstallError(f"{module.id} does not support {platform}")

    def _check_disk(self, module: ModuleSpec) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(self.workspace).free / (1024**3)
        required = module.hardware.min_disk_gb
        if required and free_gb < required:
            raise InstallError(
                f"{module.id} needs {required:.1f} GiB free; only {free_gb:.1f} GiB available"
            )

    def _module(self, module_id: str) -> ModuleSpec:
        module = self.catalog.module(module_id)
        if module is None:
            raise InstallError(f"unknown module: {module_id}")
        return module

    def _safe_module_dir(self, module_id: str) -> Path:
        target = (self.modules_root / module_id).resolve()
        try:
            target.relative_to(self.modules_root.resolve())
        except ValueError as exc:
            raise InstallError("unsafe module id") from exc
        return target

    @staticmethod
    def _safe_destination(root: Path, relative: str) -> Path:
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as exc:
            raise InstallError("unsafe install destination") from exc
        return target

    @staticmethod
    def _python_command(version: str | None) -> list[str]:
        if not version:
            return [sys.executable]
        if sys.platform == "win32":
            launcher = shutil.which("py")
            if not launcher:
                raise InstallError("Python launcher 'py' not found")
            return [launcher, f"-{version}"]
        executable = shutil.which(f"python{version}")
        if not executable:
            raise InstallError(f"python{version} not found")
        return [executable]

    @staticmethod
    def _venv_python(module_dir: Path) -> Path:
        relative = Path("Scripts/python.exe") if sys.platform == "win32" else Path("bin/python")
        path = module_dir / ".venv" / relative
        if not path.is_file():
            raise InstallError("module virtual environment is missing")
        return path

    @staticmethod
    def _context(module_dir: Path) -> dict[str, str]:
        relative = (
            Path("Scripts/python.exe")
            if sys.platform == "win32"
            else Path("bin/python")
        )
        return {
            "module_dir": str(module_dir),
            "module_python": str(module_dir / ".venv" / relative),
        }

    @staticmethod
    def _render(value: str, context: dict[str, str]) -> str:
        try:
            return str(value).format_map(context)
        except KeyError as exc:
            raise InstallError(f"unknown install placeholder: {exc.args[0]}") from exc

    def _cwd(
        self,
        value: str | None,
        context: dict[str, str],
        module_dir: Path,
    ) -> Path:
        if not value:
            return module_dir
        rendered = self._render(value, context)
        candidate = Path(rendered)
        if not candidate.is_absolute():
            candidate = self.catalog.root / candidate
        candidate = candidate.resolve()
        if not candidate.is_dir():
            raise InstallError(f"install working directory missing: {candidate}")
        return candidate

    @staticmethod
    def _cancelled(cancel: Event) -> None:
        if cancel.is_set():
            raise InstallCancelled("installation cancelled")
