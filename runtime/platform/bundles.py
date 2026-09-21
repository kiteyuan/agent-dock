"""Discover user-extracted upstream programs declared by module bundles."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.types import BundleSpec


def placeholder_dir(workspace: Path, bundle: BundleSpec) -> Path:
    return workspace / bundle.directory


def ensure_placeholder(workspace: Path, bundle: BundleSpec) -> Path:
    folder = placeholder_dir(workspace, bundle)
    folder.mkdir(parents=True, exist_ok=True)
    if bundle.note_file and bundle.note and not (folder / bundle.note_file).is_file():
        (folder / bundle.note_file).write_text(bundle.note.strip() + "\n", encoding="utf-8")
    return folder


def discover_bundle(workspace: Path, bundle: BundleSpec) -> tuple[Path, Path] | None:
    """Return ``(package_root, python)`` when the declared marker is present."""
    base = ensure_placeholder(workspace, bundle)
    candidates = [base]
    if bundle.nested:
        candidates.extend(path for path in base.iterdir() if path.is_dir())
    for folder in candidates:
        if not (folder / bundle.marker).is_file():
            continue
        python = _find_python(folder, bundle)
        if python is not None:
            return folder.resolve(), python
    return None


class BundleBinder:
    """Cache bundle discovery and publish the result into sidecar config."""

    def __init__(
        self,
        catalog: ModuleCatalog,
        workspace: Path,
        configs: list[dict[str, Any]],
        refresh_services: Callable[[], None],
    ) -> None:
        self.catalog = catalog
        self.workspace = workspace
        self._configs = configs
        self._refresh_services = refresh_services
        self._cache: dict[str, tuple[bool, str]] = {}
        self._lock = threading.Lock()

    def sync(self) -> None:
        for module in self.catalog.modules:
            if module.bundle is not None:
                self.status(module.id, refresh=True)

    def status(self, module_id: str, *, refresh: bool = False) -> tuple[bool, str]:
        if not refresh:
            cached = self._cache.get(module_id)
            if cached is not None:
                return cached
        with self._lock:
            if not refresh:
                cached = self._cache.get(module_id)
                if cached is not None:
                    return cached
            spec = self.catalog.module(module_id)
            if spec is None or spec.bundle is None or not spec.sidecar_id:
                result = (False, "")
                self._cache[module_id] = result
                return result
            found = discover_bundle(self.workspace, spec.bundle)
            expected = placeholder_dir(self.workspace, spec.bundle)
            root = str(found[0]) if found else ""
            python = str(found[1]) if found else ""
            result = (True, root) if found else (False, str(expected))
            for cfg in self._configs:
                services = cfg.setdefault("services", {})
                current = dict(services.get(spec.sidecar_id) or {})
                if current.get("root") == root and current.get("python") == python:
                    continue
                current["root"] = root
                current["python"] = python
                services[spec.sidecar_id] = current
            self._refresh_services()
            self._cache[module_id] = result
            return result


def _find_python(root: Path, bundle: BundleSpec) -> Path | None:
    for relative in (bundle.python, *bundle.python_fallbacks):
        candidate = root / relative
        if candidate.is_file():
            return candidate.resolve()
    return None
