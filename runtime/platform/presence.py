"""Single check for whether an Agent CLI is actually present on this machine."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime.platform.types import ModuleSpec


def agent_installed(
    spec: ModuleSpec,
    *,
    root: Path,
    workspace: Path | None = None,
    has_receipt: bool = False,
) -> tuple[bool, str]:
    """Return (installed, detail). Detail is a path or a short reason."""
    command = spec.health.command if spec.health.kind == "command" else None
    if command:
        found = shutil.which(command)
        if found:
            return True, found
    if workspace is not None and has_receipt:
        leftover = workspace / "modules" / spec.id
        if leftover.is_dir():
            return True, str(leftover)
    if spec.local_marker:
        local = root / spec.local_marker
        if local.is_dir():
            return True, str(local)
    if command:
        return False, f"{command} not on PATH"
    return False, "official CLI not detected"
