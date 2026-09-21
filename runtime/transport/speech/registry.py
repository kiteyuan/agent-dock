"""TTS registry — discover and select TTS providers."""

from __future__ import annotations

from runtime.transport.speech.base import TTSInfo, TTSProvider


class TTSRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, TTSProvider] = {}
        self.default_id: str | None = None

    def register(self, provider: TTSProvider, *, default: bool = False) -> None:
        self._providers[provider.info.id] = provider
        if default:
            self.default_id = provider.info.id

    def unregister(self, tts_id: str) -> None:
        self._providers.pop(tts_id, None)
        if self.default_id == tts_id:
            self.default_id = None

    def get(self, tts_id: str | None = None) -> TTSProvider | None:
        if not self._providers:
            return None
        key = tts_id or self.default_id
        if key is None:
            return None
        return self._providers.get(key)

    def list(self) -> list[TTSInfo]:
        return [p.info for p in self._providers.values()]

    def list_dicts(self) -> list[dict]:
        return [i.model_dump() for i in self.list()]

    def ids(self) -> list[str]:
        return list(self._providers.keys())
