"""Shared catalog facts used by Admin projections and default switching."""

from __future__ import annotations

import sys
from typing import Any

from runtime.platform.presence import agent_installed


def agent_is_installed(host: Any, spec: Any) -> tuple[bool, str]:
    return agent_installed(
        spec,
        root=host.catalog.root,
        workspace=host.runtime.workspace,
        has_receipt=host.module_state.receipt(spec.id) is not None,
    )


def module_installed(host: Any, module_id: str, cwd: str | None) -> tuple[bool, str]:
    del cwd
    spec = host.catalog.module(module_id)
    if spec and spec.install.kind == "steps":
        receipt = host.module_state.receipt(module_id)
        path = host.runtime.workspace / "modules" / module_id
        return bool(receipt and path.is_dir()), (
            f"{receipt.get('version')} · {path}" if receipt else str(path)
        )
    if spec and spec.bundle is not None:
        return host.runtime.bundle_status(module_id)
    return True, "built-in integration"


def provider_metadata(host: Any, spec: Any) -> dict[str, Any]:
    current_platform = {
        "win32": "windows",
        "linux": "linux",
        "darwin": "darwin",
    }.get(sys.platform, sys.platform)
    return {
        "version": spec.version,
        "homepage": spec.homepage,
        "hardware": spec.hardware.model_dump(mode="json"),
        "capabilities": spec.capabilities.model_dump(mode="json"),
        "managed": host.module_state.receipt(spec.id) is not None,
        "install_mode": (
            "bundle"
            if spec.bundle is not None
            else "managed"
            if spec.install.kind != "none"
            else "cli"
            if spec.kind == "agent"
            else "builtin"
        ),
        "platform_compatible": current_platform in spec.hardware.platforms,
        "licenses": [
            {
                **license.model_dump(mode="json"),
                "accepted": host.module_state.accepted(spec.id, license.id),
            }
            for license in spec.licenses
        ],
    }


def agent_detail(
    registered: bool,
    installed: bool,
    running: bool,
    install_detail: str,
) -> str:
    if not registered:
        return "not registered in config"
    if not installed:
        return install_detail or "dependency missing"
    if not running:
        return "installed, gateway stopped"
    return "running"
