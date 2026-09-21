"""Save device audio takes so a silent capture can be checked later."""

from __future__ import annotations

import io
import math
import struct
import time
import wave
from pathlib import Path


def save_audio_capture(workspace: Path, device_id: str, audio: bytes) -> tuple[Path, str]:
    folder = workspace / "captures"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in device_id) or "device"
    path = folder / f"{stamp}-{safe_id}.wav"
    path.write_bytes(audio)
    return path, describe_audio(audio)


def describe_audio(audio: bytes) -> str:
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return f"not a WAV ({len(audio)} bytes)"
    try:
        with wave.open(io.BytesIO(audio), "rb") as handle:
            channels = handle.getnchannels()
            rate = handle.getframerate()
            width = handle.getsampwidth()
            frames = handle.getnframes()
            pcm = handle.readframes(frames)
    except (wave.Error, EOFError) as exc:
        return f"WAV header unreadable ({exc})"
    duration = frames / rate if rate else 0.0
    if width != 2 or not pcm:
        return (
            f"WAV {rate} Hz {channels} ch {width * 8}-bit "
            f"{duration:.2f}s {len(audio)} bytes"
        )
    count = len(pcm) // 2
    samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
    peak = max(abs(sample) for sample in samples)
    mean_sq = sum(sample * sample for sample in samples) / count
    rms = math.sqrt(mean_sq)
    return (
        f"WAV {rate} Hz {channels} ch 16-bit {duration:.2f}s "
        f"peak={peak / 32767:.4f} rms={rms / 32767:.4f} bytes={len(audio)}"
    )
