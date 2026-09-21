"""Character pack projection. Readiness follows the selected pet only."""

from __future__ import annotations

from typing import Any


def project_pets(host: Any) -> dict[str, Any]:
    assets = host.assets.snapshot()
    items = assets["pets"]
    default = assets["pet_default"]
    chosen = next((item for item in items if item.get("id") == default), None)
    ready = (
        bool(chosen.get("present"))
        if chosen is not None
        else any(item.get("present") for item in items)
    )
    return {
        "default": default,
        "ready": ready,
        "pets": items,
        "root": str(host.runtime.pets_root),
        "base_url": host.runtime.assets_base_url,
    }
