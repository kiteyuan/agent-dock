"""Fast Admin snapshot built only from registries, memory and cached health."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from runtime.admin.projections import (
    project_agents,
    project_pets,
    project_services,
    project_stt,
    project_tts,
)
from runtime.admin.projections.common import agent_is_installed

from runtime.platform.agent_config import AgentConfigStore
from runtime.platform.assets import AssetIndex
from runtime.platform.catalog import ModuleCatalog
from runtime.platform.hardware import HardwareStore
from runtime.platform.health import HealthStore
from runtime.platform.module_state import ModuleState
from runtime.platform.state import RuntimeState
from runtime.platform.types import AdminSnapshot
from runtime.services.supervisor import ServiceSupervisor
from runtime.transport.speech.stt_factory import create_stt

if TYPE_CHECKING:
    from runtime.runtime import Runtime


class SnapshotService:
    def __init__(
        self,
        runtime: Runtime,
        *,
        catalog: ModuleCatalog,
        health: HealthStore,
        supervisor: ServiceSupervisor,
        state: RuntimeState,
        assets: AssetIndex,
        module_state: ModuleState,
        hardware: HardwareStore,
        agent_configs: AgentConfigStore,
    ) -> None:
        self.runtime = runtime
        self.catalog = catalog
        self.health = health
        self.supervisor = supervisor
        self.state = state
        self.assets = assets
        self.module_state = module_state
        self.hardware = hardware
        self.agent_configs = agent_configs

    def apply_persisted_defaults(self) -> None:
        agent = self.state.default("agent")
        if agent:
            if self.runtime.registry.get(agent) is None:
                logger.warning("Ignoring stale default agent override: {}", agent)
            else:
                try:
                    self._ensure_installed("agent", agent)
                except ValueError:
                    logger.warning("Ignoring unavailable default agent override: {}", agent)
                else:
                    self.runtime.router.default_agent_id = agent
                    self.runtime.gateway.default_agent_id = agent
        tts = self.state.default("tts")
        if tts:
            if self.runtime.tts_registry.get(tts) is None:
                logger.warning("Ignoring stale default TTS override: {}", tts)
            else:
                try:
                    self._ensure_installed("tts", tts)
                except ValueError:
                    logger.warning("Ignoring unavailable default TTS override: {}", tts)
                else:
                    self.runtime.tts_registry.default_id = tts
        stt = self.state.default("stt")
        if stt:
            try:
                self._ensure_installed("stt", stt)
                self._set_stt(stt)
            except ValueError:
                logger.warning("Ignoring stale default STT override: {}", stt)

    def set_default(self, kind: str, value: str | None) -> None:
        if value:
            self._ensure_licenses(kind, value)
            self._ensure_installed(kind, value)
        if kind == "agent":
            if not value or self.runtime.registry.get(value) is None:
                raise ValueError("unknown agent")
            self.runtime.router.default_agent_id = value
            self.runtime.gateway.default_agent_id = value
        elif kind == "tts":
            voice = self.runtime.voices.get(value) if value else None
            if voice:
                if not voice.complete:
                    raise ValueError(voice.detail or "voice pack is incomplete")
                self._ensure_licenses("tts", voice.engine)
                self._ensure_installed("tts", voice.engine)
            if value and self.runtime.tts_registry.get(value) is None:
                raise ValueError("unknown tts")
            self.runtime.tts_registry.default_id = value
        elif kind == "stt":
            if not value:
                raise ValueError("STT default cannot be empty")
            self._set_stt(value)
        elif kind == "pet":
            if not value:
                raise ValueError("character cannot be empty")
            # Pet default lives in pets/catalog.json, not runtime-state.json.
            self.runtime.pet_installer.set_default(value)
            self.assets.refresh()
            self._broadcast_defaults(kind)
            return
        else:
            raise ValueError(f"unsupported default kind: {kind}")
        self.state.set_default(kind, value)
        if kind in ("agent", "tts"):
            self._broadcast_defaults(kind)

    def _broadcast_defaults(self, kind: str) -> None:
        coroutine = self.runtime.gateway.broadcast_defaults(kind)
        try:
            self.runtime.gateway.schedule(coroutine)
        except RuntimeError:
            coroutine.close()

    def _ensure_licenses(self, kind: str, value: str) -> None:
        module = next(
            (
                item
                for item in self.catalog.modules_by_kind(kind)
                if item.id == value
                or item.registry_id == value
                or value in item.provider_types
            ),
            None,
        )
        if module is None:
            return
        missing = [
            license.id
            for license in module.licenses
            if license.requires_acceptance
            and not self.module_state.accepted(module.id, license.id)
        ]
        if missing:
            raise ValueError(
                f"license acceptance required: {', '.join(missing)}"
            )

    def _ensure_installed(self, kind: str, value: str) -> None:
        module = next(
            (
                item
                for item in self.catalog.modules_by_kind(kind)
                if item.id == value
                or item.registry_id == value
                or value in item.provider_types
            ),
            None,
        )
        if (
            module
            and module.kind != "agent"
            and module.install.kind == "steps"
            and (
                self.module_state.receipt(module.id) is None
                or not (self.runtime.workspace / "modules" / module.id).is_dir()
            )
        ):
            raise ValueError(f"{module.id} is not installed")
        if module and module.kind == "agent":
            installed, detail = self._agent_installed(module)
            if not installed:
                raise ValueError(detail or f"{module.id} is not installed")

    def _set_stt(self, value: str) -> None:
        module = self.catalog.module(value)
        if module is None or module.kind != "stt":
            raise ValueError("unknown stt")
        config = dict(self.runtime.cfg.get("stt") or {})
        config["provider"] = value
        if module.sidecar_id:
            sidecar = self.catalog.sidecar(module.sidecar_id)
            if sidecar:
                config["url"] = self.catalog.service_url(module.sidecar_id, "/v1/stt")
        provider = create_stt(config)
        self.runtime.stt = provider
        self.runtime.gateway.stt = provider

    def build(self) -> AdminSnapshot:
        services = project_services(self)
        service_by_id = {item["id"]: item for item in services}
        modules = {
            "agents": project_agents(self, service_by_id),
            "tts": project_tts(self, service_by_id),
            "stt": project_stt(self, service_by_id),
            "pets": project_pets(self),
            "llm": {"shared": self.agent_configs.public_shared()},
        }
        devices = self.runtime.gateway.list_devices()
        sessions = self.runtime.sessions.list_dicts()
        expected = [item for item in services if item["expected"]]
        return AdminSnapshot(
            defaults={
                "agent": self.runtime.router.default_agent_id,
                "tts": self.runtime.tts_registry.default_id,
                "stt": (
                    self.state.default("stt")
                    or str((self.runtime.cfg.get("stt") or {}).get("provider") or "off")
                ),
            },
            counts={
                "devices_online": len(devices),
                "sessions_active": len(sessions),
                "services_ready": sum(1 for item in expected if item["healthy"]),
                "services_total": len(expected),
            },
            modules=modules,
            services=services,
            devices=devices,
            sessions=sessions,
            hardware=self.hardware.snapshot(),
            recommendations=self.hardware.recommendations(),
            meta={
                "workspace": str(self.runtime.workspace),
                "pets_root": str(self.runtime.pets_root),
                "assets_base_url": self.runtime.assets_base_url,
                "state_file": str(self.state.path),
                "module_state_file": str(self.module_state.path),
                "agent_settings_file": str(self.agent_configs.path),
                "mcp_file": str(self.runtime.mcp.path),
            },
        )

    def _agent_installed(self, spec: Any) -> tuple[bool, str]:
        return agent_is_installed(self, spec)
