from __future__ import annotations

import json

import pytest
from runtime.platform.agent_config import AgentConfigStore
from runtime.platform.catalog import ModuleCatalog
from runtime.services.supervisor import ServiceSupervisor


def test_pi_model_settings_keep_secrets_private(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    result = store.set(
        "pi",
        provider_id="openai",
        model="gpt-4.1",
        base_url="https://api.openai.com/v1",
        credential="secret-pi-key",
    )
    assert result["configured"] is True
    assert result["has_credential"] is True
    assert "credential" not in result
    assert store.environment("pi")["OPENAI_API_KEY"] == "secret-pi-key"
    assert store.environment("pi")["PI_PROVIDER"] == "openai"
    assert "secret-pi-key" not in store.secret_path.read_text(encoding="utf-8")
    public_file = json.loads(store.path.read_text(encoding="utf-8"))
    assert public_file["agents"]["pi"]["model"] == "gpt-4.1"
    assert "api_key" not in json.dumps(public_file)


def test_pi_model_settings_validate_provider_and_url(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    with pytest.raises(ValueError, match="unsupported model provider"):
        store.set(
            "pi",
            provider_id="unknown",
            model="x",
            base_url="",
        )
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        store.set(
            "pi",
            provider_id="openai",
            model="gpt-4.1",
            base_url="file:///tmp/key",
        )


def test_switching_provider_does_not_reuse_another_provider_credential(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    store.set(
        "pi",
        provider_id="anthropic",
        model="claude-sonnet-4",
        base_url="",
        credential="anthropic-key",
    )
    with pytest.raises(ValueError, match="credential is required"):
        store.set(
            "pi",
            provider_id="openai",
            model="gpt-4.1",
            base_url="https://api.openai.com/v1",
        )


def test_shared_llm_can_be_inherited_by_pi(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    shared = store.set_shared(
        provider_id="openai",
        model="gpt-5",
        base_url="https://api.openai.com/v1",
        credential="shared-openai-key",
    )
    assert shared["configured"] is True
    assert "pi" in shared["compatible_agents"]
    assert "shared-openai-key" not in store.secret_path.read_text(encoding="utf-8")

    pi = store.set("pi", source="shared")
    assert pi["source"] == "shared"
    assert pi["configured"] is True
    assert pi["model"] == "gpt-5"
    assert store.environment("pi")["OPENAI_API_KEY"] == "shared-openai-key"
    assert store.environment("pi").get("PI_MODEL") == "gpt-5"
    assert set(store.using_shared()) == {"pi"}

    store.set_shared(
        provider_id="openai",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
    )
    assert store.environment("pi").get("PI_MODEL") == "gpt-5.6-luna"
    assert store.environment("pi")["OPENAI_API_KEY"] == "shared-openai-key"


def test_shared_deepseek_maps_to_pi_native_provider(tmp_path) -> None:
    """Pi has a native deepseek provider; do not force PI_PROVIDER=openai."""
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    store.set_shared(
        provider_id="deepseek",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        credential="sk-deepseek-test",
    )
    store.set("pi", source="shared")
    env = store.environment("pi")
    assert env["PI_PROVIDER"] == "deepseek"
    assert env["PI_MODEL"] == "deepseek-v4-pro"
    assert env["DEEPSEEK_API_KEY"] == "sk-deepseek-test"
    assert env.get("OPENAI_API_KEY") in (None, "")
    assert "PI_THINKING" not in env
    assert "thinking" not in store.public("pi")


def test_leaving_shared_llm_does_not_keep_shared_credential(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    store.set_shared(
        provider_id="openai",
        model="gpt-4.1",
        base_url="https://api.openai.com/v1",
        credential="shared-key",
    )
    store.set("pi", source="shared")
    with pytest.raises(ValueError, match="credential is required"):
        store.set(
            "pi",
            source="custom",
            provider_id="openai",
            model="gpt-4.1",
            base_url="https://api.openai.com/v1",
        )


def test_agent_sidecar_receives_only_its_explicit_model_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "global-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "global-anthropic")
    monkeypatch.setenv("PATH", "keep-path")
    env = ServiceSupervisor._child_environment(
        {
            "AGENTDOCK_AGENT_ID": "pi",
            "OPENAI_API_KEY": "pi-only",
        }
    )
    assert env["OPENAI_API_KEY"] == "pi-only"
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PATH"] == "keep-path"
