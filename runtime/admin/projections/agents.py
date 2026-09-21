"""Agent cards for the Admin snapshot."""

from __future__ import annotations

from typing import Any

from runtime.admin.projections.common import (
    agent_detail,
    agent_is_installed,
    provider_metadata,
)


def project_agents(host: Any, services: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in host.catalog.modules_by_kind("agent"):
        metadata = provider_metadata(host, spec)
        registered = host.runtime.registry.get(spec.registry_id or spec.id) is not None
        installed, install_detail = agent_is_installed(host, spec)
        service = services.get(spec.sidecar_id or "", {})
        running = bool(service.get("healthy"))
        authenticated = (service.get("data") or {}).get("authenticated")
        configuration = host.agent_configs.public(spec.id)
        configuration["configured"] = bool(
            configuration["configured"] or authenticated is True
        )
        ready = (
            registered
            and installed
            and running
            and configuration["configured"]
            and authenticated is not False
        )
        items.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "dependencies": spec.dependencies,
                **metadata,
                "registered": registered,
                "installed": installed,
                "install_detail": install_detail,
                "running": running,
                "authenticated": authenticated,
                "configuration": configuration,
                "configured": configuration["configured"],
                "region": spec.region,
                "ready": ready,
                "status": "ready" if ready else (
                    "missing"
                    if not installed or not registered
                    else (
                        "unconfigured"
                        if not configuration["configured"]
                        else "stopped"
                    )
                ),
                "is_default": host.runtime.router.default_agent_id
                == (spec.registry_id or spec.id),
                "sidecar_id": spec.sidecar_id,
                "port": service.get("port"),
                "address": (
                    f"http://127.0.0.1:{service.get('port')}"
                    if service.get("port")
                    else ""
                ),
                "can_prepare": False,
                "installable": False,
                "can_start": registered and installed and not running,
                "can_stop": bool(service.get("can_stop")),
                "can_default": registered,
                "detail": agent_detail(
                    registered, installed, running, install_detail
                ),
            }
        )
    return items
