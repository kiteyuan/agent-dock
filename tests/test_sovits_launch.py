"""External engines are discovered from the catalog bundle declaration."""

from __future__ import annotations

from pathlib import Path

from runtime.platform.bundles import discover_bundle
from runtime.platform.catalog import ModuleCatalog
from runtime.runtime import Runtime


def _bundle(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "api_v2.py").write_text("# stub\n", encoding="utf-8")
    runtime = folder / "runtime"
    runtime.mkdir()
    (runtime / "python.exe").write_bytes(b"")


def _runtime(tmp_path: Path) -> Runtime:
    return Runtime(
        {
            "workspace": {"root": str(tmp_path / "workspace")},
            "pets": {"root": str(tmp_path / "pets")},
            "stt": {"provider": "none"},
            "tts": {"default": "edge", "providers": {"edge": {"type": "edge"}}},
        }
    )


def test_placeholder_comes_from_catalog_not_a_hardcoded_name(tmp_path: Path) -> None:
    spec = ModuleCatalog.load({}).module("gpt-sovits")
    assert spec is not None and spec.bundle is not None
    runtime = _runtime(tmp_path)
    engines = {
        item["id"]: item for item in runtime.snapshot.build().modules["tts"]["engines"]
    }
    folder = tmp_path / "workspace" / spec.bundle.directory
    assert folder.is_dir()
    assert (folder / spec.bundle.note_file).is_file()
    assert engines["gpt-sovits"]["installed"] is False
    assert engines["gpt-sovits"]["install_detail"] == str(folder)
    runtime.lifecycle.close()


def test_nested_extract_is_detected_from_bundle_marker(tmp_path: Path) -> None:
    spec = ModuleCatalog.load({}).module("gpt-sovits")
    assert spec is not None and spec.bundle is not None
    runtime = _runtime(tmp_path)
    nested = tmp_path / "workspace" / spec.bundle.directory / "GPT-SoVITS-v2"
    _bundle(nested)
    ready, root = runtime.bundle_status("gpt-sovits", refresh=True)
    assert ready is True
    assert root == str(nested.resolve())
    found = discover_bundle(tmp_path / "workspace", spec.bundle)
    assert found is not None
    assert found[1].name == "python.exe"
    runtime.lifecycle.close()
