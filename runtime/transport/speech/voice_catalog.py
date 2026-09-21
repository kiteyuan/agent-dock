"""Discover speakable voices from voices/<id>/voice.yaml.

A pack names an engine from the module catalog. The catalog's voice_pack
rules decide which files are required and how the pack is bound. config.yaml
does not need a provider entry per character.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.types import ModuleSpec, VoicePackSpec
from runtime.transport.speech.base import TTSProvider
from runtime.transport.speech.registry import TTSRegistry


@dataclass
class VoiceRecord:
    id: str
    name: str
    engine: str
    complete: bool
    detail: str
    provider: TTSProvider | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class VoiceCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.records: list[VoiceRecord] = []
        self._managed: set[str] = set()
        self._signature: tuple[tuple[str, bool, int], ...] | None = None

    def get(self, voice_id: str) -> VoiceRecord | None:
        return next((item for item in self.records if item.id == voice_id), None)

    def sync(self, registry: TTSRegistry, catalog: ModuleCatalog) -> None:
        specs = _load_records(self.root, catalog)
        signature = tuple(
            (item.id, item.complete, _mtime(self.root / item.id / "voice.yaml"))
            for item in specs
        )
        if signature == self._signature:
            return
        complete = {item.id for item in specs if item.provider is not None}
        for stale in self._managed - complete:
            registry.unregister(stale)
        for item in specs:
            if item.provider is not None:
                registry.register(item.provider)
        self._managed = complete
        self.records = specs
        self._signature = signature
        logger.info(
            "voice catalog: {} pack(s), {} ready",
            len(specs),
            len(complete),
        )


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _load_records(root: Path, catalog: ModuleCatalog) -> list[VoiceRecord]:
    if not root.is_dir():
        return []
    records: list[VoiceRecord] = []
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        records.append(_load_one(child, catalog))
    return records


def _load_one(folder: Path, catalog: ModuleCatalog) -> VoiceRecord:
    voice_id = folder.name
    meta_path = folder / "voice.yaml"
    if not meta_path.is_file():
        return VoiceRecord(
            id=voice_id,
            name=voice_id,
            engine="",
            complete=False,
            detail="缺少 voice.yaml",
        )
    try:
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return VoiceRecord(
            id=voice_id,
            name=voice_id,
            engine="",
            complete=False,
            detail=f"voice.yaml 无法解析: {exc}",
        )
    if not isinstance(meta, dict):
        meta = {}
    engine = str(meta.get("engine") or "").strip()
    name = str(meta.get("name") or voice_id)
    module = catalog.module(engine)
    pack = module.voice_pack if module else None
    pack_ids = {item.id for item in catalog.modules if item.voice_pack is not None}
    if voice_id in pack_ids:
        return VoiceRecord(
            id=voice_id,
            name=name,
            engine=engine,
            complete=False,
            detail="目录名与引擎 id 冲突，请换一个音色目录名",
            meta=meta,
        )
    if pack is None:
        return VoiceRecord(
            id=voice_id,
            name=name,
            engine=engine,
            complete=False,
            detail=f"未知引擎: {engine or '(空)'}",
            meta=meta,
        )
    missing = _missing_assets(folder, pack, meta)
    if missing:
        return VoiceRecord(
            id=voice_id,
            name=name,
            engine=engine,
            complete=False,
            detail="缺少 " + ", ".join(missing),
            meta=meta,
        )
    try:
        provider = _build_provider(voice_id, folder, module, pack, meta, catalog)
    except Exception as exc:  # noqa: BLE001
        logger.warning("voice {} failed to load: {}", voice_id, exc)
        return VoiceRecord(
            id=voice_id,
            name=name,
            engine=engine,
            complete=False,
            detail=str(exc),
            meta=meta,
        )
    return VoiceRecord(
        id=voice_id,
        name=name,
        engine=engine,
        complete=True,
        detail="",
        provider=provider,
        meta=meta,
    )


def _missing_assets(folder: Path, pack: VoicePackSpec, meta: dict[str, Any]) -> list[str]:
    missing = [
        field for field in pack.required_fields if not str(meta.get(field) or "").strip()
    ]
    for item in pack.files:
        relative = _lookup(meta, item.id) or item.default
        if not (folder / relative).is_file():
            missing.append(item.id)
    return missing


def _lookup(meta: dict[str, Any], dotted: str) -> str:
    current: Any = meta
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    return str(current or "")


def _build_provider(
    voice_id: str,
    folder: Path,
    module: ModuleSpec,
    pack: VoicePackSpec,
    meta: dict[str, Any],
    catalog: ModuleCatalog,
) -> TTSProvider:
    name = str(meta.get("name") or voice_id)
    if pack.provider == "edge":
        from runtime.transport.speech.edge_tts import EdgeTTS

        voice = str(meta.get("voice") or "").strip()
        return EdgeTTS(tts_id=voice_id, name=name, voice=voice, voices=[voice])
    from runtime.transport.speech.http_tts import HTTPTTS

    if pack.model == "directory":
        model = str(folder)
    elif pack.model == "voice":
        model = str(meta.get("voice") or "").strip() or None
    else:
        model = str(meta.get("model") or meta.get("voice") or "").strip() or None
    return HTTPTTS(
        url=str(meta.get("url") or _engine_url(catalog, module, "/v1/tts")),
        tts_id=voice_id,
        name=name,
        model=model,
        models=[model] if model else [],
        timeout=float(meta.get("timeout", 180)),
    )


def _engine_url(catalog: ModuleCatalog, module: ModuleSpec, suffix: str) -> str:
    sidecar = catalog.sidecar(module.sidecar_id) if module.sidecar_id else None
    if sidecar is None:
        raise ValueError(f"engine {module.id} has no sidecar")
    base = f"http://127.0.0.1:{sidecar.port}"
    if suffix == "/":
        return base
    return base + suffix
