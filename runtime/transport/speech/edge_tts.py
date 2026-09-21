"""Edge TTS — Microsoft neural voices (online, good Chinese/English default)."""

from __future__ import annotations

from runtime.transport.speech.base import TTSInfo, TTSProvider

# Common voices users can select via tts_model / --tts-model
DEFAULT_VOICES = [
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoyiNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
]


class EdgeTTS(TTSProvider):
    def __init__(
        self,
        tts_id: str = "edge",
        *,
        name: str = "Edge TTS",
        voice: str = "zh-CN-XiaoxiaoNeural",
        voices: list[str] | None = None,
    ) -> None:
        self._id = tts_id
        self._name = name
        self.default_voice = voice
        self._voices = voices or list(DEFAULT_VOICES)
        if self.default_voice not in self._voices:
            self._voices.insert(0, self.default_voice)

    @property
    def info(self) -> TTSInfo:
        return TTSInfo(
            id=self._id,
            name=self._name,
            provider="edge",
            description="Microsoft Edge online neural TTS (mp3).",
            models=list(self._voices),
            audio_format="mp3",
        )

    async def synthesize(self, text: str, *, model: str | None = None) -> bytes:
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError(
                "edge-tts is required for default TTS. Run: pip install -e ."
            ) from exc

        voice = model or self.default_voice
        communicate = edge_tts.Communicate(text, voice)
        chunks: list[bytes] = []
        async for item in communicate.stream():
            if item["type"] == "audio":
                chunks.append(item["data"])
        return b"".join(chunks)
