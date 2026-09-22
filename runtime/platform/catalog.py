"""Load the built-in module catalog and apply config overrides."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from runtime.platform.types import ModuleSpec, SidecarSpec
from runtime.paths import repo_root, resolve_catalog_path, resolve_vault


def retarget_port(url: str, port: int) -> str:
    """Replace only the URL port. Do not string-replace, so :80 cannot hit :8080."""
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    auth = ""
    if parts.username:
        auth = parts.username
        if parts.password:
            auth += f":{parts.password}"
        auth += "@"
    return urlunsplit(
        (parts.scheme or "http", f"{auth}{host}:{port}", parts.path, parts.query, parts.fragment)
    )


class ModuleCatalog:
    def __init__(
        self,
        *,
        modules: list[ModuleSpec],
        sidecars: list[SidecarSpec],
        root: Path,
    ) -> None:
        self.modules = modules
        self.sidecars = sidecars
        self.root = root
        self._module_by_id = {item.id: item for item in modules}
        self._sidecar_by_id = {item.id: item for item in sidecars}

    @classmethod
    def load(cls, cfg: dict[str, Any] | None = None) -> ModuleCatalog:
        config = cfg or {}
        root = repo_root()
        path = resolve_catalog_path(config)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        documents = [data]
        provider_glob = str(data.get("provider_glob") or "providers/*.yaml")
        for provider_path in sorted(path.parent.glob(provider_glob)):
            document = yaml.safe_load(provider_path.read_text(encoding="utf-8")) or {}
            if isinstance(document, dict):
                documents.append(document)

        raw_sidecars: dict[str, dict[str, Any]] = {}
        raw_modules: list[dict[str, Any]] = []
        for document in documents:
            for sid, raw in (document.get("sidecars") or {}).items():
                if sid in raw_sidecars:
                    raise ValueError(f"duplicate sidecar id in catalog: {sid}")
                raw_sidecars[sid] = dict(raw or {})
            raw_modules.extend(
                item
                for item in (document.get("modules") or [])
                if isinstance(item, dict)
            )

        enabled = data.get("enabled")
        enabled_ids = set(enabled) if isinstance(enabled, list) else None
        if enabled_ids is not None:
            raw_modules = [item for item in raw_modules if item.get("id") in enabled_ids]

        service_overrides = (
            config.get("services") if isinstance(config.get("services"), dict) else {}
        )
        server = config.get("server") if isinstance(config.get("server"), dict) else {}
        sidecars: list[SidecarSpec] = []
        for sid, raw in raw_sidecars.items():
            item = dict(raw or {})
            item["id"] = sid
            override = service_overrides.get(sid)
            if isinstance(override, dict):
                for key in ("port", "autostart", "managed"):
                    if key in override:
                        item[key] = override[key]
            if sid == "runtime":
                item["port"] = int((server or {}).get("port", item.get("port", 8765)))
            elif sid == "admin":
                item["port"] = int(
                    (server or {}).get("assets_port", item.get("port", 8766))
                )
            health = dict(item.get("health") or {})
            if health.get("kind") == "tcp":
                health["port"] = int(item["port"])
            elif health.get("url"):
                health["url"] = retarget_port(str(health["url"]), int(item["port"]))
            item["health"] = health
            sidecars.append(SidecarSpec.model_validate(item))
        ports = [item.port for item in sidecars]
        if len(ports) != len(set(ports)):
            raise ValueError("duplicate sidecar port in provider manifests")

        modules = [ModuleSpec.model_validate(item) for item in raw_modules]
        module_ids = [item.id for item in modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("duplicate module id in provider manifests")
        known = set(module_ids)
        for module in modules:
            missing = set(module.depends_on) - known
            if missing:
                raise ValueError(
                    f"module {module.id} depends on unknown modules: {sorted(missing)}"
                )
            if module.sidecar_id and module.sidecar_id not in {
                item.id for item in sidecars
            }:
                raise ValueError(
                    f"module {module.id} references unknown sidecar {module.sidecar_id}"
                )
            license_ids = {item.id for item in module.licenses}
            if len(license_ids) != len(module.licenses):
                raise ValueError(f"module {module.id} has duplicate license ids")
            provider_ids = {
                item.id for item in module.configuration.providers
            }
            if len(provider_ids) != len(module.configuration.providers):
                raise ValueError(
                    f"module {module.id} has duplicate configuration providers"
                )
            if (
                module.configuration.mode == "model"
                and not module.configuration.providers
            ):
                raise ValueError(
                    f"module {module.id} model configuration has no providers"
                )
            for asset in module.models:
                if asset.license_id and asset.license_id not in license_ids:
                    raise ValueError(
                        f"module {module.id} model {asset.id} references "
                        f"unknown license {asset.license_id}"
                    )
        if enabled_ids is not None:
            missing_enabled = enabled_ids - known
            if missing_enabled:
                raise ValueError(
                    f"enabled modules missing from manifests: {sorted(missing_enabled)}"
                )
            order = {module_id: index for index, module_id in enumerate(enabled)}
            modules.sort(key=lambda item: order[item.id])
        return cls(modules=modules, sidecars=sidecars, root=root)

    def module(self, module_id: str) -> ModuleSpec | None:
        return self._module_by_id.get(module_id)

    def sidecar(self, sidecar_id: str) -> SidecarSpec | None:
        return self._sidecar_by_id.get(sidecar_id)

    def service_url(self, sidecar_id: str, path: str) -> str:
        spec = self.sidecar(sidecar_id)
        if spec is None:
            raise KeyError(sidecar_id)
        suffix = path if path.startswith("/") else f"/{path}"
        return f"http://127.0.0.1:{spec.port}{suffix}"

    def modules_by_kind(self, kind: str) -> list[ModuleSpec]:
        return [item for item in self.modules if item.kind == kind]

    def context(self, cfg: dict[str, Any] | None = None) -> dict[str, str]:
        config = cfg or {}
        services = (
            config.get("services") if isinstance(config.get("services"), dict) else {}
        )
        values = {
            "python": sys.executable,
            "root": str(self.root),
            "workspace": str(resolve_vault(config)),
        }
        for module in self.modules:
            if module.bundle is None or not module.sidecar_id:
                continue
            service = services.get(module.sidecar_id)
            service = service if isinstance(service, dict) else {}
            prefix = module.sidecar_id.replace("-", "_")
            values[f"{prefix}_root"] = str(service.get("root") or "")
            values[f"{prefix}_python"] = str(service.get("python") or "")
        return values
