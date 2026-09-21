import asyncio
import threading
import time

from runtime.transport.speech.whisper_stt import WhisperSTT


def test_overlapping_loads_share_one_model() -> None:
    stt = WhisperSTT(model="tiny", device="cpu", language="zh")
    entered = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def slow() -> None:
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        stt._model = object()

    stt._load_unlocked = slow  # type: ignore[method-assign]
    first = threading.Thread(target=stt._load)
    second = threading.Thread(target=stt._load)
    first.start()
    assert entered.wait(2)
    second.start()
    time.sleep(0.05)
    assert calls == [first.ident]
    release.set()
    first.join(2)
    second.join(2)
    assert calls == [first.ident]


def test_transcribe_loads_off_the_event_loop() -> None:
    stt = WhisperSTT(model="tiny", device="cpu", language="zh")
    ticks = 0
    seen_during_load: list[int] = []

    def slow() -> None:
        time.sleep(0.05)
        seen_during_load.append(ticks)
        time.sleep(0.05)
        stt._model = object()

    stt._load_unlocked = slow  # type: ignore[method-assign]
    stt._transcribe_source = lambda source: "你好"  # type: ignore[method-assign]

    async def run() -> None:
        nonlocal ticks

        async def ticker() -> None:
            nonlocal ticks
            for _ in range(8):
                ticks += 1
                await asyncio.sleep(0.01)

        await asyncio.gather(stt.transcribe(b"RIFFxxxxWAVE"), ticker())

    asyncio.run(run())
    assert seen_during_load and seen_during_load[0] > 0
