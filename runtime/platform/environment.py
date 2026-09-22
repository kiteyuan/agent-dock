"""Process / deployment environment helpers."""

from __future__ import annotations

import os
from pathlib import Path


def running_in_docker() -> bool:
    """True when Runtime is inside a container (compose sets AGENTDOCK_DOCKER=1)."""
    if os.environ.get("AGENTDOCK_DOCKER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if Path("/.dockerenv").is_file():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.is_file():
        try:
            text = cgroup.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        return "docker" in text or "containerd" in text or "/lxc/" in text
    return False


def is_private_lan_ip(host: str) -> bool:
    """RFC1918 / link-local / unique-local — typical Docker bridge peers."""
    value = (host or "").split("%", 1)[0]
    if value.startswith("10."):
        return True
    if value.startswith("192.168."):
        return True
    if value.startswith("169.254."):
        return True
    parts = value.split(".")
    if len(parts) == 4 and parts[0] == "172":
        try:
            second = int(parts[1])
        except ValueError:
            return False
        return 16 <= second <= 31
    if value.startswith("fc") or value.startswith("fd") or value.startswith("fe80:"):
        return True
    return False
