"""Install a remote pet pack into the host-owned pets directory."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse


class PetInstaller:
    def __init__(self, pets_root: Path) -> None:
        self.pets_root = pets_root.resolve()

    def install(self, *, pet_id: str, url: str, label: str | None = None) -> Path:
        clean_id = self._validate_id(pet_id)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("pet URL must use http or https")
        target = self.pets_root / clean_id
        target.mkdir(parents=True, exist_ok=True)
        tmp = self._download(url)
        try:
            if zipfile.is_zipfile(tmp):
                self._extract_safe(tmp, target)
            else:
                shutil.copy2(tmp, target / "spritesheet.webp")
            sheet = target / "spritesheet.webp"
            if not sheet.is_file():
                nested = next(target.rglob("spritesheet.webp"), None)
                if nested is not None:
                    shutil.copy2(nested, sheet)
            if not sheet.is_file():
                raise ValueError("package does not contain spritesheet.webp")
            self._upsert_catalog(clean_id, label or clean_id)
            return sheet
        finally:
            tmp.unlink(missing_ok=True)

    def set_default(self, pet_id: str) -> None:
        clean_id = self._validate_id(pet_id)
        catalog_path = self.pets_root / "catalog.json"
        if not catalog_path.is_file():
            raise ValueError("pet catalog is missing")
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        known = {
            str(item.get("id"))
            for item in (data.get("pets") or [])
            if isinstance(item, dict)
        }
        if clean_id not in known:
            raise ValueError("unknown pet")
        if not (self.pets_root / clean_id / "spritesheet.webp").is_file():
            raise ValueError("pet spritesheet is missing")
        data["default"] = clean_id
        self._write_catalog(catalog_path, data)

    @staticmethod
    def _validate_id(pet_id: str) -> str:
        value = pet_id.strip()
        if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
            raise ValueError("pet id may contain only letters, numbers, '-' and '_'")
        return value

    @staticmethod
    def _download(url: str) -> Path:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentDock/1.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(256 * 1024 * 1024 + 1)
        if len(data) > 256 * 1024 * 1024:
            raise ValueError("pet package exceeds 256 MiB")
        fd, name = tempfile.mkstemp(suffix=".download")
        __import__("os").close(fd)
        path = Path(name)
        path.write_bytes(data)
        return path

    @staticmethod
    def _extract_safe(archive: Path, target: Path) -> None:
        root = target.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                destination = (root / member.filename).resolve()
                try:
                    destination.relative_to(root)
                except ValueError as exc:
                    raise ValueError("unsafe path in pet archive") from exc
            bundle.extractall(root)

    def _upsert_catalog(self, pet_id: str, label: str) -> None:
        catalog_path = self.pets_root / "catalog.json"
        if catalog_path.is_file():
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        else:
            data = {"default": pet_id, "pets": []}
        pets = [
            item
            for item in (data.get("pets") or [])
            if isinstance(item, dict) and item.get("id") != pet_id
        ]
        pets.append(
            {
                "id": pet_id,
                "label": label,
                "sheet": f"{pet_id}/spritesheet.webp",
                "url": "",
            }
        )
        data["pets"] = pets
        if not data.get("default"):
            data["default"] = pet_id
        self._write_catalog(catalog_path, data)

    @staticmethod
    def _write_catalog(catalog_path: Path, data: dict[str, object]) -> None:
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = catalog_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(catalog_path)
