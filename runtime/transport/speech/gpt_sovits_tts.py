"""GPT-SoVITS TTS — uses a voice pack under voices/<name>/ + local API."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from runtime.transport.speech.base import TTSInfo, TTSProvider


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class GPTSoVITSTTS(TTSProvider):
    """Call GPT-SoVITS HTTP API using models/reference from a voice pack."""

    def __init__(
        self,
        tts_id: str,
        *,
        name: str | None = None,
        voice_dir: str | Path,
        url: str = "http://127.0.0.1:19880",
        api: str = "v2",
        text_lang: str = "auto",
        timeout: float = 120,
        load_weights: bool = True,
    ) -> None:
        self._id = tts_id
        self.url = url.rstrip("/")
        self.api = api
        self.text_lang = text_lang
        self.timeout = timeout
        self.load_weights = load_weights
        self._weights_loaded = False

        root = Path(voice_dir)
        if not root.is_absolute():
            root = _repo_root() / root
        self.voice_dir = root.resolve()
        meta_path = self.voice_dir / "voice.yaml"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}

        self._name = name or str(meta.get("name") or tts_id)
        models = meta.get("models") or {}
        ref = meta.get("reference") or {}
        defaults = meta.get("inference_defaults") or {}

        self.gpt_path = self._resolve(models.get("gpt") or "models/gpt.ckpt")
        self.sovits_path = self._resolve(models.get("sovits") or "models/sovits.pth")
        self.ref_wav = self._resolve(ref.get("wav") or "reference/ref.wav")
        self.prompt_text = str(ref.get("text") or "")
        self.prompt_lang = str(ref.get("language") or text_lang)
        self.top_k = int(defaults.get("top_k", 5))
        self.top_p = float(defaults.get("top_p", 0.7))
        self.temperature = float(defaults.get("temperature", 0.5))
        self.speed = float(defaults.get("speed", 1.0))

    def _resolve(self, rel: str) -> Path:
        p = Path(rel)
        if not p.is_absolute():
            p = self.voice_dir / p
        return p.resolve()

    @property
    def info(self) -> TTSInfo:
        return TTSInfo(
            id=self._id,
            name=self._name,
            provider="gpt-sovits",
            description=f"Voice pack {self.voice_dir.name} → {self.url}",
            models=[self._name],
        )

    async def warm(self) -> None:
        """Pre-switch GPT/SoVITS weights so the first utterance is not cold."""
        if not self.load_weights or self._weights_loaded:
            return
        await asyncio.to_thread(self._ensure_weights)
        self._weights_loaded = True

    async def synthesize(self, text: str, *, model: str | None = None) -> bytes:
        if not text.strip():
            return b""
        if not self.ref_wav.is_file():
            raise FileNotFoundError(f"reference wav missing: {self.ref_wav}")
        return await asyncio.to_thread(self._synthesize_sync, text.strip())

    def _synthesize_sync(self, text: str) -> bytes:
        if self.load_weights and not self._weights_loaded:
            self._ensure_weights()
            self._weights_loaded = True

        if self.api == "v1":
            endpoint = f"{self.url}/"
            body = {
                "text": text,
                "text_language": self.text_lang,
                "refer_wav_path": str(self.ref_wav),
                "prompt_text": self.prompt_text,
                "prompt_language": self.prompt_lang,
                "top_k": self.top_k,
                "top_p": self.top_p,
                "temperature": self.temperature,
                "speed": self.speed,
            }
        else:
            endpoint = f"{self.url}/tts"
            body = {
                "text": text,
                "text_lang": self.text_lang,
                "ref_audio_path": str(self.ref_wav),
                "prompt_text": self.prompt_text,
                "prompt_lang": self.prompt_lang,
                "top_k": self.top_k,
                "top_p": self.top_p,
                "temperature": self.temperature,
                "speed_factor": self.speed,
                "media_type": "wav",
                "streaming_mode": False,
            }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"GPT-SoVITS HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"GPT-SoVITS unreachable at {self.url} ({exc}). "
                "The internal API should be listening; the sidecar does not speak this protocol."
            ) from exc

        if "json" in ctype:
            raise RuntimeError(f"GPT-SoVITS returned JSON error: {raw[:400]!r}")
        if not raw:
            raise RuntimeError("GPT-SoVITS returned empty audio")
        return raw

    def _ensure_weights(self) -> None:
        for path, route in (
            (self.gpt_path, "/set_gpt_weights"),
            (self.sovits_path, "/set_sovits_weights"),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"voice model missing: {path}")
            q = urllib.parse.urlencode({"weights_path": str(path)})
            url = f"{self.url}{route}?{q}"
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                    resp.read()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"GPT-SoVITS weight switch failed ({route}): {exc}") from exc
