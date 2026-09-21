"""Shared LLM providers the Admin console can assign to agents."""

from __future__ import annotations

from runtime.platform.types import AgentModelChoice, AgentProviderSpec


def _models(*pairs: tuple[str, str]) -> list[AgentModelChoice]:
    return [AgentModelChoice(id=model_id, name=name) for model_id, name in pairs]


SHARED_LLM_PROVIDERS = [
    AgentProviderSpec(
        id="openai",
        name="OpenAI",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-5.6",
        models=_models(
            ("gpt-6-astra", "GPT-6 Astra"),
            ("gpt-5.6", "GPT-5.6"),
            ("gpt-5.6-terra", "GPT-5.6 Terra"),
            ("gpt-5.6-luna", "GPT-5.6 Luna"),
            ("gpt-5", "GPT-5"),
            ("gpt-5-mini", "GPT-5 Mini"),
            ("gpt-4.1", "GPT-4.1"),
        ),
    ),
    AgentProviderSpec(
        id="anthropic",
        name="Anthropic",
        credential_env="ANTHROPIC_API_KEY",
        base_url_env="ANTHROPIC_BASE_URL",
        default_model="claude-sonnet-5",
        models=_models(
            ("claude-opus-5", "Claude Opus 5"),
            ("claude-sonnet-5", "Claude Sonnet 5"),
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
            ("claude-fable-5-1", "Claude Fable 5.1"),
            ("claude-opus-4-8", "Claude Opus 4.8"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ),
    ),
    AgentProviderSpec(
        id="gemini",
        name="Google Gemini",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.8-flash",
        models=_models(
            ("gemini-3.8-flash", "Gemini 3.8 Flash"),
            ("gemini-3.7-flash", "Gemini 3.7 Flash"),
            ("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
            ("gemini-3.5-flash", "Gemini 3.5 Flash"),
            ("gemini-2.5-pro", "Gemini 2.5 Pro"),
            ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ),
    ),
    AgentProviderSpec(
        id="deepseek",
        name="DeepSeek",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://api.deepseek.com",
        default_model="deepseek-flash",
        models=_models(
            ("deepseek-flash", "DeepSeek Flash"),
            ("deepseek-v4-pro", "DeepSeek V4 Pro"),
        ),
    ),
    AgentProviderSpec(
        id="moonshot",
        name="Kimi / Moonshot",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2.6",
        models=_models(
            ("kimi-k3", "Kimi K3"),
            ("kimi-k2.7-code", "Kimi K2.7 Code"),
            ("kimi-k2.6", "Kimi K2.6"),
            ("kimi-k2.5", "Kimi K2.5"),
        ),
    ),
    AgentProviderSpec(
        id="dashscope",
        name="阿里云百炼",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3-coder-plus",
        models=_models(
            ("qwen3-coder-plus", "Qwen3-Coder Plus"),
            ("qwen3-coder-next", "Qwen3-Coder Next"),
            ("qwen3.7-plus", "Qwen3.7 Plus"),
            ("qwen3.8-max", "Qwen3.8 Max"),
            ("qwen-plus", "Qwen Plus"),
        ),
    ),
    AgentProviderSpec(
        id="zhipu",
        name="智谱 GLM",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5.2",
        models=_models(
            ("glm-5.3", "GLM-5.3"),
            ("glm-5.2", "GLM-5.2"),
            ("glm-4.7", "GLM-4.7"),
        ),
    ),
    AgentProviderSpec(
        id="xai",
        name="xAI Grok",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://api.x.ai/v1",
        default_model="grok-4.6",
        models=_models(
            ("grok-4.6", "Grok 4.6"),
            ("grok-build-0.1", "Grok Build 0.1"),
        ),
    ),
    AgentProviderSpec(
        id="openrouter",
        name="OpenRouter",
        credential_env="OPENROUTER_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-5.6",
        models=_models(
            ("openai/gpt-5.6", "OpenAI GPT-5.6"),
            ("anthropic/claude-sonnet-5", "Anthropic Claude Sonnet 5"),
            ("google/gemini-3.8-flash", "Google Gemini 3.8 Flash"),
            ("deepseek/deepseek-chat", "DeepSeek Chat"),
        ),
    ),
    AgentProviderSpec(
        id="modelscope",
        name="魔搭社区",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        default_base_url="https://api-inference.modelscope.cn/v1",
        default_model="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        models=_models(
            (
                "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                "Qwen3-Coder 480B",
            ),
        ),
    ),
    AgentProviderSpec(
        id="openai-compat",
        name="自定义 OpenAI 兼容服务",
        credential_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        model_env="OPENAI_MODEL",
        model_required=False,
    ),
]
