"""Speech package — keep imports lazy so isolated sidecars stay lean.

Sidecars run under module venvs (SenseVoice/FunASR) that only install engine
deps. Eager imports here previously pulled ``pydantic`` via ``base.py`` and
broke ``python -m runtime.transport.speech.sidecar``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["STTProvider", "TTSInfo", "TTSProvider", "TTSRegistry"]


def __getattr__(name: str) -> Any:
    if name in ("STTProvider", "TTSInfo", "TTSProvider"):
        from runtime.transport.speech.base import STTProvider, TTSInfo, TTSProvider

        return {
            "STTProvider": STTProvider,
            "TTSInfo": TTSInfo,
            "TTSProvider": TTSProvider,
        }[name]
    if name == "TTSRegistry":
        from runtime.transport.speech.registry import TTSRegistry

        return TTSRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
