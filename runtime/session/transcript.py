"""Completed chat transcript per device (not live WS session state).

Only stores finished user/assistant turns after ``agent.done``.
Cancelled / errored / mid-stream turns are never written.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")
_DEFAULT_MAX = 100
_LOCK = threading.Lock()


def _safe_device_id(device_id: str) -> str:
    raw = (device_id or "").strip() or "unknown"
    cleaned = _SAFE.sub("_", raw).strip("._") or "unknown"
    return cleaned[:120]


class TranscriptStore:
    """JSON files under ``<sessions_root>/transcripts/<device_id>.json``."""

    def __init__(self, root: Path | None, *, max_messages: int = _DEFAULT_MAX) -> None:
        self.root = Path(root) if root is not None else None
        self.max_messages = max(1, int(max_messages))

    def _path(self, device_id: str) -> Path | None:
        if self.root is None:
            return None
        return self.root / "transcripts" / f"{_safe_device_id(device_id)}.json"

    def load(self, device_id: str) -> list[dict[str, Any]]:
        path = self._path(device_id)
        if path is None or not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        msgs = raw.get("messages") if isinstance(raw, dict) else raw
        if not isinstance(msgs, list):
            return []
        out: list[dict[str, Any]] = []
        for item in msgs:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            text = item.get("text")
            if role not in ("user", "assistant") or not isinstance(text, str):
                continue
            entry: dict[str, Any] = {"role": role, "text": text}
            if "ts" in item:
                try:
                    entry["ts"] = float(item["ts"])
                except (TypeError, ValueError):
                    entry["ts"] = time.time()
            else:
                entry["ts"] = time.time()
            mid = item.get("id")
            if isinstance(mid, str) and mid:
                entry["id"] = mid
            out.append(entry)
        return out[-self.max_messages :]

    def clear(self, device_id: str) -> None:
        path = self._path(device_id)
        if path is None:
            return
        with _LOCK:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def append_completed(
        self,
        device_id: str,
        *,
        user_text: str,
        assistant_texts: list[str],
    ) -> list[dict[str, Any]]:
        """Append one finished turn (user + assistant replies). Returns full list."""
        did = (device_id or "").strip()
        user = (user_text or "").strip()
        replies = [str(t).strip() for t in assistant_texts if str(t).strip()]
        if not did or not user or not replies:
            return self.load(did) if did else []

        path = self._path(did)
        if path is None:
            return []

        now = time.time()
        additions = [{"role": "user", "text": user, "ts": now}]
        for reply in replies:
            additions.append({"role": "assistant", "text": reply, "ts": now})

        with _LOCK:
            existing = self.load(did)
            merged = (existing + additions)[-self.max_messages :]
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            payload = {"device_id": did, "messages": merged, "updated_at": now}
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
            return merged
