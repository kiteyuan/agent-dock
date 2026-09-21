"""Background host capability detection and deterministic provider recommendations."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from runtime.platform.catalog import ModuleCatalog


def _gpu_info() -> tuple[str | None, float]:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return None, 0.0
    try:
        result = subprocess.run(
            [
                nvidia,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, 0.0
    text = (result.stdout or "").strip() or (result.stderr or "").strip()
    first = text.splitlines()[0] if text else ""
    parts = [part.strip() for part in first.split(",", 1)]
    if result.returncode != 0 or len(parts) != 2:
        return None, 0.0
    name, memory = parts
    try:
        return (name or None), round(float(memory) / 1024, 1)
    except ValueError:
        return None, 0.0


def _memory_gb() -> float:
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total", ctypes.c_ulonglong),
                ("available", ctypes.c_ulonglong),
                ("page_total", ctypes.c_ulonglong),
                ("page_available", ctypes.c_ulonglong),
                ("virtual_total", ctypes.c_ulonglong),
                ("virtual_available", ctypes.c_ulonglong),
                ("extended_available", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.total / (1024**3), 1)
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / (1024**3), 1)
    except (AttributeError, ValueError, OSError):
        return 0


class HardwareStore:
    def __init__(self, *, workspace: Path, catalog: ModuleCatalog) -> None:
        self.workspace = workspace
        self.catalog = catalog
        self._data: dict[str, Any] = {
            "status": "detecting",
            "platform": sys.platform,
            "architecture": platform.machine(),
        }
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._detect,
            name="hardware-detect",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def recommendations(self) -> dict[str, Any]:
        hardware = self.snapshot()
        ram = float(hardware.get("ram_gb") or 0)
        commands = hardware.get("commands") or {}
        current_platform = {
            "win32": "windows",
            "linux": "linux",
            "darwin": "darwin",
        }.get(str(hardware.get("platform") or sys.platform), str(hardware.get("platform")))

        def compatible(module_id: str) -> bool:
            module = self.catalog.module(module_id)
            return bool(module and current_platform in module.hardware.platforms)

        preferred = "opencode" if commands.get("node") and commands.get("npm") else "aider"
        agent = preferred if compatible(preferred) else next(
            (
                item.id
                for item in self.catalog.modules_by_kind("agent")
                if compatible(item.id)
            ),
            "",
        )
        tts_modules = self.catalog.modules_by_kind("tts")
        cloud = [item.id for item in tts_modules if not item.capabilities.local]
        tts = cloud[0] if cloud else (tts_modules[0].id if tts_modules else "")
        tts_alternatives = [item.id for item in tts_modules if item.id != tts]
        stt_modules = [item.id for item in self.catalog.modules_by_kind("stt")]
        sense = self.catalog.module("sensevoice")
        sense_ram = sense.hardware.min_ram_gb if sense else 4
        if sense and ram >= sense_ram and "sensevoice" in stt_modules:
            stt = "sensevoice"
        elif "whisper" in stt_modules:
            stt = "whisper"
        else:
            stt = stt_modules[0] if stt_modules else ""
        return {
            "agent": agent,
            "tts": tts,
            "stt": stt,
            "alternatives": {
                "agent": [
                    item.id
                    for item in self.catalog.modules_by_kind("agent")
                    if item.id != agent and compatible(item.id)
                ],
                "tts": tts_alternatives,
                "stt": [item for item in stt_modules if item != stt],
            },
            "reason": {
                "agent": "OpenCode is provider-neutral" if agent == "opencode" else "Python fallback",
                "tts": "no local model" if tts in cloud else "local engine",
                "stt": "SenseVoice prioritizes Chinese" if stt == "sensevoice" else "low-memory fallback",
            },
        }

    def _detect(self) -> None:
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
            disk = shutil.disk_usage(self.workspace)
            commands = {
                name: bool(shutil.which(name))
                for name in (
                    "node",
                    "npm",
                    "git",
                    "uv",
                    "docker",
                    "codex",
                    "claude",
                )
            }
            gpu_name, vram_gb = _gpu_info()
            value = {
                "status": "ready",
                "platform": {
                    "win32": "windows",
                    "linux": "linux",
                    "darwin": "darwin",
                }.get(sys.platform, sys.platform),
                "architecture": platform.machine(),
                "ram_gb": _memory_gb(),
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "gpu": gpu_name,
                "vram_gb": vram_gb,
                "cuda": bool(gpu_name),
                "commands": commands,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("hardware detection failed")
            value = {
                "status": "error",
                "platform": sys.platform,
                "architecture": platform.machine(),
                "error": str(exc),
            }
        with self._lock:
            self._data = value
