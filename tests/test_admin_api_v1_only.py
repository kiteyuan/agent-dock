"""Admin HTTP surface is /api/v1 only (legacy aliases removed)."""

from __future__ import annotations

from pathlib import Path

from runtime.admin import api as admin_api


class _FakeHost:
    def __init__(self) -> None:
        self.status: int | None = None
        self.payload: dict | None = None
        self.path = "/api/status"
        self.runtime = object()

    def _runtime(self):
        return None  # early return — we only assert path tables via source

    def _json(self, status, payload):
        self.status = int(status)
        self.payload = payload


def test_devices_page_uses_v1_disconnect() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (
        root / "runtime" / "admin" / "ui" / "src" / "pages" / "DevicesPage.tsx"
    ).read_text(encoding="utf-8")
    assert "/api/v1/devices/${encodeURIComponent(id)}/disconnect" in page
    assert "`/api/devices/" not in page


def test_legacy_get_alias_strings_gone_from_api_module() -> None:
    src = Path(admin_api.__file__).read_text(encoding="utf-8")
    for legacy in (
        '"/api/status"',
        '"/api/agents"',
        '"/api/tts"',
        "legacy_action",
        "_LEGACY_SUNSET",
        '"/api/pets/import"',
    ):
        assert legacy not in src, f"legacy remnant: {legacy}"
    assert '"/api/v1/devices/"' in src or "/api/v1/devices/" in src
    assert "/api/v1/sessions/" in src
