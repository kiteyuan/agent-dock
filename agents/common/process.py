"""Shared CLI process lifecycle for Agent Protocol gateways."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from typing import Any


def kill_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass


def launch_cli(command: list[str], *, cwd: str) -> tuple[subprocess.Popen[str], Any]:
    """Start a CLI with stdout PIPE and stderr on a TemporaryFile (avoids PIPE deadlock).

    Caller owns the returned error_log file object and must close it.
    """
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdin": subprocess.DEVNULL,
        "bufsize": 1,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    error_log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    try:
        process = subprocess.Popen(command, stderr=error_log, **kwargs)
    except Exception:
        error_log.close()
        raise
    return process, error_log


class ProcessTable:
    """Track one CLI process per session_id with cancel support."""

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def register(self, session_id: str, process: subprocess.Popen[Any]) -> None:
        with self._lock:
            old = self._processes.pop(session_id, None)
            if old is not None:
                kill_process(old)
            self._processes[session_id] = process
            self._cancelled.discard(session_id)

    def release(self, session_id: str, process: subprocess.Popen[Any]) -> bool:
        """Drop registry entry if it still points at ``process``. Return cancelled flag."""
        with self._lock:
            cancelled = session_id in self._cancelled
            self._cancelled.discard(session_id)
            if self._processes.get(session_id) is process:
                self._processes.pop(session_id, None)
            return cancelled

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            process = self._processes.get(session_id)
            if process is not None:
                self._cancelled.add(session_id)
        if process is None:
            return False
        kill_process(process)
        return True
