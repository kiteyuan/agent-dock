"""Pi Terminal entry — wake-word loop (default) or click-to-talk against AgentDock Runtime."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from pathlib import Path

# Allow `python -m device` from clients/rpi
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_SHARED_PARENT = _HERE.parent  # clients/
if str(_SHARED_PARENT) not in sys.path:
    sys.path.insert(0, str(_SHARED_PARENT))

from loguru import logger

from device.config import load_config
from device.display import build_display
from device.input_trigger import build_trigger
from device.listen import record_until_silence, wait_for_wake
from device.network import RuntimeConnection
from device.state import DeviceState


def _audio_device(audio: dict):
    dev = audio.get("device")
    if dev is None or dev == "":
        return None
    if isinstance(dev, str) and dev.isdigit():
        return int(dev)
    return dev


async def main_async(config_path: str | None = None) -> None:
    cfg = load_config(config_path)
    display = build_display(cfg.get("display") or {})
    display.show(DeviceState.BOOT)

    audio = cfg.get("audio") or {}
    listen = cfg.get("listen") or {}
    reconnect = cfg.get("reconnect") or {}
    mode = str(listen.get("mode") or "wake").strip().lower()
    device = _audio_device(audio)
    playback_device = audio.get("playback_device")
    if isinstance(playback_device, str) and playback_device.isdigit():
        playback_device = int(playback_device)
    sample_rate = int(audio.get("sample_rate", 16000))

    conn = RuntimeConnection(
        url=cfg.get("runtime_url") or "ws://127.0.0.1:8765",
        device_id=cfg.get("device_id") or "pi-001",
        device_type=cfg.get("device_type") or "pi",
        token=cfg.get("token"),
        display=display,
        sample_rate=sample_rate,
        record_seconds=float(audio.get("record_seconds", 5)),
        audio_device=device,
        playback_device=playback_device,
        heartbeat_seconds=float(cfg.get("heartbeat_seconds", 0)),
        reconnect_retries=int(reconnect.get("retries", 20)),
        reconnect_delay=float(reconnect.get("base_delay", 1.0)),
        ws_ping_interval=float(cfg.get("ws_ping_interval", 30) or 0) or None,
    )

    await conn.connect()
    try:
        if mode == "button":
            await _button_loop(cfg, conn)
        else:
            await _wake_loop(listen, conn, sample_rate=sample_rate, device=device)
    except KeyboardInterrupt:
        logger.info("bye")
    finally:
        await conn.close()


async def _button_loop(cfg: dict, conn: RuntimeConnection) -> None:
    trigger = build_trigger(cfg.get("button") or {})
    while True:
        await trigger.wait_press()
        stop = threading.Event()

        async def _wait_stop() -> None:
            await trigger.wait_press()
            stop.set()

        stopper = asyncio.create_task(_wait_stop())
        try:
            await conn.talk_once(stop)
        except Exception as exc:  # noqa: BLE001
            logger.exception("turn failed: {}", exc)
            conn.display.show(DeviceState.ERROR, f"错误:{exc}")
            await asyncio.sleep(1)
            conn.display.show(DeviceState.ONLINE)
        finally:
            stop.set()
            stopper.cancel()
            try:
                await stopper
            except asyncio.CancelledError:
                pass


async def _wake_loop(
    listen: dict,
    conn: RuntimeConnection,
    *,
    sample_rate: int,
    device,
) -> None:
    model = str(listen.get("model") or listen.get("wake_word") or "hey_jarvis")
    model_path = Path(model)
    if model_path.suffix.lower() in {".onnx", ".tflite"} and not model_path.is_absolute():
        resolved = (_HERE / model_path).resolve()
        if resolved.is_file():
            model = str(resolved)
    threshold = float(listen.get("threshold", 0.5))
    silence_ms = float(listen.get("silence_ms", 1500))
    min_speech_ms = float(listen.get("min_speech_ms", 400))
    max_seconds = float(listen.get("max_seconds", 30))
    vad_aggr = int(listen.get("vad_aggressiveness", 2))
    cooldown_s = float(listen.get("cooldown_ms", 800)) / 1000.0
    pre_roll_ms = float(listen.get("pre_roll_ms", 300))
    stop = threading.Event()

    while True:
        conn.display.show(DeviceState.ONLINE, "待命")
        stop.clear()
        try:
            await asyncio.to_thread(
                wait_for_wake,
                sample_rate=sample_rate,
                model=model,
                threshold=threshold,
                device=device,
                stop_event=stop,
                cooldown_s=cooldown_s,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("wake failed: {}", exc)
            conn.display.show(DeviceState.ERROR, f"错误:{exc}")
            await asyncio.sleep(2)
            continue

        conn.display.show(DeviceState.LISTENING, "请说")
        try:
            wav = await asyncio.to_thread(
                record_until_silence,
                sample_rate=sample_rate,
                silence_ms=silence_ms,
                min_speech_ms=min_speech_ms,
                max_seconds=max_seconds,
                vad_aggressiveness=vad_aggr,
                device=device,
                stop_event=stop,
                pre_roll_ms=pre_roll_ms,
            )
            await conn.talk_wav(wav)
        except Exception as exc:  # noqa: BLE001
            logger.exception("turn failed: {}", exc)
            conn.display.show(DeviceState.ERROR, f"错误:{exc}")
            await asyncio.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentDock Pi Terminal")
    parser.add_argument("-c", "--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    asyncio.run(main_async(args.config))


if __name__ == "__main__":
    main()
