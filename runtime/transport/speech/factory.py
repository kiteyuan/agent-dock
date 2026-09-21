"""Build TTS providers from config."""

from __future__ import annotations

import importlib
from typing import Any

from runtime.transport.speech.base import TTSProvider
from runtime.transport.speech.providers import build_tts


def create_tts(tts_id: str, cfg: dict[str, Any]) -> TTSProvider:
    ptype = cfg.get("type", tts_id)

    built = build_tts(str(ptype), tts_id, cfg)
    if built is not None:
        return built
    if ptype == "import" or ":" in str(ptype):
        path = cfg.get("path") or ptype
        return _load_import(path, cfg, tts_id)
    raise ValueError(f"unknown TTS type: {ptype}")


def _load_import(path: str, cfg: dict[str, Any], tts_id: str) -> TTSProvider:
    if ":" not in path:
        raise ValueError(f"import path must be 'module:Class', got {path!r}")
    mod_name, cls_name = path.rsplit(":", 1)
    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    kwargs = {k: v for k, v in cfg.items() if k not in ("type", "path")}
    kwargs.setdefault("tts_id", tts_id)
    obj = cls(**kwargs)
    if not isinstance(obj, TTSProvider):
        raise TypeError(f"{path} did not return TTSProvider")
    return obj
