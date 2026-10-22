"""Single check for whether an Agent CLI is actually present on this machine."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime.platform.types import ModuleSpec


def agent_installed(
    spec: ModuleSpec,
    *,
    root: Path,
    installs_root: Path | None = None,
    has_receipt: bool = False,
    workspace: Path | None = None,
) -> tuple[bool, str]:
    """Return (installed, detail). Detail is a path or a short reason."""
    del workspace  # legacy kwarg ignored; installs live under installs_root
    # Bundled assistants (e.g. Pi under agents/pi-coding) win over a global PATH CLI.
    if spec.local_marker:
        local = root / spec.local_marker
        if local.is_dir():
            return True, str(local)
    if installs_root is not None and has_receipt:
        leftover = installs_root / spec.id
        if leftover.is_dir():
            return True, str(leftover)
    command = spec.health.command if spec.health.kind == "command" else None
    if command:
        found = shutil.which(command)
        if found:
            return True, found
        return False, f"{command} not on PATH (and bundled install missing)"
    return False, "assistant package not detected"
