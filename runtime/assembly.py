"""Wire catalog modules onto the agent and speech registries.

The Runtime object owns lifecycle. This module only decides which adapter
each catalog entry becomes, and which local sidecar URL replaces a loopback
address already present in config.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from runtime.agent.adapters.http import HTTPAgent
from runtime.agent.factory import create_agent
from runtime.agent.registry import AgentRegistry
from runtime.platform.catalog import ModuleCatalog
from runtime.transport.speech.factory import create_tts
from runtime.transport.speech.registry import TTSRegistry


def register_agents(registry: AgentRegistry, agent_cfg: dict[str, Any]) -> None:
    agents = agent_cfg.get("agents") or {}
    for aid, acfg in agents.items():
        registry.register(create_agent(aid, acfg or {}))


def register_tts(tts_registry: TTSRegistry, tts_cfg: dict[str, Any]) -> None:
    provider = tts_cfg.get("provider", "none")
    providers = tts_cfg.get("providers")

    # Legacy single-provider form: tts.provider: echo
    if not providers:
        if provider in (None, "none", "off", ""):
            return
        providers = {provider: {"type": provider, **(tts_cfg.get(provider) or {})}}

    default = tts_cfg.get("default", provider)
    enable_default = default not in (None, "none", "off", "")

    for tid, tcfg in providers.items():
        ptype = (tcfg or {}).get("type", tid)
        if ptype in (None, "none", "off"):
            continue
        engine = create_tts(tid, tcfg or {})
        tts_registry.register(engine, default=(enable_default and tid == default))


def stt_config(catalog: ModuleCatalog, raw: dict[str, Any]) -> dict[str, Any]:
    config = dict(raw or {})
    provider = str(config.get("provider") or "")
    module = catalog.module(provider)
    if module and module.sidecar_id and not config.get("url"):
        config["url"] = catalog.service_url(module.sidecar_id, "/v1/stt")
    return config


def bind_catalog_endpoints(
    catalog: ModuleCatalog,
    registry: AgentRegistry,
    tts_registry: TTSRegistry,
) -> None:
    """Local addresses come from the sidecar port. A remote host in config is kept."""
    for module in catalog.modules_by_kind("agent"):
        agent_id = module.registry_id or module.id
        if not module.sidecar_id or catalog.sidecar(module.sidecar_id) is None:
            continue
        run_url = catalog.service_url(module.sidecar_id, "/v1/agent/run")
        cancel_url = catalog.service_url(module.sidecar_id, "/v1/agent/cancel")
        current = registry.get(agent_id)
        if isinstance(current, HTTPAgent) and _loopback(current.url):
            current.url = run_url
            current.cancel_url = cancel_url
            continue
        if current is not None:
            continue
        registry.register(
            create_agent(
                agent_id,
                {
                    "type": "http",
                    "name": module.name,
                    "url": run_url,
                    "cancel_url": cancel_url,
                    "mode": "stream",
                    "timeout": 600,
                },
            )
        )
    for module in catalog.modules_by_kind("tts"):
        tts_id = module.registry_id
        if (
            not tts_id
            or not module.sidecar_id
            or catalog.sidecar(module.sidecar_id) is None
            or tts_registry.get(tts_id) is not None
        ):
            continue
        tts_registry.register(
            create_tts(
                tts_id,
                {
                    "type": "http",
                    "name": module.name,
                    "url": catalog.service_url(module.sidecar_id, "/v1/tts"),
                    "timeout": 180,
                },
            )
        )


def _loopback(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"} or host.startswith("127.")
