"""Voice packs under voices/<id>/ register without config.yaml entries."""

from __future__ import annotations

from runtime.platform.catalog import ModuleCatalog
from runtime.transport.speech.registry import TTSRegistry
from runtime.transport.speech.voice_catalog import VoiceCatalog


def _pack(root, name: str, body: str, files: dict[str, bytes] | None = None) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "voice.yaml").write_text(body, encoding="utf-8")
    for rel, data in (files or {}).items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def test_folder_pack_registers_without_config(tmp_path) -> None:
    voices = tmp_path / "voices"
    _pack(
        voices,
        "miku",
        "name: Miku\nengine: gpt-sovits\n",
        {
            "models/gpt.ckpt": b"g",
            "models/sovits.pth": b"s",
            "reference/ref.wav": b"w",
        },
    )
    _pack(voices, "broken", "name: Broken\nengine: nope\n")
    catalog = ModuleCatalog.load({})
    registry = TTSRegistry()
    found = VoiceCatalog(voices)
    found.sync(registry, catalog)

    assert registry.get("miku") is not None
    assert registry.get("miku").url.endswith("/v1/tts")
    assert registry.get("miku").default_model.endswith("miku")
    assert registry.get("broken") is None
    by_id = {item.id: item for item in found.records}
    assert by_id["miku"].complete is True
    assert by_id["broken"].complete is False
    assert "未知引擎" in by_id["broken"].detail


def test_removed_pack_is_unregistered(tmp_path) -> None:
    voices = tmp_path / "voices"
    _pack(
        voices,
        "miku",
        "name: Miku\nengine: edge\nvoice: zh-CN-XiaoxiaoNeural\n",
    )
    catalog = ModuleCatalog.load({})
    registry = TTSRegistry()
    found = VoiceCatalog(voices)
    found.sync(registry, catalog)
    assert registry.get("miku") is not None

    (voices / "miku" / "voice.yaml").unlink()
    found.sync(registry, catalog)
    assert registry.get("miku") is None
    assert found.get("miku") is not None
    assert found.get("miku").complete is False
