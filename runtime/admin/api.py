"""Admin write and read routes — transport-free (http_server owns HTTP).

Only `/api/v1/*` is supported (pre-v1 aliases removed). Handlers are synchronous and may
block (process control, disk); the HTTP layer runs them off the event loop.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

# (HTTP status, JSON-serialisable body)
Reply = tuple[int, Any]


def _not_found(error: str = "not found") -> Reply:
    return HTTPStatus.NOT_FOUND, {"ok": False, "error": error}


def _bad_request(error: str) -> Reply:
    return HTTPStatus.BAD_REQUEST, {"ok": False, "error": error}


def api_get(runtime: Any, path: str, query: str = "") -> Reply:
    params = parse_qs(query)
    if path == "/api/v1/snapshot":
        if "discover" in params:
            runtime.sync_bundles()
        return HTTPStatus.OK, runtime.snapshot.build().model_dump(mode="json")
    if path == "/api/v1/mcp":
        return HTTPStatus.OK, {"ok": True, **runtime.mcp.public()}
    if path == "/api/v1/notes/graph":
        indexer = getattr(runtime, "notes", None)
        if indexer is None:
            return HTTPStatus.OK, {"ok": True, "root": "", "nodes": [], "edges": [], "stats": {}}
        return HTTPStatus.OK, indexer.graph()
    if path == "/api/v1/notes/doc":
        indexer = getattr(runtime, "notes", None)
        note_id = (params.get("id") or [""])[0]
        if indexer is None:
            return HTTPStatus.OK, {
                "ok": True,
                "id": note_id,
                "title": "",
                "path": "",
                "exists": False,
                "content": "",
            }
        payload = indexer.doc(note_id)
        return (HTTPStatus.OK if payload.get("ok", True) else HTTPStatus.BAD_REQUEST), payload
    if path == "/api/v1/jobs":
        return HTTPStatus.OK, {
            "jobs": [job.model_dump(mode="json") for job in runtime.lifecycle.jobs()]
        }
    if path.startswith("/api/v1/jobs/"):
        job = runtime.lifecycle.job(path.rsplit("/", 1)[-1])
        if job is None:
            return _not_found("job not found")
        return HTTPStatus.OK, job.model_dump(mode="json")
    return _not_found()


def _credential(body: dict[str, Any]) -> str | None:
    value = body.get("credential")
    return str(value) if "credential" in body and value is not None else None


def api_post(runtime: Any, path: str, body: dict[str, Any]) -> Reply:
    if path == "/api/v1/mcp":
        try:
            saved = runtime.mcp.replace(body)
        except ValueError as exc:
            return _bad_request(str(exc))
        return HTTPStatus.OK, {"ok": True, **saved}

    if path == "/api/v1/llm/shared":
        try:
            settings = runtime.agent_configs.set_shared(
                provider_id=str(body.get("provider") or "").strip(),
                model=str(body.get("model") or "").strip(),
                base_url=str(body.get("base_url") or "").strip(),
                credential=_credential(body),
                clear_credential=body.get("clear_credential") is True,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        job_ids = [
            job_id
            for module_id in runtime.agent_configs.using_shared()
            if (job_id := restart_owned_agent(runtime, module_id)[0])
        ]
        return HTTPStatus.OK, {
            "ok": True,
            "settings": settings,
            "job_id": job_ids[0] if job_ids else None,
            "job_ids": job_ids,
            "restart_required": False,
        }

    if path.startswith("/api/v1/agents/") and path.endswith("/settings"):
        parts = path.strip("/").split("/")
        if len(parts) != 5:
            return _not_found()
        module_id = parts[3]
        try:
            settings = runtime.agent_configs.set(
                module_id,
                source=str(body.get("source") or "custom").strip() or "custom",
                provider_id=str(body.get("provider") or "").strip(),
                model=str(body.get("model") or "").strip(),
                base_url=str(body.get("base_url") or "").strip(),
                credential=_credential(body),
                clear_credential=body.get("clear_credential") is True,
            )
        except ValueError as exc:
            return _bad_request(str(exc))
        job_id, owned = restart_owned_agent(runtime, module_id)
        return HTTPStatus.OK, {
            "ok": True,
            "settings": settings,
            "job_id": job_id,
            "restart_required": owned and not job_id,
        }

    if path.startswith("/api/v1/defaults/"):
        kind = path[len("/api/v1/defaults/") :]
        if kind in ("agent", "tts", "stt", "pet"):
            return set_default(runtime, kind, body.get("id"))
        return _not_found()

    if path.startswith("/api/v1/jobs/") and path.endswith("/cancel"):
        job_id = path[len("/api/v1/jobs/") : -len("/cancel")]
        ok = runtime.lifecycle.cancel(job_id)
        return (HTTPStatus.ACCEPTED if ok else HTTPStatus.NOT_FOUND), {"ok": ok, "job_id": job_id}

    if path.startswith("/api/v1/licenses/"):
        parts = path.strip("/").split("/")
        if len(parts) != 5:
            return _not_found()
        _, _, _, module_id, license_id = parts
        module = runtime.catalog.module(module_id)
        if not (module and any(item.id == license_id for item in module.licenses)):
            return _not_found("license not found")
        accepted = body.get("accepted") is True
        runtime.module_state.accept_license(module_id, license_id, accepted=accepted)
        return HTTPStatus.OK, {
            "ok": True,
            "module_id": module_id,
            "license_id": license_id,
            "accepted": accepted,
        }

    if path.startswith("/api/v1/modules/"):
        parts = path.strip("/").split("/")
        if len(parts) != 6:
            return _not_found()
        _, _, _, kind, target, action = parts
        if kind not in ("agent", "tts", "stt", "service", "pet"):
            return _bad_request(f"unsupported module kind: {kind}")
        if action not in ("prepare", "start", "stop", "uninstall"):
            return _bad_request(f"unsupported action: {action}")
        if action == "uninstall" and _uninstall_blocked(runtime, kind, target):
            return HTTPStatus.CONFLICT, {
                "ok": False,
                "error": "switch the default provider before uninstalling",
            }
        result = runtime.lifecycle.submit(action, target, options=body)
        return (HTTPStatus.ACCEPTED if result.ok else HTTPStatus.BAD_REQUEST), result.model_dump(
            mode="json"
        )

    if path == "/api/v1/pets/import":
        target = str(body.get("id") or "").strip()
        result = runtime.lifecycle.submit(
            "import_pet",
            target,
            options={"url": body.get("url"), "label": body.get("label")},
        )
        return (HTTPStatus.ACCEPTED if result.ok else HTTPStatus.BAD_REQUEST), result.model_dump(
            mode="json"
        )

    if path.startswith("/api/v1/devices/") and path.endswith("/disconnect"):
        device_id = path[len("/api/v1/devices/") : -len("/disconnect")]
        return _schedule(runtime, runtime.gateway.disconnect_device(device_id), device_id=device_id)
    if path.startswith("/api/v1/sessions/") and path.endswith("/cancel"):
        session_id = path[len("/api/v1/sessions/") : -len("/cancel")]
        return _schedule(runtime, runtime.gateway.cancel_session(session_id), session_id=session_id)

    return _not_found()


def set_default(runtime: Any, kind: str, raw: Any) -> Reply:
    value = str(raw).strip() if raw else None
    try:
        runtime.snapshot.set_default(kind, value)
    except ValueError as exc:
        return _bad_request(str(exc))
    return HTTPStatus.OK, {"ok": True, "default": value}


def restart_owned_agent(runtime: Any, module_id: str) -> tuple[str | None, bool]:
    module = runtime.catalog.module(module_id)
    if module is None or not module.sidecar_id:
        return None, False
    owned = bool(runtime.services.process_state(module.sidecar_id).get("owned"))
    if not owned:
        return None, False
    runtime.services.stop(module.sidecar_id)
    return runtime.lifecycle.submit("start", module_id).job_id, True


def _uninstall_blocked(runtime: Any, kind: str, target: str) -> bool:
    module = runtime.catalog.module(target)
    if module and kind == "agent":
        return runtime.router.default_agent_id in {module.id, module.registry_id}
    if module and kind == "tts":
        return runtime.tts_registry.default_id in {
            module.id,
            module.registry_id,
            *module.provider_types,
        }
    if module and kind == "stt":
        current = runtime.state.default("stt") or (runtime.cfg.get("stt") or {}).get("provider")
        return current == module.id
    return False


def _schedule(runtime: Any, coroutine: Any, **identity: str) -> Reply:
    """Run a gateway coroutine on the event loop; callers run in a worker thread."""
    try:
        ok = runtime.gateway.schedule(coroutine).result(timeout=5)
    except Exception as exc:  # noqa: BLE001
        return HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)}
    return (HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND), {"ok": ok, **identity}
