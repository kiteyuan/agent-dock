"""Always-on wake word + VAD end-of-utterance for the Pi terminal.

Wake audio is discarded (no disk). After a hit, PCM is buffered until silence.
openWakeWord / webrtcvad are optional imports — missing extras fall back clearly.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from loguru import logger

from device.audio import _frames_to_wav, input_kwargs

WAKE_FRAME = 1280  # openWakeWord: 80 ms @ 16 kHz
VAD_FRAME_MS = 30
SAMPLE_RATE = 16000


class SilenceGate:
    """Count VAD frames; stop after enough speech then consecutive silence."""

    def __init__(self, *, min_speech_frames: int, silence_frames: int) -> None:
        self.min_speech_frames = max(1, min_speech_frames)
        self.silence_frames = max(1, silence_frames)
        self.speech_seen = 0
        self.silence_run = 0

    def feed(self, is_speech: bool) -> bool:
        if is_speech:
            self.speech_seen += 1
            self.silence_run = 0
            return False
        if self.speech_seen < self.min_speech_frames:
            return False
        self.silence_run += 1
        return self.silence_run >= self.silence_frames


def _ms_to_frames(ms: float, frame_ms: int) -> int:
    return max(1, int(round(ms / frame_ms)))


def wait_for_wake(
    *,
    sample_rate: int = SAMPLE_RATE,
    model: str = "hey_jarvis",
    threshold: float = 0.5,
    device: int | str | None = None,
    stop_event=None,
    cooldown_s: float = 0.8,
) -> None:
    """Block until openWakeWord score >= threshold. Raises if the lib is missing."""
    try:
        from openwakeword.model import Model
    except ImportError as exc:
        raise RuntimeError(
            "openWakeWord not installed. On Pi: pip install openwakeword webrtcvad"
        ) from exc

    oww = _load_wake_model(Model, model)
    if cooldown_s > 0:
        time.sleep(cooldown_s)

    import numpy as np
    import sounddevice as sd

    buf = bytearray()
    hit = {"ok": False}
    logger.info("Wake listen model={} threshold={}", model, threshold)

    def _callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
        if stop_event is not None and stop_event.is_set():
            raise sd.CallbackStop
        buf.extend(indata[:frames].tobytes())
        frame_bytes = WAKE_FRAME * 2
        while len(buf) >= frame_bytes:
            chunk = bytes(buf[:frame_bytes])
            del buf[:frame_bytes]
            pcm = np.frombuffer(chunk, dtype=np.int16)
            scores = oww.predict(pcm)
            if not scores:
                continue
            best = max(scores.values())
            if float(best) >= threshold:
                hit["ok"] = True
                raise sd.CallbackStop

    kwargs = input_kwargs(sample_rate=sample_rate, device=device, blocksize=WAKE_FRAME)
    with sd.InputStream(**kwargs, callback=_callback):
        while not hit["ok"]:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(0.05)
    logger.info("Wake word hit")


def record_until_silence(
    *,
    sample_rate: int = SAMPLE_RATE,
    silence_ms: float = 1500,
    min_speech_ms: float = 400,
    max_seconds: float = 30.0,
    vad_aggressiveness: int = 2,
    device: int | str | None = None,
    stop_event=None,
    pre_roll_ms: float = 300,
) -> bytes:
    """Capture 16-bit mono PCM until VAD silence (or max_seconds / stop_event)."""
    import numpy as np
    import sounddevice as sd

    try:
        import webrtcvad
    except ImportError as exc:
        raise RuntimeError("webrtcvad not installed. pip install webrtcvad") from exc

    vad = webrtcvad.Vad(int(max(0, min(3, vad_aggressiveness))))
    frame_samples = int(sample_rate * VAD_FRAME_MS / 1000)
    frame_bytes = frame_samples * 2
    gate = SilenceGate(
        min_speech_frames=_ms_to_frames(min_speech_ms, VAD_FRAME_MS),
        silence_frames=_ms_to_frames(silence_ms, VAD_FRAME_MS),
    )
    max_frames = int(max_seconds * sample_rate)
    pcm = bytearray()
    pending = bytearray()
    pre_bytes = int(sample_rate * pre_roll_ms / 1000) * 2
    preroll: deque[bytes] = deque()
    preroll_len = 0
    got = 0
    done = {"ok": False}

    logger.info(
        "Record until silence={}ms min_speech={}ms max={}s",
        silence_ms,
        min_speech_ms,
        max_seconds,
    )

    def _consume_vad() -> None:
        nonlocal preroll_len, got
        while len(pending) >= frame_bytes:
            frame = bytes(pending[:frame_bytes])
            del pending[:frame_bytes]
            if got == 0:
                preroll.append(frame)
                preroll_len += len(frame)
                cap = pre_bytes if pre_bytes > 0 else frame_bytes
                while preroll_len > cap:
                    old = preroll.popleft()
                    preroll_len -= len(old)
                try:
                    voiced = vad.is_speech(frame, sample_rate)
                except Exception:
                    voiced = True
                if not voiced:
                    continue
                for p in preroll:
                    pcm.extend(p)
                    got += len(p) // 2
                preroll.clear()
                preroll_len = 0
                if gate.feed(True) or got >= max_frames:
                    done["ok"] = True
                    return
                continue
            try:
                voiced = vad.is_speech(frame, sample_rate)
            except Exception:
                voiced = True
            pcm.extend(frame)
            got += frame_samples
            if gate.feed(voiced) or got >= max_frames:
                done["ok"] = True
                return

    def _callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
        if stop_event is not None and stop_event.is_set():
            done["ok"] = True
            raise sd.CallbackStop
        pending.extend(np.asarray(indata[:frames]).tobytes())
        _consume_vad()
        if done["ok"] or got >= max_frames:
            raise sd.CallbackStop

    kwargs = input_kwargs(sample_rate=sample_rate, device=device, blocksize=frame_samples)
    with sd.InputStream(**kwargs, callback=_callback):
        while not done["ok"] and got < max_frames:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.03)

    if len(pcm) < frame_bytes:
        logger.warning("utterance too short ({} bytes)", len(pcm))
        return b""
    return _frames_to_wav(bytes(pcm), sample_rate)


def _load_wake_model(Model: Any, spec: str):
    models = [spec]
    for framework in ("tflite", "onnx"):
        try:
            m = Model(wakeword_models=models, inference_framework=framework)
            logger.info("openWakeWord framework={}", framework)
            return m
        except Exception as exc:  # noqa: BLE001
            logger.debug("wake framework {} failed: {}", framework, exc)
    return Model(wakeword_models=models)
