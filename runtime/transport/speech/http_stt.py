"""STT client for isolated local speech sidecars."""

from __future__ import annotations

import asyncio
import json
import urllib.request

from runtime.transport.speech.base import STTProvider


class HTTPSTT(STTProvider):
    def __init__(
        self,
        *,
        url: str,
        provider_id: str,
        timeout: float = 120,
    ) -> None:
        self.url = url
        self.provider_id = provider_id
        self.timeout = timeout

    async def transcribe(self, audio: bytes) -> str:
        return await asyncio.to_thread(self._call, audio)

    def _call(self, audio: bytes) -> str:
        request = urllib.request.Request(
            self.url,
            data=audio,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("text") or "")

    def status(self) -> dict[str, object]:
        return {
            "provider": self.provider_id,
            "ready": False,
            "status": "unknown",
            "url": self.url,
        }
