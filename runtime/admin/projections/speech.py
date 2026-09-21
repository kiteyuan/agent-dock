"""TTS, voice pack and STT projections."""

from __future__ import annotations

from typing import Any

from runtime.admin.projections.common import module_installed, provider_metadata


def project_tts(host: Any, services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    providers = host.runtime.tts_registry.list_dicts()
    voice_items = _voice_items(host, services)
    active = next(
        (item for item in voice_items if item["id"] == host.runtime.tts_registry.default_id),
        None,
    )
    engines: list[dict[str, Any]] = []
    for spec in host.catalog.modules_by_kind("tts"):
        metadata = provider_metadata(host, spec)
        engine_ids = {spec.id, spec.registry_id}
        matching = [item for item in providers if item.get("id") in engine_ids]
        service = services.get(spec.sidecar_id or "", {})
        sidecar = host.catalog.sidecar(spec.sidecar_id) if spec.sidecar_id else None
        port = service.get("port") or (sidecar.port if sidecar else None)
        local = spec.sidecar_id is not None
        installed, install_detail = module_installed(host, spec.id, spec.install.cwd)
        ready = bool(service.get("healthy")) if local else bool(matching)
        engines.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "dependencies": spec.dependencies,
                **metadata,
                "registered": bool(matching),
                "selection_id": spec.registry_id or spec.id,
                "selected": host.runtime.tts_registry.default_id in engine_ids
                or (active is not None and active["engine"] == spec.id),
                "installed": installed,
                "install_detail": install_detail,
                "ready": ready and installed and (bool(matching) or local),
                "status": "ready" if ready and installed and (matching or local) else (
                    "missing" if not installed else "stopped"
                ),
                "sidecar_id": spec.sidecar_id,
                "port": port,
                "address": f"http://127.0.0.1:{port}" if port else "",
                "can_prepare": not installed
                and spec.install.kind != "none"
                and metadata["platform_compatible"],
                "installable": spec.install.kind != "none",
                "can_start": installed and local and not service.get("healthy"),
                "can_stop": bool(service.get("can_stop")),
                "detail": service.get("detail") if local else "no local process",
            }
        )
    return {
        "default": host.runtime.tts_registry.default_id,
        "engines": engines,
        "providers": providers,
        "voices": voice_items,
    }


def _voice_items(host: Any, services: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in host.runtime.voices.records:
        module = host.catalog.module(record.engine) if record.engine else None
        engine_ready = True
        if module and module.sidecar_id:
            engine_ready = bool(services.get(module.sidecar_id, {}).get("healthy"))
        elif module and module.install.kind == "steps":
            installed, _detail = module_installed(host, module.id, module.install.cwd)
            engine_ready = installed
        ready = record.complete and engine_ready
        detail = record.detail
        if record.complete and not engine_ready:
            detail = "引擎未就绪"
        address = str(getattr(record.provider, "url", "") or "")
        model = ""
        if isinstance(record.meta, dict):
            model = str(record.meta.get("voice") or record.meta.get("model") or "")
        items.append(
            {
                "id": record.id,
                "name": record.name,
                "engine": record.engine,
                "engine_name": module.name if module else record.engine,
                "path": f"voices/{record.id}",
                "address": address,
                "model": model,
                "complete": record.complete,
                "ready": ready,
                "selected": host.runtime.tts_registry.default_id == record.id,
                "detail": detail,
            }
        )
    return items


def project_stt(host: Any, services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    provider = host.runtime.stt
    config = host.runtime.cfg.get("stt") or {}
    selected_id = host.state.default("stt") or config.get("provider", "whisper")
    providers = []
    for spec in host.catalog.modules_by_kind("stt"):
        metadata = provider_metadata(host, spec)
        installed, detail = module_installed(host, spec.id, spec.install.cwd)
        service = (
            host.health.get(f"service:{spec.sidecar_id}")
            if spec.sidecar_id
            else None
        )
        sidecar = host.catalog.sidecar(spec.sidecar_id) if spec.sidecar_id else None
        port = sidecar.port if sidecar else None
        providers.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "installed": installed,
                "install_detail": detail,
                "running": bool(service and service.healthy),
                "sidecar_id": spec.sidecar_id,
                "port": port,
                "address": f"http://127.0.0.1:{port}" if port else "",
                "selected": selected_id == spec.id,
                "can_prepare": not installed
                and spec.install.kind != "none"
                and metadata["platform_compatible"],
                "installable": spec.install.kind != "none",
                "can_start": bool(
                    spec.sidecar_id and installed and not (service and service.healthy)
                ),
                "can_stop": bool(services.get(spec.sidecar_id or "", {}).get("owned")),
                **metadata,
            }
        )
    if provider is None:
        return {
            "id": selected_id,
            "enabled": False,
            "ready": False,
            "status": "off",
            "config": config,
            "providers": providers,
        }
    status_fn = getattr(provider, "status", None)
    provider_status = status_fn() if callable(status_fn) else {}
    selected = host.catalog.module(str(selected_id))
    if selected and selected.sidecar_id:
        sidecar_state = services.get(selected.sidecar_id, {})
        ready = bool(sidecar_state.get("healthy"))
        provider_status = {
            **provider_status,
            "ready": ready,
            "status": "ready" if ready else "stopped",
        }
    else:
        ready = bool(provider_status.get("ready"))
    return {
        "id": selected_id,
        "enabled": True,
        "ready": ready,
        "status": provider_status.get("status", "unknown"),
        "provider": provider_status,
        "config": config,
        "providers": providers,
    }
