"""Per-agent model settings with OS-user protected credentials."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.llm_providers import SHARED_LLM_PROVIDERS
from runtime.platform.secrets import seal as _seal
from runtime.platform.secrets import unseal as _unseal
from runtime.platform.types import AgentProviderSpec, ModuleSpec


_OPENAI_COMPAT = (
    "openai",
    "openai-compat",
    "gemini",
    "deepseek",
    "moonshot",
    "openrouter",
    "dashscope",
    "modelscope",
    "zhipu",
    "xai",
    "compatible",
)
_SHARED_BY_ID = {item.id: item for item in SHARED_LLM_PROVIDERS}


def _map_shared_to_agent(
    module: ModuleSpec, shared_provider_id: str
) -> AgentProviderSpec | None:
    if module.configuration.mode != "model" or not shared_provider_id:
        return None
    providers = module.configuration.providers
    exact = next((item for item in providers if item.id == shared_provider_id), None)
    if exact:
        return exact
    if shared_provider_id in _OPENAI_COMPAT:
        generic = next(
            (
                item
                for item in providers
                if item.id in ("openai", "openai-compat", "compatible")
            ),
            None,
        )
        if generic:
            return generic
        return next((item for item in providers if item.id in _OPENAI_COMPAT), None)
    return None


class AgentConfigStore:
    """Stores public model choices separately from credentials."""

    def __init__(
        self,
        state_dir: Path,
        catalog: ModuleCatalog,
        *,
        secrets_dir: Path | None = None,
    ) -> None:
        self.path = state_dir / "agent-settings.json"
        self.secret_path = state_dir / "agent-secrets.json"
        self._key_dir = secrets_dir
        self.catalog = catalog
        self._lock = threading.RLock()
        self._settings = self._load(self.path)
        self._secrets = self._load(self.secret_path)

    def public_shared(self) -> dict[str, Any]:
        with self._lock:
            value, provider, has_credential = self._shared_state()
            configured = self._configured(
                "model",
                provider,
                value,
                has_credential=has_credential,
            )
            compatible = [
                spec.id
                for spec in self.catalog.modules_by_kind("agent")
                if provider and _map_shared_to_agent(spec, provider.id)
            ]
            return {
                "configured": configured,
                "provider": value.get("provider")
                or SHARED_LLM_PROVIDERS[0].id,
                "model": value.get("model")
                or (provider.default_model if provider else ""),
                "base_url": value.get("base_url")
                or (provider.default_base_url if provider else ""),
                "has_credential": has_credential,
                "providers": [
                    self._public_provider(item) for item in SHARED_LLM_PROVIDERS
                ],
                "compatible_agents": compatible,
                "updated_at": value.get("updated_at"),
            }

    def public(self, module_id: str) -> dict[str, Any]:
        with self._lock:
            module = self._module(module_id)
            spec = module.configuration
            value = dict((self._settings.get("agents") or {}).get(module_id) or {})
            shared_value, shared_provider, shared_has_credential = self._shared_state()
            shared_configured = self._configured(
                "model",
                shared_provider,
                shared_value,
                has_credential=shared_has_credential,
            )
            mapped = _map_shared_to_agent(
                module, shared_provider.id if shared_provider else ""
            )
            using_shared = value.get("source") == "shared"
            if using_shared:
                provider = mapped
                has_credential = shared_has_credential
                model = str(
                    shared_value.get("model")
                    or (shared_provider.default_model if shared_provider else "")
                    or (provider.default_model if provider else "")
                )
                base_url = str(
                    shared_value.get("base_url")
                    or (
                        shared_provider.default_base_url if shared_provider else ""
                    )
                    or (provider.default_base_url if provider else "")
                )
                configured = bool(mapped) and shared_configured
            else:
                provider = self._provider(module, str(value.get("provider") or ""))
                has_credential = bool(
                    (self._secrets.get("agents") or {}).get(module_id)
                )
                model = value.get("model") or (
                    provider.default_model if provider else ""
                )
                base_url = value.get("base_url") or (
                    provider.default_base_url if provider else ""
                )
                configured = self._configured(
                    spec.mode,
                    provider,
                    value,
                    has_credential=has_credential,
                )
            return {
                "mode": spec.mode,
                "help_url": spec.help_url or module.homepage,
                "source": "shared" if using_shared else "custom",
                "shared_compatible": mapped is not None,
                "provider": (
                    (mapped.id if mapped else None)
                    if using_shared
                    else value.get("provider")
                    or (spec.providers[0].id if spec.providers else None)
                ),
                "model": model,
                "base_url": base_url,
                "has_credential": has_credential,
                "configured": configured,
                "providers": [
                    self._public_provider(item) for item in spec.providers
                ],
                "updated_at": value.get("updated_at"),
            }

    def set_shared(
        self,
        *,
        provider_id: str,
        model: str,
        base_url: str,
        credential: str | None = None,
        clear_credential: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            provider = next(
                (item for item in SHARED_LLM_PROVIDERS if item.id == provider_id),
                None,
            )
            if provider is None:
                raise ValueError("unsupported model provider")
            model, base_url, credential = self._validated_fields(
                provider, model, base_url, credential
            )
            current = self._settings.get("shared") or {}
            provider_changed = current.get("provider") not in (None, provider.id)
            existing_credential = bool(self._secrets.get("shared"))
            will_have_credential = bool(credential) or (
                existing_credential and not clear_credential and not provider_changed
            )
            if provider.credential_required and not will_have_credential:
                raise ValueError("credential is required")
            self._settings["shared"] = {
                "provider": provider.id,
                "model": model,
                "base_url": base_url,
                "updated_at": time.time(),
            }
            if clear_credential or provider_changed:
                self._secrets.pop("shared", None)
            if credential:
                self._secrets["shared"] = _seal(credential, key_dir=self._key_dir)
            self._write(self.path, self._settings)
            self._write(self.secret_path, self._secrets, private=True)
            return self.public_shared()

    def set(
        self,
        module_id: str,
        *,
        provider_id: str = "",
        model: str = "",
        base_url: str = "",
        credential: str | None = None,
        clear_credential: bool = False,
        source: str = "custom",
    ) -> dict[str, Any]:
        with self._lock:
            module = self._module(module_id)
            if module.configuration.mode != "model":
                raise ValueError(f"{module_id} does not support managed model settings")
            if source == "shared":
                return self._bind_shared(module_id, module)
            provider = self._provider(module, provider_id)
            if provider is None:
                raise ValueError("unsupported model provider")
            model, base_url, credential = self._validated_fields(
                provider, model, base_url, credential
            )

            current = (self._settings.get("agents") or {}).get(module_id) or {}
            provider_changed = current.get("source") == "shared" or current.get(
                "provider"
            ) not in (None, provider.id)
            existing_credential = bool(
                (self._secrets.get("agents") or {}).get(module_id)
            )
            will_have_credential = bool(credential) or (
                existing_credential and not clear_credential and not provider_changed
            )
            if provider.credential_required and not will_have_credential:
                raise ValueError("credential is required")

            self._settings.setdefault("agents", {})[module_id] = {
                "source": "custom",
                "provider": provider.id,
                "model": model,
                "base_url": base_url,
                "updated_at": time.time(),
            }
            secrets = self._secrets.setdefault("agents", {})
            if clear_credential or provider_changed:
                secrets.pop(module_id, None)
            if credential:
                secrets[module_id] = _seal(credential, key_dir=self._key_dir)
            self._write(self.path, self._settings)
            self._write(self.secret_path, self._secrets, private=True)
            return self.public(module_id)

    def environment(self, module_id: str) -> dict[str, str]:
        with self._lock:
            module = self.catalog.module(module_id)
            if module is None or module.kind != "agent":
                return {}
            value = dict((self._settings.get("agents") or {}).get(module_id) or {})
            if value.get("source") == "shared":
                shared_value, shared_provider, _has_credential = self._shared_state()
                provider = _map_shared_to_agent(
                    module, shared_provider.id if shared_provider else ""
                )
                if provider is None or shared_provider is None:
                    return {}
                model = str(
                    shared_value.get("model")
                    or shared_provider.default_model
                    or provider.default_model
                ).strip()
                base_url = str(
                    shared_value.get("base_url")
                    or shared_provider.default_base_url
                    or provider.default_base_url
                ).strip()
                sealed = self._secrets.get("shared")
            else:
                provider = self._provider(module, str(value.get("provider") or ""))
                if provider is None:
                    return {}
                model = str(value.get("model") or provider.default_model).strip()
                base_url = str(
                    value.get("base_url") or provider.default_base_url
                ).strip()
                sealed = (self._secrets.get("agents") or {}).get(module_id)
            env = dict(provider.extra_env)
            credential = _unseal(str(sealed), key_dir=self._key_dir) if sealed else ""
            if provider.credential_env and credential:
                env[provider.credential_env] = credential
            if provider.base_url_env and base_url:
                env[provider.base_url_env] = base_url
            if provider.model_env and model:
                env[provider.model_env] = model
            env["AGENTDOCK_AGENT_PROVIDER"] = provider.id
            env["AGENTDOCK_AGENT_MODEL"] = model
            env["AGENTDOCK_AGENT_BASE_URL"] = base_url
            if value.get("source") == "shared":
                env["AGENTDOCK_AGENT_LLM_SOURCE"] = "shared"
            return env

    def using_shared(self) -> list[str]:
        with self._lock:
            agents = self._settings.get("agents") or {}
            return [
                module_id
                for module_id, value in agents.items()
                if isinstance(value, dict) and value.get("source") == "shared"
            ]

    def _bind_shared(self, module_id: str, module: ModuleSpec) -> dict[str, Any]:
        shared_value, shared_provider, has_credential = self._shared_state()
        if not self._configured(
            "model",
            shared_provider,
            shared_value,
            has_credential=has_credential,
        ):
            raise ValueError("shared LLM is not configured")
        mapped = _map_shared_to_agent(
            module, shared_provider.id if shared_provider else ""
        )
        if mapped is None:
            raise ValueError("this agent cannot use the shared LLM")
        self._settings.setdefault("agents", {})[module_id] = {
            "source": "shared",
            "updated_at": time.time(),
        }
        (self._secrets.setdefault("agents", {})).pop(module_id, None)
        self._write(self.path, self._settings)
        self._write(self.secret_path, self._secrets, private=True)
        return self.public(module_id)

    def _shared_state(
        self,
    ) -> tuple[dict[str, Any], AgentProviderSpec | None, bool]:
        raw = self._settings.get("shared")
        value = dict(raw) if isinstance(raw, dict) else {}
        provider_id = str(value.get("provider") or "")
        provider = next(
            (item for item in SHARED_LLM_PROVIDERS if item.id == provider_id),
            SHARED_LLM_PROVIDERS[0] if not provider_id else None,
        )
        has_credential = bool(self._secrets.get("shared"))
        return value, provider, has_credential

    @staticmethod
    def _validated_fields(
        provider: AgentProviderSpec,
        model: str,
        base_url: str,
        credential: str | None,
    ) -> tuple[str, str, str | None]:
        model = model.strip()
        base_url = base_url.strip()
        credential = credential.strip() if credential is not None else None
        if provider.model_required and not model:
            raise ValueError("model is required")
        if len(model) > 200:
            raise ValueError("model is too long")
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("base URL must be HTTP or HTTPS")
            if parsed.username or parsed.password:
                raise ValueError("base URL cannot contain credentials")
        if credential is not None and len(credential) > 8192:
            raise ValueError("credential is too long")
        return model, base_url, credential

    def _module(self, module_id: str) -> ModuleSpec:
        module = self.catalog.module(module_id)
        if module is None or module.kind != "agent":
            raise ValueError("unknown agent")
        return module

    @classmethod
    def _public_provider(cls, item: AgentProviderSpec) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "credential_label": item.credential_label,
            "credential_required": item.credential_required,
            "supports_credential": bool(item.credential_env),
            "supports_base_url": bool(item.base_url_env),
            "default_base_url": item.default_base_url,
            "default_model": item.default_model,
            "model_required": item.model_required,
            "models": cls._model_choices(item),
        }

    @staticmethod
    def _model_choices(item: AgentProviderSpec) -> list[dict[str, str]]:
        source = item
        if not item.models:
            catalog = _SHARED_BY_ID.get(item.models_from or item.id)
            if catalog is not None:
                source = catalog
        return [
            {"id": choice.id, "name": choice.name or choice.id}
            for choice in source.models
        ]

    @staticmethod
    def _provider(
        module: ModuleSpec, provider_id: str
    ) -> AgentProviderSpec | None:
        providers = module.configuration.providers
        if not provider_id and providers:
            return providers[0]
        return next((item for item in providers if item.id == provider_id), None)

    @staticmethod
    def _configured(
        mode: str,
        provider: AgentProviderSpec | None,
        value: dict[str, Any],
        *,
        has_credential: bool,
    ) -> bool:
        if mode != "model":
            return True
        if provider is None:
            return False
        if provider.credential_required and not has_credential:
            return False
        model = str(value.get("model") or provider.default_model).strip()
        return bool(model or not provider.model_required)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"schema_version": 1, "agents": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "agents": {}}
        if not isinstance(value, dict):
            return {"schema_version": 1, "agents": {}}
        value.setdefault("schema_version", 1)
        value.setdefault("agents", {})
        return value

    @staticmethod
    def _write(path: Path, value: dict[str, Any], *, private: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if private and os.name != "nt":
            os.chmod(tmp, 0o600)
        tmp.replace(path)
        if private and os.name != "nt":
            os.chmod(path, 0o600)


__all__ = ["AgentConfigStore", "SHARED_LLM_PROVIDERS"]
