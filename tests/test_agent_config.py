from __future__ import annotations

import json

import pytest

from runtime.platform.agent_config import AgentConfigStore
from runtime.platform.catalog import ModuleCatalog
from runtime.services.supervisor import ServiceSupervisor


def test_agent_model_settings_are_isolated_and_secrets_are_not_public(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    result = store.set(
        "qwen-code",
        provider_id="dashscope",
        model="qwen3-coder-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        credential="secret-qwen-key",
    )
    store.set(
        "kimi-code",
        provider_id="kimi-code",
        model="kimi-for-coding",
        base_url="https://api.kimi.com/coding/v1",
        credential="secret-kimi-key",
    )

    assert result["configured"] is True
    assert result["has_credential"] is True
    assert "credential" not in result
    assert store.environment("gpt-sovits") == {}
    assert store.environment("qwen-code")["OPENAI_API_KEY"] == "secret-qwen-key"
    assert store.environment("kimi-code")["KIMI_MODEL_API_KEY"] == "secret-kimi-key"
    assert "secret-qwen-key" not in store.secret_path.read_text(encoding="utf-8")
    public_file = json.loads(store.path.read_text(encoding="utf-8"))
    assert public_file["agents"]["qwen-code"]["model"] == "qwen3-coder-plus"
    assert "api_key" not in json.dumps(public_file)


def test_agent_model_settings_validate_provider_and_url(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    with pytest.raises(ValueError, match="unsupported model provider"):
        store.set(
            "qwen-code",
            provider_id="unknown",
            model="qwen",
            base_url="",
        )
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        store.set(
            "qwen-code",
            provider_id="dashscope",
            model="qwen",
            base_url="file:///tmp/key",
        )


def test_switching_provider_does_not_reuse_another_provider_credential(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    store.set(
        "qwen-code",
        provider_id="dashscope",
        model="qwen3-coder-plus",
        base_url="",
        credential="dashscope-key",
    )
    with pytest.raises(ValueError, match="credential is required"):
        store.set(
            "qwen-code",
            provider_id="openai",
            model="gpt-5",
            base_url="https://api.openai.com/v1",
        )


def test_shared_llm_can_be_inherited_by_compatible_agents(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    shared = store.set_shared(
        provider_id="openai",
        model="gpt-5",
        base_url="https://api.openai.com/v1",
        credential="shared-openai-key",
    )
    assert shared["configured"] is True
    assert "credential" not in shared
    assert "qwen-code" in shared["compatible_agents"]
    assert "codebuddy" in shared["compatible_agents"]
    assert "qoder" not in shared["compatible_agents"]
    assert "shared-openai-key" not in store.secret_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="cannot use the shared LLM"):
        store.set("qoder", source="shared")

    qwen = store.set("qwen-code", source="shared")
    kimi = store.set("kimi-code", source="shared")
    codebuddy = store.set("codebuddy", source="shared")
    assert qwen["source"] == "shared"
    assert qwen["configured"] is True
    assert qwen["model"] == "gpt-5"
    assert store.environment("qwen-code")["OPENAI_API_KEY"] == "shared-openai-key"
    assert store.environment("qwen-code")["OPENAI_MODEL"] == "gpt-5"
    assert store.environment("kimi-code")["KIMI_MODEL_API_KEY"] == "shared-openai-key"
    assert store.environment("kimi-code")["KIMI_MODEL_PROVIDER_TYPE"] == "openai"
    assert store.environment("codebuddy")["CODEBUDDY_API_KEY"] == "shared-openai-key"
    assert set(store.using_shared()) == {"qwen-code", "kimi-code", "codebuddy"}
    assert kimi["has_credential"] is True
    public_file = json.loads(store.path.read_text(encoding="utf-8"))
    assert public_file["agents"]["qwen-code"] == {
        "source": "shared",
        "updated_at": public_file["agents"]["qwen-code"]["updated_at"],
    }

    store.set_shared(
        provider_id="openai",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
    )
    assert store.environment("qwen-code")["OPENAI_MODEL"] == "gpt-5.6-luna"
    assert store.environment("qwen-code")["OPENAI_API_KEY"] == "shared-openai-key"


def test_shared_llm_catalog_lists_official_providers_and_models(tmp_path) -> None:
    store = AgentConfigStore(tmp_path, ModuleCatalog.load({}))
    shared = store.public_shared()
    providers = {item["id"]: item for item in shared["providers"]}
    assert {
        "openai",
        "anthropic",
        "gemini",
        "deepseek",
        "moonshot",
        "dashscope",
        "zhipu",
        "xai",
        "openrouter",
        "openai-compat",
    } <= set(providers)
    assert providers["openai"]["name"] == "OpenAI"
    assert providers["openai"]["default_base_url"] == "https://api.openai.com/v1"
    assert "gpt-5.6" in {item["id"] for item in providers["openai"]["models"]}
    assert providers["gemini"]["default_base_url"].startswith(
        "https://generativelanguage.googleapis.com/"
    )
    assert "gemini-3.8-flash" in {item["id"] for item in providers["gemini"]["models"]}
    assert providers["deepseek"]["default_base_url"] == "https://api.deepseek.com"
    assert "deepseek-flash" in {item["id"] for item in providers["deepseek"]["models"]}
    assert providers["anthropic"]["default_model"] == "claude-sonnet-5"

    shared = store.set_shared(
        provider_id="gemini",
        model="gemini-3.8-flash",
        base_url="",
        credential="gemini-key",
    )
    assert shared["configured"] is True
    store.set("qwen-code", source="shared")
    env = store.environment("qwen-code")
    assert env["OPENAI_API_KEY"] == "gemini-key"
    assert env["OPENAI_MODEL"] == "gemini-3.8-flash"
    assert "generativelanguage.googleapis.com" in env["OPENAI_BASE_URL"]


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
        provider_id="dashscope",
        model="qwen3-coder-plus",
        base_url="",
        credential="shared-dashscope",
    )
    store.set("qwen-code", source="shared")
    with pytest.raises(ValueError, match="credential is required"):
        store.set(
            "qwen-code",
            source="custom",
            provider_id="dashscope",
            model="qwen3-coder-plus",
            base_url="",
        )


def test_agent_sidecar_receives_only_its_explicit_model_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "global-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "global-anthropic")
    monkeypatch.setenv("PATH", "keep-path")
    env = ServiceSupervisor._child_environment(
        {
            "AGENTDOCK_AGENT_ID": "qwen-code",
            "OPENAI_API_KEY": "qwen-only",
        }
    )
    assert env["OPENAI_API_KEY"] == "qwen-only"
    assert "ANTHROPIC_API_KEY" not in env
    assert env["PATH"] == "keep-path"
