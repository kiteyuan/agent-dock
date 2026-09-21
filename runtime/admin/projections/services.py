"""Sidecar rows for the Admin service list."""

from __future__ import annotations

from typing import Any

from runtime.admin.projections.common import agent_is_installed, module_installed


def public_health_detail(detail: str, *, healthy: bool, kind: str) -> str:
    """Hide interpreter exception text. Keep real HTTP status codes."""
    text = (detail or "").strip()
    if healthy:
        if text.startswith("HTTP") or text in {"正常", "监听中"}:
            return "正常"
        return text or "正常"
    if text.startswith("HTTP "):
        return text
    lowered = text.lower()
    if "timed out" in lowered or "timeout" in lowered or text == "无响应":
        return "无响应"
    if kind in ("tcp", "http") or any(
        token in lowered
        for token in ("urlopen", "not listening", "refused", "errno", "未监听")
    ):
        return "未监听"
    return text or "未就绪"


def project_services(host: Any) -> list[dict[str, Any]]:
    modules_by_sidecar: dict[str, list[Any]] = {}
    for module in host.catalog.modules:
        if module.sidecar_id:
            modules_by_sidecar.setdefault(module.sidecar_id, []).append(module)
    result: list[dict[str, Any]] = []
    for spec in host.catalog.sidecars:
        health = host.health.get(f"service:{spec.id}")
        process = host.supervisor.process_state(spec.id)
        related = modules_by_sidecar.get(spec.id, [])
        startable, blocked = _sidecar_startable(host, related)
        result.append(
            {
                "id": spec.id,
                "name": spec.name,
                "port": spec.port,
                "group": related[0].kind if related else "core",
                "managed": spec.managed,
                "autostart": spec.autostart,
                "healthy": health.healthy,
                "status": health.status,
                "detail": public_health_detail(
                    health.detail,
                    healthy=health.healthy,
                    kind=spec.health.kind,
                ),
                "expected": bool(health.healthy or startable),
                "blocked_reason": "" if startable or health.healthy else blocked,
                "data": health.data,
                "checked_at": health.checked_at,
                "can_start": bool(
                    spec.managed
                    and spec.spawn is not None
                    and not health.healthy
                    and startable
                ),
                "can_stop": spec.managed and bool(process["owned"]),
                **process,
            }
        )
    return result


def _sidecar_startable(host: Any, modules: list[Any]) -> tuple[bool, str]:
    """Core services have no module. Everything else must be installed first."""
    if not modules:
        return True, ""
    for module in modules:
        if module.kind == "agent":
            installed, detail = agent_is_installed(host, module)
        elif module.install.kind == "none":
            return True, ""
        else:
            installed, detail = module_installed(host, module.id, module.install.cwd)
        if installed:
            return True, ""
        return False, detail or "未安装"
    return False, "未安装"
