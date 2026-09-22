"""Pet pack catalog — resources under assets/pets/ served to clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.paths import resolve_pets


def pets_root(cfg: dict[str, Any] | None = None) -> Path:
    return resolve_pets(cfg)


def load_catalog(root: Path) -> dict[str, Any]:
    catalog_path = root / "catalog.json"
    if catalog_path.is_file():
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    # Discover folders with spritesheet.webp
    pets: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            sheet = child / "spritesheet.webp"
            if child.is_dir() and sheet.is_file():
                pets.append(
                    {
                        "id": child.name,
                        "label": child.name,
                        "sheet": f"{child.name}/spritesheet.webp",
                    }
                )
    default = pets[0]["id"] if pets else None
    return {"default": default, "pets": pets}


def list_pets(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    data = load_catalog(root)
    pets = [p for p in (data.get("pets") or []) if isinstance(p, dict) and p.get("id")]
    default = data.get("default")
    if default and not any(p.get("id") == default for p in pets):
        default = pets[0]["id"] if pets else None
    elif not default and pets:
        default = pets[0]["id"]
    return pets, default if isinstance(default, str) else None


def resolve_asset(root: Path, rel: str) -> Path | None:
    """Resolve a path under pets root; reject traversal."""
    rel = str(rel).replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return None
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None
