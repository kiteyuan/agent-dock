"""TTS provider interfaces and info cards."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class TTSInfo(BaseModel):
    id: str
    name: str
    provider: str
    description: str = ""
    models: list[str] = Field(default_factory=list)
    audio_format: str = "wav"


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes) -> str: ...


class TTSProvider(ABC):
    @property
    @abstractmethod
    def info(self) -> TTSInfo: ...

    @abstractmethod
    async def synthesize(self, text: str, *, model: str | None = None) -> bytes: ...
