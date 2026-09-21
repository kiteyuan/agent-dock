"""Persistent Runtime overrides written by Admin, separate from config.yaml."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from loguru import logger


class RuntimeState:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "runtime-state.json"
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "defaults": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("schema_version", 1)
                data.setdefault("defaults", {})
                return data
        except (OSError, json.JSONDecodeError):
            logger.exception("Invalid runtime state {}; ignoring", self.path)
        return {"schema_version": 1, "defaults": {}}

    def default(self, key: str) -> str | None:
        with self._lock:
            value = (self._data.get("defaults") or {}).get(key)
            return str(value) if value else None

    def set_default(self, key: str, value: str | None) -> None:
        if key not in ("agent", "tts", "stt"):
            raise ValueError(f"unsupported default: {key}")
        with self._lock:
            defaults = self._data.setdefault("defaults", {})
            if value:
                defaults[key] = value
            else:
                defaults.pop(key, None)
            self._write_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
