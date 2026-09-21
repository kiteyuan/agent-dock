"""Build STT providers from config."""

from __future__ import annotations

from typing import Any

from runtime.transport.speech.base import STTProvider
from runtime.transport.speech.providers import build_stt


def create_stt(cfg: dict[str, Any] | None = None) -> STTProvider | None:
    config = cfg or {}
    provider = config.get("provider", "whisper")
    if provider in (None, "none", "off", ""):
        return None
    built = build_stt(str(provider), config)
    if built is not None:
        return built
    if provider == "import" or ":" in str(provider):
        import importlib

        path = config.get("path") or provider
        if ":" not in str(path):
            raise ValueError("STT import path must be module:Class")
        module_name, class_name = str(path).rsplit(":", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        kwargs = {
            key: value
            for key, value in config.items()
            if key not in ("provider", "path")
        }
        instance = cls(**kwargs)
        if not isinstance(instance, STTProvider):
            raise TypeError(f"{path} did not return STTProvider")
        return instance
    raise ValueError(f"unknown STT provider: {provider}")
