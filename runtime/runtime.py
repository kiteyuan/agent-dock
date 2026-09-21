"""Runtime facade — wires Session, Registry, Router, TTS, Pipeline, Gateway."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from runtime.admin.http_server import start_admin_http_server
from runtime.admin.snapshot import SnapshotService
from runtime.agent.registry import AgentRegistry
from runtime.agent.router import AgentRouter
from runtime.assembly import (
    bind_catalog_endpoints,
    register_agents,
    register_tts,
    stt_config,
)
from runtime.bridge.pipeline import BridgePipeline
from runtime.device.gateway import DeviceGateway
from runtime.pets import pets_root as resolve_pets_root
from runtime.pets.installer import PetInstaller
from runtime.pets.urls import build_assets_base_url
from runtime.platform.agent_config import AgentConfigStore
from runtime.platform.mcp_config import McpConfigStore
from runtime.platform.assets import AssetIndex
from runtime.platform.bundles import BundleBinder
from runtime.platform.catalog import ModuleCatalog
from runtime.platform.hardware import HardwareStore
from runtime.platform.health import HealthStore
from runtime.platform.installer import InstallManager
from runtime.platform.lifecycle import ModuleLifecycle
from runtime.platform.module_state import ModuleState
from runtime.platform.state import RuntimeState
from runtime.security.auth import DeviceAuth
from runtime.security.permissions import PermissionGuard
from runtime.services import ServiceSupervisor
from runtime.session.manager import SessionManager
from runtime.transport.speech.registry import TTSRegistry
from runtime.transport.speech.stt_factory import create_stt
from runtime.transport.speech.voice_catalog import VoiceCatalog
from runtime.workspace import resolve_workspace


class Runtime:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.catalog = ModuleCatalog.load(cfg)
        session_cfg = cfg.get("session") or {}
        self.sessions = SessionManager(max_context=int(session_cfg.get("max_context", 40)))
        self.registry = AgentRegistry()
        self.tts_registry = TTSRegistry()
        self.permissions = PermissionGuard()
        self.auth = self._build_auth(cfg.get("security", {}))
        register_agents(self.registry, cfg.get("agent", {}))
        register_tts(self.tts_registry, cfg.get("tts", {}))
        bind_catalog_endpoints(self.catalog, self.registry, self.tts_registry)
        self.voices = VoiceCatalog(self.catalog.root / "voices")
        self.voices.sync(self.tts_registry, self.catalog)
        default_id = (
            cfg.get("agent", {}).get("default")
            or (self.registry.ids()[0] if self.registry.ids() else "pi")
        )
        self.router = AgentRouter(
            self.registry, default_agent_id=default_id, permissions=self.permissions
        )
        self.stt = create_stt(stt_config(self.catalog, cfg.get("stt", {})))
        self.workspace = resolve_workspace(cfg, ensure=True)
        self.pipeline = BridgePipeline(
            self.router,
            tts_registry=self.tts_registry,
            workspace=str(self.workspace),
        )
        self.pipeline.prepare_turn = self._prepare_turn_sidecars
        server = cfg.get("server", {})
        network = cfg.get("network", {})
        self.pets_root = resolve_pets_root(cfg)
        self.assets_port = int(server.get("assets_port", 8766))
        self.assets_base_url = build_assets_base_url(
            host_hint=server.get("host", "0.0.0.0"),
            port=self.assets_port,
            advertise_url=network.get("advertise_url"),
            assets_url=network.get("assets_url"),
        )
        self._admin_httpd = None
        self._warm_tasks: list[asyncio.Task] = []
        self.agent_configs = AgentConfigStore(self.workspace, self.catalog)
        self.mcp = McpConfigStore(self.workspace)
        self.services = ServiceSupervisor(
            cfg,
            catalog=self.catalog,
            environment_resolver=self._service_environment,
        )
        health_cfg = cfg.get("health") if isinstance(cfg.get("health"), dict) else {}
        self.health = HealthStore(
            self.catalog,
            interval_seconds=float((health_cfg or {}).get("interval_seconds", 3)),
        )
        self.assets = AssetIndex(
            root=self.catalog.root,
            pets_root=self.pets_root,
            interval_seconds=float((health_cfg or {}).get("asset_interval_seconds", 5)),
            on_refresh=self.sync_voices,
        )
        self.hardware = HardwareStore(
            workspace=self.workspace,
            catalog=self.catalog,
        )
        self.state = RuntimeState(self.workspace)
        self.bundles = BundleBinder(
            self.catalog,
            self.workspace,
            [self.cfg, self.services.cfg],
            self.services.refresh_context,
        )
        self.bundles.sync()
        self.module_state = ModuleState(self.workspace)
        self.pet_installer = PetInstaller(self.pets_root)
        self.installer = InstallManager(
            catalog=self.catalog,
            workspace=self.workspace,
            state=self.module_state,
            proxy=(
                (cfg.get("modules") or {}).get("proxy")
                if isinstance(cfg.get("modules"), dict)
                else None
            ),
        )
        self.lifecycle = ModuleLifecycle(
            catalog=self.catalog,
            supervisor=self.services,
            health=self.health,
            pet_installer=self.pet_installer,
            installer=self.installer,
            asset_invalidate=self.assets.invalidate,
            receipt_lookup=lambda module_id: self.module_state.receipt(module_id) is not None,
        )
        self.gateway = DeviceGateway(
            host=server.get("host", "0.0.0.0"),
            port=server.get("port", 8765),
            sessions=self.sessions,
            auth=self.auth,
            pipeline=self.pipeline,
            registry=self.registry,
            tts_registry=self.tts_registry,
            stt=self.stt,
            advertise_url=network.get("advertise_url"),
            pets_root=self.pets_root,
            assets_port=self.assets_port,
            assets_base_url=self.assets_base_url,
            default_agent_id=self.router.default_agent_id,
        )
        self.snapshot = SnapshotService(
            self,
            catalog=self.catalog,
            health=self.health,
            supervisor=self.services,
            state=self.state,
            assets=self.assets,
            module_state=self.module_state,
            hardware=self.hardware,
            agent_configs=self.agent_configs,
        )
        self.snapshot.apply_persisted_defaults()

    def sync_bundles(self) -> None:
        self.bundles.sync()

    def sync_voices(self) -> None:
        """Refresh voice packs into the TTS registry (never from Admin snapshot reads)."""
        self.voices.sync(self.tts_registry, self.catalog)

    def bundle_status(self, module_id: str, *, refresh: bool = False) -> tuple[bool, str]:
        return self.bundles.status(module_id, refresh=refresh)

    async def start(self) -> None:
        stt_cfg = self.cfg.get("stt") or {}
        tts_cfg = self.cfg.get("tts") or {}
        warm_stt = bool(stt_cfg.get("warm", True))
        defer_warm = bool(stt_cfg.get("defer_warm", True))
        warm_tts = bool(tts_cfg.get("warm", True))

        self.health.start()
        self.assets.start()
        self.hardware.start()
        try:
            self._admin_httpd = start_admin_http_server(
                host=self.cfg.get("server", {}).get("host", "0.0.0.0"),
                port=self.assets_port,
                pets_root=self.pets_root,
                runtime=self,
            )
        except OSError:
            logger.exception(
                "Admin HTTP failed to bind :{} — pets/admin UI unavailable",
                self.assets_port,
            )

        if self.stt is not None and warm_stt and hasattr(self.stt, "warm"):
            if defer_warm:
                logger.info("STT warm deferred — gateway opens while model loads")
                self._warm_tasks.append(asyncio.create_task(self._warm_stt()))
            else:
                try:
                    await asyncio.to_thread(self.stt.warm)
                except Exception:  # noqa: BLE001
                    logger.exception("STT warm-up failed; will load on first audio")

        if warm_tts:
            self._warm_tasks.append(asyncio.create_task(self._warm_default_tts()))

        # Autostart uses the same background lifecycle as Admin actions.
        for service in self.catalog.sidecars:
            if not service.managed or not service.autostart:
                continue
            module = next(
                (
                    item
                    for item in self.catalog.modules
                    if item.sidecar_id == service.id
                ),
                None,
            )
            target = module.id if module else service.id
            self.lifecycle.submit("start", target)

        logger.info(
            "AgentDock Runtime ready | agents={} | tts={} | default_agent={} | default_tts={} | workspace={} | pets={} | admin=http://127.0.0.1:{}/admin/",
            self.registry.ids(),
            self.tts_registry.ids(),
            self.router.default_agent_id,
            self.tts_registry.default_id,
            self.workspace,
            self.pets_root,
            self.assets_port,
        )
        try:
            await self.gateway.start()
        finally:
            for task in self._warm_tasks:
                task.cancel()
            if self._warm_tasks:
                await asyncio.gather(*self._warm_tasks, return_exceptions=True)
            self._warm_tasks.clear()
            self.health.stop()
            self.assets.stop()
            self.lifecycle.close()
            self.services.stop_all()
            if self._admin_httpd is not None:
                self._admin_httpd.shutdown()
                self._admin_httpd = None

    async def _warm_stt(self) -> None:
        try:
            await asyncio.to_thread(self.stt.warm)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.exception("STT warm-up failed; will load on first audio")

    async def _warm_default_tts(self) -> None:
        tts = self.tts_registry.get(self.tts_registry.default_id)
        if tts is None or not hasattr(tts, "warm"):
            return
        try:
            await tts.warm()  # type: ignore[attr-defined]
            logger.info("TTS warm done: {}", tts.info.id)
        except Exception:  # noqa: BLE001
            logger.warning("TTS warm skipped/failed for {} — first utterance may be cold", tts.info.id)

    def _service_environment(self, module_id: str) -> dict[str, str]:
        env = self.agent_configs.environment(module_id)
        module = self.catalog.module(module_id)
        if module is not None and module.kind == "agent":
            env["AGENTDOCK_MCP_CONFIG"] = str(self.mcp.path)
        return env

    def _prepare_turn_sidecars(self, agent_id: str | None, tts_id: str | None) -> None:
        self._ensure_sidecar(agent_id)
        self._ensure_sidecar(self._tts_engine_id(tts_id))
        self._ensure_sidecar(self._current_stt_id())

    def _tts_engine_id(self, tts_id: str | None) -> str | None:
        """Map a voice-pack registry id (e.g. Haibara) to its engine module id."""
        if not tts_id:
            return None
        voice = self.voices.get(tts_id)
        if voice is not None and voice.engine:
            return voice.engine
        return tts_id

    def _current_stt_id(self) -> str | None:
        override = self.state.default("stt")
        if override and override != "none":
            return override
        provider = (self.cfg.get("stt") or {}).get("provider")
        if provider and provider != "none":
            return str(provider)
        return None

    def _ensure_sidecar(self, module_id: str | None) -> None:
        if not module_id:
            return
        module = self.catalog.module(module_id)
        if module is None:
            module = next(
                (
                    item
                    for item in self.catalog.modules
                    if item.registry_id == module_id
                ),
                None,
            )
        if module is None or not module.sidecar_id:
            return
        result = self.services.ensure_listening(module.sidecar_id)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or f"{module.sidecar_id} is not listening")

    def _build_auth(self, sec: dict[str, Any]) -> DeviceAuth:
        return DeviceAuth(
            require_token=bool(sec.get("require_token", False)),
            tokens=list(sec.get("tokens") or []),
        )
