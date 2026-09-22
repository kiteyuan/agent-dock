"""Local-only Admin API/UI plus public pet assets (default :8766)."""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from loguru import logger

from runtime.admin.access import (
    admin_host_allowed,
    admin_peer_allowed,
    admin_token_allowed,
    admin_write_allowed,
)
from runtime.admin.api import api_get, api_post
from runtime.pets import list_pets, load_catalog, resolve_asset

if TYPE_CHECKING:
    from runtime.runtime import Runtime

_ADMIN_STATIC = Path(__file__).resolve().parent / "static"


class _AdminServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        # The browser aborts a snapshot download when it refreshes. That must
        # not be printed as a server crash, and it must not affect :8765.
        exc = sys.exception()
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class _AdminHandler(BaseHTTPRequestHandler):
    runtime: Runtime | None = None
    pets_root: Path = Path("assets/pets")

    def log_message(self, fmt: str, *args: object) -> None:
        # Polling access logs are noise. Keep only HTTP failures.
        if args and str(args[1]).startswith(("4", "5")):
            logger.warning("[admin-http] " + (fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if urlparse(self.path).path.startswith(("/admin", "/api")) or self.path == "/":
            self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'",
        )
        super().end_headers()

    def do_OPTIONS(self) -> None:
        path = unquote(urlparse(self.path).path or "/")
        if path.startswith("/pets"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()
            return
        if not self._admin_allowed():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path or "/")
        if path.startswith("/pets"):
            self._serve_pet(path)
            return
        if path == "/health":
            pets, default = list_pets(self.pets_root)
            self._json(
                HTTPStatus.OK,
                {"ok": True, "admin": True, "pets": len(pets), "default": default},
            )
            return
        if path.startswith("/api/"):
            if self._admin_allowed():
                self._api_get(path)
            return
        if path in ("/", "/admin", "/admin/"):
            if self._admin_allowed():
                self._serve_static("index.html")
            return
        if path.startswith("/admin/"):
            if self._admin_allowed():
                self._serve_static(path[len("/admin/") :])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path or "/")
        if not path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._admin_allowed():
            return
        if not self._admin_write_allowed():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid length"})
            return
        if length > 1024 * 1024:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json"})
            return
        self._api_post(path, body if isinstance(body, dict) else {})

    def _admin_allowed(self) -> bool:
        host = self.headers.get("Host")
        peer = self.client_address[0]
        if (
            admin_peer_allowed(peer)
            and admin_host_allowed(host)
            and admin_token_allowed(self.headers, peer=peer)
        ):
            return True
        self._json(
            HTTPStatus.FORBIDDEN,
            {
                "ok": False,
                "error": (
                    "Admin requires localhost Host and a loopback peer "
                    "(or Docker bridge peer when AGENTDOCK_DOCKER=1)"
                ),
            },
        )
        return False

    def _admin_write_allowed(self) -> bool:
        if admin_write_allowed(self.headers):
            return True
        self._json(
            HTTPStatus.FORBIDDEN,
            {"ok": False, "error": "Admin writes require same-origin browser requests"},
        )
        return False

    def _runtime(self) -> Runtime | None:
        if self.runtime is None:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "runtime not ready"},
            )
        return self.runtime

    def _api_get(self, path: str) -> None:
        api_get(self, path)

    def _api_post(self, path: str, body: dict[str, Any]) -> None:
        api_post(self, path, body)


    def _serve_pet(self, path: str) -> None:
        if path in ("/pets", "/pets/"):
            path = "/pets/catalog.json"
        if path == "/pets/catalog.json":
            self._json(HTTPStatus.OK, load_catalog(self.pets_root), cache=True)
            return
        if not path.startswith("/pets/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        asset = resolve_asset(self.pets_root, path[len("/pets/") :])
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND, "pet asset not found")
            return
        data = asset.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
        )
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, relative: str) -> None:
        value = relative.replace("\\", "/").lstrip("/") or "index.html"
        if ".." in value.split("/"):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        path = (_ADMIN_STATIC / value).resolve()
        try:
            path.relative_to(_ADMIN_STATIC.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, payload: Any, *, cache: bool = False) -> None:
        self.send_response(code)
        if cache:
            self.send_header("Cache-Control", "public, max-age=30")
            self.send_header("Access-Control-Allow-Origin", "*")
        else:
            self.send_header("Cache-Control", "no-store")
        self._write_json_headers(payload)

    def _write_json_headers(self, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_admin_http_server(
    *,
    host: str,
    port: int,
    pets_root: Path,
    runtime: Runtime,
) -> ThreadingHTTPServer:
    _AdminHandler.pets_root = pets_root
    _AdminHandler.runtime = runtime
    server = _AdminServer((host, port), _AdminHandler)
    threading.Thread(
        target=server.serve_forever,
        name="admin-http",
        daemon=True,
    ).start()
    pets, default = list_pets(pets_root)
    logger.info(
        "Admin local-only at http://127.0.0.1:{}/admin/; pets public ({} packs, default={})",
        server.server_port,
        len(pets),
        default,
    )
    return server


__all__ = ["start_admin_http_server"]
