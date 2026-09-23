"""Agent-side conversation memory files (Pi session jsonl, etc.).

Device reconnect keeps the same device_id, so Pi reuses ``dev-<device_id>``
session files under ``paths.sessions``. When that history is poisoned
(e.g. DeepSeek Content Exists Risk after screenshots), quarantine those
files so the next turn starts a fresh Pi session.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path


def quarantine_device_sessions(
    sessions_root: Path,
    device_id: str,
    *,
    reason: str = "reset",
) -> list[str]:
    """Move session files that belong to ``device_id`` into ``_quarantine/``.

    Returns relative paths (posix) of moved files.
    """
    did = (device_id or "").strip()
    if not did or not sessions_root.is_dir():
        return []

    needles = {did, f"dev-{did}"}
    if did.startswith("dev-") and len(did) > 4:
        needles.add(did[4:])

    moved: list[str] = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    quarantine = sessions_root / "_quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)

    for path in sessions_root.rglob("*"):
        if not path.is_file():
            continue
        if "_quarantine" in path.parts:
            continue
        name = path.name
        if not any(n and n in name for n in needles):
            continue
        dest = quarantine / f"{reason}_{stamp}_{name}"
        # Avoid clobber if same second
        if dest.exists():
            dest = quarantine / f"{reason}_{stamp}_{path.stem}_{path.suffix.lstrip('.') or 'bin'}"
        try:
            shutil.move(str(path), str(dest))
            moved.append(dest.relative_to(sessions_root).as_posix())
        except OSError:
            continue
    return moved
