"""Admin HTML is no longer served over HTTP — console is desk-pet App only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from runtime.admin.http_server import _AdminHandler


def _get(port: int, path: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Host": f"127.0.0.1:{port}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def test_admin_html_paths_return_admin_ui_removed(tmp_path: Path) -> None:
    pets = tmp_path / "pets"
    pets.mkdir()
    _AdminHandler.pets_root = pets
    _AdminHandler.runtime = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AdminHandler)
    port = server.server_address[1]
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ("/", "/admin", "/admin/", "/admin/index.html", "/admin/assets/x.js"):
            status, body = _get(port, path)
            assert status == 404, path
            assert isinstance(body, dict), path
            assert body.get("error") == "admin_ui_removed", path
    finally:
        server.shutdown()
        server.server_close()
