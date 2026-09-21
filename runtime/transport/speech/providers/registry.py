"""Registration-based speech provider factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from runtime.transport.speech.base import STTProvider, TTSProvider

TTSBuilder = Callable[[str, dict[str, Any]], TTSProvider]
STTBuilder = Callable[[dict[str, Any]], STTProvider]

_TTS: dict[str, TTSBuilder] = {}
_STT: dict[str, STTBuilder] = {}


def register_tts(*names: str) -> Callable[[TTSBuilder], TTSBuilder]:
    def decorator(builder: TTSBuilder) -> TTSBuilder:
        for name in names:
            _TTS[name] = builder
        return builder

    return decorator


def register_stt(*names: str) -> Callable[[STTBuilder], STTBuilder]:
    def decorator(builder: STTBuilder) -> STTBuilder:
        for name in names:
            _STT[name] = builder
        return builder

    return decorator


def build_tts(name: str, provider_id: str, cfg: dict[str, Any]) -> TTSProvider | None:
    builder = _TTS.get(name)
    return builder(provider_id, cfg) if builder else None


def build_stt(name: str, cfg: dict[str, Any]) -> STTProvider | None:
    builder = _STT.get(name)
    return builder(cfg) if builder else None


@register_tts("echo")
def _echo(provider_id: str, cfg: dict[str, Any]) -> TTSProvider:
    from runtime.transport.speech.echo_tts import EchoTTS

    return EchoTTS(tts_id=provider_id, name=cfg.get("name", "Echo TTS"))


@register_tts("edge")
def _edge(provider_id: str, cfg: dict[str, Any]) -> TTSProvider:
    from runtime.transport.speech.edge_tts import EdgeTTS

    return EdgeTTS(
        tts_id=provider_id,
        name=cfg.get("name", "Edge TTS"),
        voice=cfg.get("voice") or cfg.get("model") or "zh-CN-XiaoxiaoNeural",
        voices=list(cfg.get("models") or cfg.get("voices") or []) or None,
    )


@register_tts("gpt-sovits")
def _sovits(provider_id: str, cfg: dict[str, Any]) -> TTSProvider:
    from runtime.transport.speech.gpt_sovits_tts import GPTSoVITSTTS

    return GPTSoVITSTTS(
        tts_id=provider_id,
        name=cfg.get("name"),
        voice_dir=cfg.get("voice_dir")
        or cfg.get("voices_dir")
        or f"voices/{provider_id}",
        url=cfg.get("url") or "http://127.0.0.1:19880",
        api=cfg.get("api") or "v2",
        text_lang=cfg.get("text_lang") or "auto",
        timeout=float(cfg.get("timeout", 120)),
        load_weights=bool(cfg.get("load_weights", True)),
    )


@register_tts("http")
def _http(provider_id: str, cfg: dict[str, Any]) -> TTSProvider:
    from runtime.transport.speech.http_tts import HTTPTTS

    return HTTPTTS(
        url=cfg["url"],
        tts_id=provider_id,
        name=cfg.get("name", "HTTP TTS"),
        model=cfg.get("model"),
        models=list(cfg.get("models") or []),
        headers=dict(cfg.get("headers") or {}),
        timeout=float(cfg.get("timeout", 60)),
    )


@register_stt("whisper")
def _whisper(cfg: dict[str, Any]) -> STTProvider:
    from runtime.transport.speech.whisper_stt import WhisperSTT

    opts = cfg.get("whisper") or cfg
    return WhisperSTT(
        model=opts.get("model", "small"),
        device=opts.get("device", "cpu"),
        language=opts.get("language", "auto"),
        beam_size=int(opts.get("beam_size", 5)),
        vad_filter=bool(opts.get("vad_filter", True)),
        initial_prompt=opts.get("initial_prompt") if "initial_prompt" in opts else None,
        code_switch=bool(opts.get("code_switch"))
        if "code_switch" in opts
        else None,
    )


@register_stt("sensevoice", "funasr")
def _http_stt(cfg: dict[str, Any]) -> STTProvider:
    from runtime.transport.speech.http_stt import HTTPSTT

    provider = str(cfg.get("provider"))
    url = str(cfg.get("url") or "")
    if not url:
        from runtime.platform.catalog import ModuleCatalog

        catalog = ModuleCatalog.load({})
        module = catalog.module(provider)
        if module is None or not module.sidecar_id:
            raise ValueError(f"{provider} has no sidecar")
        url = catalog.service_url(module.sidecar_id, "/v1/stt")
    return HTTPSTT(
        provider_id=provider,
        url=url,
        timeout=float(cfg.get("timeout", 120)),
    )
