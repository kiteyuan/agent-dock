"""Admin write and read routes. HTTP transport stays in http_server.

Only `/api/v1/*` is supported (pre-v1 aliases removed).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse


def api_get(host: Any, path: str) -> None:
    runtime = host._runtime()
    if runtime is None:
        return
    snapshot = runtime.snapshot.build().model_dump(mode="json")
    if path == "/api/v1/snapshot":
        if "discover" in parse_qs(urlparse(host.path).query):
            runtime.sync_bundles()
            snapshot = runtime.snapshot.build().model_dump(mode="json")
        host._json(HTTPStatus.OK, snapshot)
        return
    if path == "/api/v1/mcp":
        host._json(HTTPStatus.OK, {"ok": True, **runtime.mcp.public()})
        return
    if path == "/api/v1/notes/graph":
        indexer = getattr(runtime, "notes", None)
        if indexer is None:
            host._json(HTTPStatus.OK, {"ok": True, "root": "", "nodes": [], "edges": [], "stats": {}})
            return
        host._json(HTTPStatus.OK, indexer.graph())
        return
    if path == "/api/v1/notes/doc":
        indexer = getattr(runtime, "notes", None)
        note_id = (parse_qs(urlparse(host.path).query).get("id") or [""])[0]
        if indexer is None:
            host._json(
                HTTPStatus.OK,
                {"ok": True, "id": note_id, "title": "", "path": "", "exists": False, "content": ""},
            )
            return
        payload = indexer.doc(note_id)
        status = HTTPStatus.OK if payload.get("ok", True) else HTTPStatus.BAD_REQUEST
        host._json(status, payload)
        return
    if path == "/api/v1/jobs":
        host._json(
            HTTPStatus.OK,
            {"jobs": [job.model_dump(mode="json") for job in runtime.lifecycle.jobs()]},
        )
        return
    if path.startswith("/api/v1/jobs/"):
        job = runtime.lifecycle.job(path.rsplit("/", 1)[-1])
        if job is None:
            host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "job not found"})
        else:
            host._json(HTTPStatus.OK, job.model_dump(mode="json"))
        return

    host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def api_post(host: Any, path: str, body: dict[str, Any]) -> None:
    runtime = host._runtime()
    if runtime is None:
        return

    if path == "/api/v1/mcp":
        try:
            saved = runtime.mcp.replace(body)
        except ValueError as exc:
            host._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        host._json(HTTPStatus.OK, {"ok": True, **saved})
        return

    if path == "/api/v1/llm/shared":
        try:
            settings = runtime.agent_configs.set_shared(
                provider_id=str(body.get("provider") or "").strip(),
                model=str(body.get("model") or "").strip(),
                base_url=str(body.get("base_url") or "").strip(),
                credential=(
                    str(body["credential"])
                    if "credential" in body and body["credential"] is not None
                    else None
                ),
                clear_credential=body.get("clear_credential") is True,
            )
        except ValueError as exc:
            host._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        job_ids = [
            job_id
            for module_id in runtime.agent_configs.using_shared()
            if (job_id := restart_owned_agent(runtime, module_id)[0])
        ]
        host._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "settings": settings,
                "job_id": job_ids[0] if job_ids else None,
                "job_ids": job_ids,
                "restart_required": False,
            },
        )
        return

    if path.startswith("/api/v1/agents/") and path.endswith("/settings"):
        parts = path.strip("/").split("/")
        if len(parts) != 5:
            host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        module_id = parts[3]
        try:
            settings = runtime.agent_configs.set(
                module_id,
                source=str(body.get("source") or "custom").strip() or "custom",
                provider_id=str(body.get("provider") or "").strip(),
                model=str(body.get("model") or "").strip(),
                base_url=str(body.get("base_url") or "").strip(),
                credential=(
                    str(body["credential"])
                    if "credential" in body and body["credential"] is not None
                    else None
                ),
                clear_credential=body.get("clear_credential") is True,
            )
        except ValueError as exc:
            host._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        job_id, owned = restart_owned_agent(runtime, module_id)
        host._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "settings": settings,
                "job_id": job_id,
                "restart_required": owned and not job_id,
            },
        )
        return

    if path == "/api/v1/defaults/agent":
        set_default(host, runtime, "agent", body.get("id"))
        return
    if path == "/api/v1/defaults/tts":
        set_default(host, runtime, "tts", body.get("id"))
        return
    if path == "/api/v1/defaults/stt":
        set_default(host, runtime, "stt", body.get("id"))
        return
    if path == "/api/v1/defaults/pet":
        set_default(host, runtime, "pet", body.get("id"))
        return
    if path.startswith("/api/v1/jobs/") and path.endswith("/cancel"):
        job_id = path[len("/api/v1/jobs/") : -len("/cancel")]
        ok = runtime.lifecycle.cancel(job_id)
        host._json(
            HTTPStatus.ACCEPTED if ok else HTTPStatus.NOT_FOUND,
            {"ok": ok, "job_id": job_id},
        )
        return
    if path.startswith("/api/v1/licenses/"):
        parts = path.strip("/").split("/")
        if len(parts) != 5:
            host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        _, _, _, module_id, license_id = parts
        module = runtime.catalog.module(module_id)
        known = module and any(item.id == license_id for item in module.licenses)
        if not known:
            host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "license not found"})
            return
        accepted = body.get("accepted") is True
        runtime.module_state.accept_license(
            module_id,
            license_id,
            accepted=accepted,
        )
        host._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "module_id": module_id,
                "license_id": license_id,
                "accepted": accepted,
            },
        )
        return

    if path.startswith("/api/v1/modules/"):
        parts = path.strip("/").split("/")
        if len(parts) != 6:
            host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        _, _, _, kind, target, action = parts
        if kind not in ("agent", "tts", "stt", "service", "pet"):
            host._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"unsupported module kind: {kind}"},
            )
            return
        if action not in ("prepare", "start", "stop", "uninstall"):
            host._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"unsupported action: {action}"},
            )
            return
        if action == "uninstall" and _uninstall_blocked(host, runtime, kind, target):
            return
        result = runtime.lifecycle.submit(action, target, options=body)
        host._json(
            HTTPStatus.ACCEPTED if result.ok else HTTPStatus.BAD_REQUEST,
            result.model_dump(mode="json"),
        )
        return

    if path == "/api/v1/pets/import":
        target = str(body.get("id") or "").strip()
        result = runtime.lifecycle.submit(
            "import_pet",
            target,
            options={"url": body.get("url"), "label": body.get("label")},
        )
        host._json(
            HTTPStatus.ACCEPTED if result.ok else HTTPStatus.BAD_REQUEST,
            result.model_dump(mode="json"),
        )
        return

    if path.startswith("/api/v1/devices/") and path.endswith("/disconnect"):
        device_id = path[len("/api/v1/devices/") : -len("/disconnect")]
        _schedule(host, runtime.gateway.disconnect_device(device_id), device_id=device_id)
        return
    if path.startswith("/api/v1/sessions/") and path.endswith("/cancel"):
        session_id = path[len("/api/v1/sessions/") : -len("/cancel")]
        _schedule(host, runtime.gateway.cancel_session(session_id), session_id=session_id)
        return

    host._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def set_default(host: Any, runtime: Any, kind: str, raw: Any) -> None:
    value = str(raw).strip() if raw else None
    try:
        runtime.snapshot.set_default(kind, value)
    except ValueError as exc:
        host._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        return
    host._json(HTTPStatus.OK, {"ok": True, "default": value})


def restart_owned_agent(runtime: Any, module_id: str) -> tuple[str | None, bool]:
    module = runtime.catalog.module(module_id)
    if module is None or not module.sidecar_id:
        return None, False
    owned = bool(runtime.services.process_state(module.sidecar_id).get("owned"))
    if not owned:
        return None, False
    runtime.services.stop(module.sidecar_id)
    return runtime.lifecycle.submit("start", module_id).job_id, True


def _uninstall_blocked(host: Any, runtime: Any, kind: str, target: str) -> bool:
    module = runtime.catalog.module(target)
    active = False
    if module and kind == "agent":
        active = runtime.router.default_agent_id in {module.id, module.registry_id}
    elif module and kind == "tts":
        active = runtime.tts_registry.default_id in {
            module.id,
            module.registry_id,
            *module.provider_types,
        }
    elif module and kind == "stt":
        active = (
            runtime.state.default("stt")
            or (runtime.cfg.get("stt") or {}).get("provider")
        ) == module.id
    if not active:
        return False
    host._json(
        HTTPStatus.CONFLICT,
        {"ok": False, "error": "switch the default provider before uninstalling"},
    )
    return True


def _schedule(host: Any, coroutine: Any, **identity: str) -> None:
    runtime = host.runtime
    try:
        ok = runtime.gateway.schedule(coroutine).result(timeout=5)
    except Exception as exc:  # noqa: BLE001
        host._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
        return
    host._json(
        HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND,
        {"ok": ok, **identity},
    )
