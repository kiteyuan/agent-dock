"""Whisper STT — optional transport."""

from __future__ import annotations

import asyncio
import inspect
import io
import os
import sys
import threading
import time
from pathlib import Path

from loguru import logger

from runtime.transport.speech.base import STTProvider

_BILINGUAL_PROMPT = (
    "The speaker may mix Mandarin Chinese and English in one sentence, "
    "for example 打开 VS Code. Keep each word in its original language."
)


def _ensure_cuda_dll_path() -> None:
    """ctranslate2 needs cublas64_12.dll; on Windows PyTorch bundles it under torch/lib."""
    if sys.platform != "win32":
        return
    try:
        import torch

        lib = Path(torch.__file__).resolve().parent / "lib"
        if not lib.is_dir():
            return
        lib_s = str(lib)
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(lib_s)
        path = os.environ.get("PATH", "")
        if lib_s.lower() not in path.lower():
            os.environ["PATH"] = lib_s + os.pathsep + path
        logger.debug("Added torch CUDA libs to PATH: {}", lib_s)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not expose torch CUDA DLLs: {}", exc)


class WhisperSTT(STTProvider):
    def __init__(
        self,
        model: str = "small",
        device: str = "cpu",
        language: str = "auto",
        *,
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: str | None = None,
        code_switch: bool | None = None,
    ) -> None:
        self.model_name = model
        self.device = device
        self.language = language or "auto"
        self.beam_size = max(1, int(beam_size))
        self.vad_filter = vad_filter
        self.code_switch = self.language in (None, "auto", "") if code_switch is None else code_switch
        if initial_prompt is not None:
            self.initial_prompt = initial_prompt
        elif self.language in (None, "auto", ""):
            self.initial_prompt = _BILINGUAL_PROMPT
        elif self.language in ("zh", "chinese", "zh-cn", "zh-CN"):
            self.initial_prompt = (
                "这是中文语音对话。常见词：技能、智能助手、编程、代码、Markdown、Agent。"
            )
        else:
            self.initial_prompt = None
        self._model = None
        self._load_lock = threading.Lock()
        self._supports_multilingual: bool | None = None
        self.requested_device = device
        self.fallback_reason: str | None = None
        self.loaded_at: float | None = None

    def _load(self, *, force: bool = False) -> None:
        """Load once. Overlapping callers wait instead of starting a second model."""
        if self._model is not None and not force:
            return
        with self._load_lock:
            if self._model is not None and not force:
                return
            self._load_unlocked()

    def _load_unlocked(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError(
                "STT requires faster-whisper. "
                "Run: pip install -e '.[stt]'   (or pip install faster-whisper)"
            ) from exc

        if self.device != "cpu":
            _ensure_cuda_dll_path()

        logger.info("Loading Whisper model '{}' on {}", self.model_name, self.device)
        t0 = time.perf_counter()
        compute = "int8" if self.device == "cpu" else "float16"
        try:
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=compute)
        except Exception as exc:
            if self.device == "cpu":
                raise
            logger.warning("Whisper CUDA load failed ({}); falling back to CPU", exc)
            self.fallback_reason = str(exc)
            self.device = "cpu"
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        self._supports_multilingual = "multilingual" in inspect.signature(
            self._model.transcribe
        ).parameters
        self.loaded_at = time.time()
        logger.info("Whisper model ready in {:.2f}s ({})", time.perf_counter() - t0, self.device)

    def _fallback_cpu(self, reason: BaseException) -> None:
        if self.device == "cpu":
            raise reason
        logger.warning("Whisper CUDA runtime failed ({}); reloading on CPU", reason)
        self.device = "cpu"
        self._model = None
        self._load(force=True)

    def warm(self) -> None:
        """Load weights at startup so the first utterance is not cold."""
        self._load()

    def status(self) -> dict[str, object]:
        """Public, side-effect-free provider health for the Admin snapshot."""
        ready = self._model is not None
        return {
            "provider": "whisper",
            "ready": ready,
            "status": "degraded" if ready and self.fallback_reason else (
                "ready" if ready else "cold"
            ),
            "model": self.model_name,
            "requested_device": self.requested_device,
            "device": self.device,
            "language": self.language,
            "fallback_reason": self.fallback_reason,
            "loaded_at": self.loaded_at,
        }

    def _lang(self) -> str | None:
        if self.language in (None, "auto", ""):
            return None
        return self.language

    def _transcribe_input(self, source) -> tuple[str, object]:
        kwargs: dict = {
            "language": self._lang(),
            "beam_size": self.beam_size,
            "temperature": 0.0,
            "vad_filter": self.vad_filter and not self.code_switch,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            "initial_prompt": self.initial_prompt,
            "word_timestamps": False,
        }
        # best_of > 1 only helps with beam search; avoid duplicating work when beam_size==1
        if self.beam_size > 1:
            kwargs["best_of"] = self.beam_size
        if self._lang() is None and self._supports_multilingual:
            kwargs["multilingual"] = True
        segments, info = self._model.transcribe(source, **kwargs)
        parts: list[str] = []
        for seg in segments:
            piece = (seg.text or "").strip()
            if not piece:
                continue
            if getattr(seg, "no_speech_prob", 0) > 0.85:
                continue
            if getattr(seg, "avg_logprob", 0) < -1.5:
                continue
            parts.append(piece)
        return collapse_char_stutter(_join_bilingual(parts)), info

    def _transcribe_code_switch(self, source) -> str:
        """Split on VAD, recognize each utterance (zh or en) then stitch."""
        try:
            from faster_whisper.audio import decode_audio
            from faster_whisper.vad import VadOptions, get_speech_timestamps
        except ImportError:
            text, info = self._transcribe_input(source)
            logger.info("STT (no vad split) lang={} text={!r}", getattr(info, "language", "?"), text)
            return text

        pcm = decode_audio(source, sampling_rate=16000)
        stamps = get_speech_timestamps(
            pcm,
            VadOptions(min_silence_duration_ms=350, speech_pad_ms=240),
        )
        if not stamps:
            text, info = self._transcribe_input(pcm)
            logger.info("STT lang={} text={!r}", getattr(info, "language", "?"), text)
            return text

        min_samples = int(16000 * 0.18)
        chunks: list[str] = []
        for ts in stamps:
            start, end = int(ts["start"]), int(ts["end"])
            piece = pcm[start:end]
            if piece.size < min_samples:
                continue
            text, info = self._transcribe_input(piece)
            if text:
                chunks.append(text)
                logger.info(
                    "STT chunk {:.2f}-{:.2f}s lang={} text={!r}",
                    start / 16000,
                    end / 16000,
                    getattr(info, "language", "?"),
                    text,
                )
        return _join_bilingual(chunks)

    def _transcribe_source(self, source) -> str:
        if self.code_switch and self._lang() is None:
            return self._transcribe_code_switch(source)
        text, info = self._transcribe_input(source)
        logger.info(
            "STT lang={} prob={:.2f} text={!r}",
            getattr(info, "language", "?"),
            float(getattr(info, "language_probability", 0) or 0),
            text,
        )
        return text

    async def transcribe(self, audio: bytes) -> str:
        def _run() -> str:
            # Load in this worker. Doing it on the event loop freezes the device
            # socket for the whole model load and the client is disconnected.
            self._load()
            t0 = time.perf_counter()
            # Prefer in-memory buffer — avoid tempfile round-trip on every utterance
            source = io.BytesIO(audio)
            try:
                try:
                    text = self._transcribe_source(source)
                except RuntimeError as exc:
                    # Common on Windows: model loads on CUDA but encode needs cublas DLL
                    if self.device == "cpu" or "cublas" not in str(exc).lower():
                        raise
                    self._fallback_cpu(exc)
                    source.seek(0)
                    text = self._transcribe_source(source)
                logger.info("STT took {:.2f}s ({} bytes audio)", time.perf_counter() - t0, len(audio))
                return text
            finally:
                source.close()

        return await asyncio.to_thread(_run)


def collapse_char_stutter(text: str) -> str:
    """Collapse a transcript where Whisper repeated every character.

    ``你你好好`` becomes ``你好``. A normal ``你好`` is left alone.
    """
    cjk = [ch for ch in text if _is_cjk(ch)]
    if len(cjk) < 8:
        return text
    pairs = len(cjk) // 2
    doubled = sum(1 for index in range(pairs) if cjk[index * 2] == cjk[index * 2 + 1])
    if doubled < pairs * 0.75:
        return text
    out: list[str] = []
    index = 0
    while index < len(text):
        ch = text[index]
        if index + 1 < len(text) and _is_cjk(ch) and text[index + 1] == ch:
            out.append(ch)
            index += 2
            continue
        out.append(ch)
        index += 1
    return "".join(out)


def _join_bilingual(parts: list[str]) -> str:
    out = ""
    for raw in parts:
        p = (raw or "").strip()
        if not p:
            continue
        if not out:
            out = p
            continue
        if _is_cjk(out[-1]) and _is_cjk(p[0]):
            out += p
        else:
            out += " " + p
    return out.strip()


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"
