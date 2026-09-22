"""TTS failures stay on the selected voice. They do not switch engines."""

from __future__ import annotations

import asyncio
from pathlib import Path

from runtime.bridge.pipeline import BridgePipeline
from runtime.session.models import Session
from runtime.transport.speech.base import TTSInfo
from runtime.transport.speech.gpt_sovits_tts import GPTSoVITSTTS


class _Broken:
    def __init__(self) -> None:
        self.info = TTSInfo(id="haibara", name="Haibara", provider="http")

    async def synthesize(self, text: str, *, model: str | None = None) -> bytes:
        raise RuntimeError("sidecar down")


class _Edge:
    def __init__(self) -> None:
        self.info = TTSInfo(id="edge", name="Edge", provider="edge")
        self.called = False

    async def synthesize(self, text: str, *, model: str | None = None) -> bytes:
        self.called = True
        return b"mp3"


class _Registry:
    def __init__(self) -> None:
        self.edge = _Edge()

    def get(self, tts_id: str | None):
        if tts_id == "edge":
            return self.edge
        return _Broken()


def test_tts_failure_does_not_fall_back_to_edge() -> None:
    registry = _Registry()
    pipeline = BridgePipeline(router=None, tts_registry=registry)  # type: ignore[arg-type]
    session = Session(session_id="s1", device_id="d1", tts_id="haibara", tts_model="assets/voices/haibara")
    sent: list[str] = []

    async def send(data: str | bytes) -> None:
        if isinstance(data, str):
            sent.append(data)

    class _Bus:
        async def _send(self, data: str | bytes) -> None:
            await send(data)

        async def publish(self, event: object) -> None:
            sent.append(str(event))

    asyncio.run(pipeline._synthesize_segment(session, _Bus(), "你好"))
    assert registry.edge.called is False
    assert not any("agent.error" in item or "TTS failed" in item for item in sent)


def test_tts_end_is_sent_if_audio_send_fails() -> None:
    class _Ok:
        def __init__(self) -> None:
            self.info = TTSInfo(id="edge", name="Edge", provider="edge", audio_format="mp3")

        async def synthesize(self, text: str, *, model: str | None = None) -> bytes:
            return b"mp3"

    class _Voices:
        def get(self, tts_id: str | None):
            return _Ok()

    pipeline = BridgePipeline(router=None, tts_registry=_Voices())  # type: ignore[arg-type]
    session = Session(session_id="s1", device_id="d1", tts_id="edge")
    sent: list[str] = []

    class _Bus:
        async def _send(self, data: str | bytes) -> None:
            if isinstance(data, bytes):
                raise ConnectionError("gone")
            sent.append(data)

        async def publish(self, event: object) -> None:
            sent.append(str(event))

    asyncio.run(pipeline._synthesize_segment(session, _Bus(), "你好"))
    assert any("tts.start" in item for item in sent)
    assert any("tts.end" in item for item in sent)


def test_cancelled_turn_emits_agent_cancel() -> None:
    from runtime.bridge.bus import EventBus
    from runtime.protocol.agent import AgentInfo, agent_start

    class _Hang:
        info = AgentInfo(id="mock", name="mock")

        async def run(self, request):
            yield agent_start(request.session_id)
            await asyncio.sleep(3600)

    class _Router:
        def resolve(self, **kwargs):
            return _Hang()

    class _SilentTts:
        def get(self, tts_id: str | None):
            return None

    sent: list[str] = []

    async def send(data: str | bytes) -> None:
        if isinstance(data, str):
            sent.append(data)

    async def main() -> None:
        pipeline = BridgePipeline(router=_Router(), tts_registry=_SilentTts())  # type: ignore[arg-type]
        session = Session(session_id="s1", device_id="d1")
        task = asyncio.create_task(pipeline.run_turn(session, "hi", EventBus(send)))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    asyncio.run(main())
    assert any("agent.cancel" in item for item in sent)


def test_weight_switch_failure_is_not_treated_as_loaded(tmp_path: Path, monkeypatch) -> None:
    voice = tmp_path / "Haibara"
    (voice / "models").mkdir(parents=True)
    (voice / "reference").mkdir()
    (voice / "models" / "gpt.ckpt").write_bytes(b"g")
    (voice / "models" / "sovits.pth").write_bytes(b"s")
    (voice / "reference" / "ref.wav").write_bytes(b"w")
    engine = GPTSoVITSTTS("Haibara", voice_dir=voice, url="http://127.0.0.1:19880")

    def fail(url: str, timeout: float = 0):
        raise OSError("refused")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    try:
        engine._ensure_weights()
    except RuntimeError as exc:
        assert "weight switch failed" in str(exc)
    else:
        raise AssertionError("weight switch failure was swallowed")
    assert engine._weights_loaded is False
