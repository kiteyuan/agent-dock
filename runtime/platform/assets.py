"""Background index for filesystem-backed voices and pet packs."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from runtime.pets import list_pets


class AssetIndex:
    def __init__(
        self,
        *,
        root: Path,
        pets_root: Path,
        interval_seconds: float = 5.0,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.pets_root = pets_root
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.on_refresh = on_refresh
        self._data: dict[str, Any] = {"voices": [], "pets": [], "pet_default": None}
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
            name="asset-index",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def invalidate(self) -> None:
        self._wake.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def refresh(self) -> None:
        voices_root = self.root / "voices"
        voices = []
        if voices_root.is_dir():
            voices = [
                {
                    "id": child.name,
                    "path": str(child.relative_to(self.root)).replace("\\", "/"),
                    "has_voice_yaml": (child / "voice.yaml").is_file(),
                }
                for child in sorted(voices_root.iterdir())
                if child.is_dir()
            ]
        pets, default = list_pets(self.pets_root)
        pet_items = []
        for pet in pets:
            pet_id = str(pet.get("id"))
            sheet = self.pets_root / pet_id / "spritesheet.webp"
            pet_items.append(
                {
                    **pet,
                    "present": sheet.is_file(),
                    "is_default": pet_id == default,
                    "path": str(sheet) if sheet.is_file() else None,
                }
            )
        with self._lock:
            self._data = {
                "voices": voices,
                "pets": pet_items,
                "pet_default": default,
            }
        if self.on_refresh is not None:
            try:
                self.on_refresh()
            except Exception:  # noqa: BLE001
                logger.exception("asset index on_refresh failed")

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.interval_seconds)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.refresh()
            except Exception:  # noqa: BLE001
                logger.exception("asset index refresh failed")
