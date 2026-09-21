"""Persistent installation receipts and explicit license acceptance."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger


class ModuleState:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "module-state.json"
        self._lock = threading.RLock()
        self._data = self._load()

    def accepted(self, module_id: str, license_id: str) -> bool:
        with self._lock:
            licenses = self._data.get("licenses") or {}
            return bool((licenses.get(module_id) or {}).get(license_id))

    def accept_license(
        self,
        module_id: str,
        license_id: str,
        *,
        accepted: bool,
    ) -> None:
        with self._lock:
            module = self._data.setdefault("licenses", {}).setdefault(module_id, {})
            if accepted:
                module[license_id] = {"accepted_at": time.time()}
            else:
                module.pop(license_id, None)
            self._write_locked()

    def receipt(self, module_id: str) -> dict[str, Any] | None:
        with self._lock:
            receipt = (self._data.get("receipts") or {}).get(module_id)
            return json.loads(json.dumps(receipt)) if receipt else None

    def set_receipt(self, module_id: str, receipt: dict[str, Any]) -> None:
        with self._lock:
            value = dict(receipt)
            value.setdefault("installed_at", time.time())
            self._data.setdefault("receipts", {})[module_id] = value
            self._write_locked()

    def remove_receipt(self, module_id: str) -> None:
        with self._lock:
            self._data.setdefault("receipts", {}).pop(module_id, None)
            self._write_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": 1,
                "licenses": {},
                "receipts": {},
            }
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("schema_version", 1)
                data.setdefault("licenses", {})
                data.setdefault("receipts", {})
                return data
        except (OSError, json.JSONDecodeError):
            logger.exception("Invalid module state {}; ignoring", self.path)
        return {
            "schema_version": 1,
            "licenses": {},
            "receipts": {},
        }

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)
