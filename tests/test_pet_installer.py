from __future__ import annotations

import json
import zipfile

import pytest

from runtime.pets.installer import PetInstaller


def test_pet_installer_rejects_bad_ids(tmp_path) -> None:
    installer = PetInstaller(tmp_path)
    with pytest.raises(ValueError):
        installer.install(pet_id="../escape", url="https://example.invalid/pet")


def test_safe_extract_rejects_zip_slip(tmp_path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError):
        PetInstaller._extract_safe(archive, tmp_path / "pet")


def test_catalog_update_is_idempotent(tmp_path) -> None:
    installer = PetInstaller(tmp_path)
    (tmp_path / "catalog.json").write_text(
        json.dumps({"default": "x", "pets": [{"id": "x", "label": "old"}]}),
        encoding="utf-8",
    )
    installer._upsert_catalog("x", "new")
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["default"] == "x"
    assert catalog["pets"] == [
        {
            "id": "x",
            "label": "new",
            "sheet": "x/spritesheet.webp",
            "url": "",
        }
    ]


def test_pet_default_can_be_switched_without_reinstall(tmp_path) -> None:
    installer = PetInstaller(tmp_path)
    for pet_id in ("a", "b"):
        directory = tmp_path / pet_id
        directory.mkdir()
        (directory / "spritesheet.webp").write_bytes(b"webp")
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "default": "a",
                "pets": [{"id": "a"}, {"id": "b"}],
            }
        ),
        encoding="utf-8",
    )

    installer.set_default("b")
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["default"] == "b"
