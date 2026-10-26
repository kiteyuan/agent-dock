"""Local-only Admin API + MCP + public pet assets (default :8766), on aiohttp.

Runs on the Runtime event loop next to the device gateway. Access checks, parsing and
responses stay on the loop; the synchronous Admin/MCP handlers (process control, disk)
are the one explicit thread boundary, via ``asyncio.to_thread``.

The Admin *UI* is not served here — it ships only inside the desk-pet Tauri App
(`desktop/web/console`) and talks to `/api` via the host invoke proxy.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from loguru import logger

from runtime.admin.access import (
    admin_host_allowed,
    admin_peer_allowed,
    admin_token_allowed,
    admin_write_allowed,
    cors_allow_origin,
)
from runtime.admin.api import api_get, api_post
from runtime.mcp import handle_mcp_post
from runtime.pets import list_pets, load_catalog, resolve_asset

if TYPE_CHECKING:
    from runtime.runtime import Runtime

MAX_BODY = 1024 * 1024
RUNTIME_KEY = web.AppKey("runtime", object)
PETS_ROOT_KEY = web.AppKey("pets_root", Path)

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def _json(request: web.Request, status: int, payload: Any, *, cache: bool = False) -> web.Response:
    headers: dict[str, str] = {}
    if cache:
        headers["Cache-Control"] = "public, max-age=30"
        headers["Access-Control-Allow-Origin"] = "*"
    else:
        headers["Cache-Control"] = "no-store"
        allow = cors_allow_origin(request.headers)
        if allow:
            headers["Access-Control-Allow-Origin"] = allow
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
    return web.Response(
        status=status,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        charset="utf-8",
        headers=headers,
    )


def _admin_denied(request: web.Request) -> web.Response | None:
    peer = request.remote or ""
    if (
        admin_peer_allowed(peer)
        and admin_host_allowed(request.headers.get("Host"))
        and admin_token_allowed(request.headers, peer=peer)
    ):
        return None
    return _json(
        request,
        HTTPStatus.FORBIDDEN,
        {"ok": False, "error": "Admin requires localhost Host and a loopback peer"},
    )


def _write_denied(request: web.Request) -> web.Response | None:
    if admin_write_allowed(request.headers):
        return None
    return _json(
        request,
        HTTPStatus.FORBIDDEN,
        {"ok": False, "error": "Admin writes require same-origin browser requests"},
    )


async def _read_body(request: web.Request, *, empty: bytes) -> bytes | web.Response:
    if (request.content_length or 0) > MAX_BODY:
        return _json(request, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False})
    raw = await request.read()
    return raw or empty


@web.middleware
async def _security_headers(request: web.Request, handler: Handler) -> web.StreamResponse:
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        # Framework-raised errors (405, 413, …) get the same JSON shape as ours.
        response = _json(request, exc.status, {"ok": False, "error": exc.reason})
        if "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.path.startswith(("/api", "/mcp")):
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; connect-src 'self'"
        )
    if response.status >= 400:
        # Polling access logs are noise. Keep only HTTP failures.
        logger.warning("[admin-http] {} {} -> {}", request.method, request.path, response.status)
    return response


def _runtime(request: web.Request) -> Any:
    return request.app[RUNTIME_KEY]


def _not_ready(request: web.Request) -> web.Response | None:
    if _runtime(request) is not None:
        return None
    return _json(
        request, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "runtime not ready"}
    )


# ---------------------------------------------------------------- routes


async def options(request: web.Request) -> web.Response:
    path = request.path
    if path.startswith("/pets"):
        return web.Response(
            status=HTTPStatus.NO_CONTENT,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
            },
        )
    if path == "/mcp":
        if denied := _admin_denied(request):
            return denied
        return web.Response(
            status=HTTPStatus.NO_CONTENT,
            headers={
                "Allow": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Mcp-Session-Id",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
            },
        )
    if path.startswith("/api/") and (denied := _admin_denied(request)):
        return denied
    headers = {"Allow": "GET, POST, OPTIONS"}
    allow = cors_allow_origin(request.headers)
    if allow:
        headers.update(
            {
                "Access-Control-Allow-Origin": allow,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-AgentDock-Admin-Token",
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
        )
    return web.Response(status=HTTPStatus.NO_CONTENT, headers=headers)


async def health(request: web.Request) -> web.Response:
    pets, default = list_pets(request.app[PETS_ROOT_KEY])
    return _json(
        request, HTTPStatus.OK, {"ok": True, "admin": True, "pets": len(pets), "default": default}
    )


async def mcp_get(request: web.Request) -> web.Response:
    if denied := _admin_denied(request):
        return denied
    # Streamable HTTP may open SSE; we only speak request/response JSON.
    resp = _json(request, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "use POST JSON-RPC"})
    resp.headers["Allow"] = "POST, OPTIONS"
    return resp


async def mcp_post(request: web.Request) -> web.Response:
    if denied := _admin_denied(request) or _write_denied(request) or _not_ready(request):
        return denied
    raw = await _read_body(request, empty=b"")
    if isinstance(raw, web.Response):
        return raw
    status, payload = await asyncio.to_thread(handle_mcp_post, _runtime(request), raw)
    if payload is None:
        return web.Response(status=status, content_type="application/json", charset="utf-8")
    return _json(request, status, payload)


async def api_get_route(request: web.Request) -> web.Response:
    if denied := _admin_denied(request) or _not_ready(request):
        return denied
    status, payload = await asyncio.to_thread(
        api_get, _runtime(request), request.path, request.query_string
    )
    return _json(request, status, payload)


async def api_post_route(request: web.Request) -> web.Response:
    if denied := _admin_denied(request) or _write_denied(request) or _not_ready(request):
        return denied
    raw = await _read_body(request, empty=b"{}")
    if isinstance(raw, web.Response):
        return raw
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json(request, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json"})
    status, payload = await asyncio.to_thread(
        api_post, _runtime(request), request.path, body if isinstance(body, dict) else {}
    )
    return _json(request, status, payload)


async def admin_ui_removed(request: web.Request) -> web.Response:
    if denied := _admin_denied(request):
        return denied
    return _json(
        request,
        HTTPStatus.NOT_FOUND,
        {
            "ok": False,
            "error": "admin_ui_removed",
            "detail": "Open the desk-pet console window; /admin HTML is not served.",
        },
    )


async def pets(request: web.Request) -> web.Response:
    root = request.app[PETS_ROOT_KEY]
    path = request.path
    if path in ("/pets", "/pets/", "/pets/catalog.json"):
        return _json(request, HTTPStatus.OK, load_catalog(root), cache=True)
    asset = resolve_asset(root, path[len("/pets/") :])
    if asset is None:
        return _json(request, HTTPStatus.NOT_FOUND, {"ok": False, "error": "pet asset not found"})
    data = await asyncio.to_thread(asset.read_bytes)
    return web.Response(
        body=data,
        headers={
            "Content-Type": mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )


async def not_found(request: web.Request) -> web.Response:
    return _json(request, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def build_admin_app(*, pets_root: Path, runtime: Runtime | None) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY + 1, middlewares=[_security_headers])
    app[RUNTIME_KEY] = runtime
    app[PETS_ROOT_KEY] = pets_root

    app.router.add_route("OPTIONS", "/{tail:.*}", options)
    app.router.add_get("/health", health)
    app.router.add_get("/mcp", mcp_get)
    app.router.add_post("/mcp", mcp_post)
    app.router.add_get("/api/{tail:.*}", api_get_route)
    app.router.add_post("/api/{tail:.*}", api_post_route)
    app.router.add_get("/pets", pets)
    app.router.add_get("/pets/{tail:.*}", pets)
    for prefix in ("/", "/admin", "/admin/{tail:.*}"):
        app.router.add_get(prefix, admin_ui_removed)
    app.router.add_route("*", "/{tail:.*}", not_found)
    return app


class AdminHttpServer:
    def __init__(self, runner: web.AppRunner, port: int) -> None:
        self._runner = runner
        self.port = port

    async def close(self) -> None:
        await self._runner.cleanup()


async def start_admin_http_server(
    *,
    host: str,
    port: int,
    pets_root: Path,
    runtime: Runtime,
) -> AdminHttpServer:
    app = build_admin_app(pets_root=pets_root, runtime=runtime)
    runner = web.AppRunner(app, access_log=None, handle_signals=False)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    try:
        await site.start()
    except OSError:
        await runner.cleanup()
        raise
    bound = int(runner.addresses[0][1]) if runner.addresses else port
    pets_list, default = list_pets(pets_root)
    logger.info(
        "Admin API loopback http://127.0.0.1:{}/api/; pets public ({} packs, default={})",
        bound,
        len(pets_list),
        default,
    )
    return AdminHttpServer(runner, bound)


__all__ = ["AdminHttpServer", "build_admin_app", "start_admin_http_server"]
