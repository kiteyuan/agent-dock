"""Admin HTTP transport (aiohttp): access gates, CSRF guard, limits, pets, removed UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer
from runtime.admin.http_server import MAX_BODY, build_admin_app


class _Snapshot:
    def build(self) -> Any:
        return SimpleNamespace(model_dump=lambda mode="json": {"ok": True, "snapshot": 1})


class _Mcp:
    def public(self) -> dict[str, Any]:
        return {"servers": []}


def _runtime() -> Any:
    return SimpleNamespace(snapshot=_Snapshot(), mcp=_Mcp(), sync_bundles=lambda: None)


async def _client(tmp_path: Path, runtime: Any) -> TestClient:
    pets = tmp_path / "pets"
    pets.mkdir(exist_ok=True)
    client = TestClient(TestServer(build_admin_app(pets_root=pets, runtime=runtime)))
    await client.start_server()
    return client


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[TestClient]:
    c = await _client(tmp_path, _runtime())
    try:
        yield c
    finally:
        await c.close()


async def test_health_and_security_headers(client: TestClient) -> None:
    resp = await client.get("/health")
    assert resp.status == 200
    assert (await resp.json())["ok"] is True
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_api_get_runs_handler(client: TestClient) -> None:
    resp = await client.get("/api/v1/snapshot")
    assert resp.status == 200
    assert await resp.json() == {"ok": True, "snapshot": 1}
    assert resp.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in resp.headers["Content-Security-Policy"]


async def test_api_rejects_non_loopback_host_header(client: TestClient) -> None:
    resp = await client.get("/api/v1/snapshot", headers={"Host": "evil.example"})
    assert resp.status == 403


async def test_api_write_rejects_cross_site(client: TestClient) -> None:
    resp = await client.post("/api/v1/mcp", data=b"{}", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status == 403
    assert "same-origin" in (await resp.json())["error"]


async def test_api_post_invalid_json(client: TestClient) -> None:
    resp = await client.post("/api/v1/mcp", data=b"{nope")
    assert resp.status == 400
    assert (await resp.json())["error"] == "invalid json"


async def test_body_limit(client: TestClient) -> None:
    resp = await client.post("/api/v1/mcp", data=b"x" * (MAX_BODY + 10))
    assert resp.status == 413


async def test_runtime_not_ready(tmp_path: Path) -> None:
    c = await _client(tmp_path, None)
    try:
        resp = await c.get("/api/v1/snapshot")
        assert resp.status == 503
    finally:
        await c.close()


@pytest.mark.parametrize(
    "path", ["/", "/admin", "/admin/", "/admin/index.html", "/admin/assets/x.js"]
)
async def test_admin_html_paths_return_admin_ui_removed(client: TestClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.status == 404
    assert (await resp.json())["error"] == "admin_ui_removed"


async def test_mcp_get_is_405_and_notification_is_202(client: TestClient) -> None:
    resp = await client.get("/mcp")
    assert resp.status == 405
    assert resp.headers["Allow"] == "POST, OPTIONS"
    resp = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status == 202
    assert await resp.read() == b""


async def test_mcp_ping(client: TestClient) -> None:
    resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status == 200
    assert await resp.json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


async def test_pets_catalog_and_missing_asset(client: TestClient) -> None:
    resp = await client.get("/pets")
    assert resp.status == 200
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
    resp = await client.get("/pets/none/spritesheet.webp")
    assert resp.status == 404


async def test_options_echoes_loopback_origin(client: TestClient) -> None:
    resp = await client.options("/api/v1/snapshot", headers={"Origin": "http://127.0.0.1:5173"})
    assert resp.status == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    resp = await client.options("/api/v1/snapshot", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in resp.headers


async def test_unknown_route_is_json_404(client: TestClient) -> None:
    resp = await client.post("/nope")
    assert resp.status == 404
    assert (await resp.json())["ok"] is False
