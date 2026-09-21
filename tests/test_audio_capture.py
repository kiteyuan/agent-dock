import io
import struct
import wave

from runtime.device.audio_capture import describe_audio, save_audio_capture


def _wav(samples: list[int], rate: int = 16000) -> bytes:
    raw = struct.pack("<" + "h" * len(samples), *samples)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(raw)
    return buffer.getvalue()


def test_silence_capture_reports_zero_level(tmp_path) -> None:
    audio = _wav([0] * 1600)
    path, summary = save_audio_capture(tmp_path, "mobile-1", audio)
    assert path.is_file()
    assert path.read_bytes() == audio
    assert "peak=0.0000" in summary
    assert "rms=0.0000" in summary
    assert "16000 Hz" in summary


def test_tone_capture_reports_a_nonzero_peak() -> None:
    summary = describe_audio(_wav([16384] * 1600))
    assert "peak=0.5000" in summary
