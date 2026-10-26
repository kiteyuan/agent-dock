"""Minimal ``.env`` loader (no third-party dotenv dependency).

Only sets keys that are not already in ``os.environ`` (shell wins).
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    if s.startswith("export "):
        s = s[7:].strip()
    key, _, raw = s.partition("=")
    key = key.strip()
    if not key:
        return None
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    return key, val


def load_env_file(path: Path) -> bool:
    """Load ``path`` into ``os.environ``. Returns True if the file was read."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed is None:
            continue
        key, val = parsed
        if key not in os.environ:
            os.environ[key] = val
    return True


def load_dotenv_files() -> list[Path]:
    """Load ``.env`` from cwd and repo root (``runtime/`` parent). First wins per key."""
    loaded: list[Path] = []
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if load_env_file(resolved):
            loaded.append(resolved)
    return loaded
