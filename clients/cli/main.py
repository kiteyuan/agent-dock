"""
cli-client — CLI + launcher for AgentDock.

Primary UI (all platforms):
  python main.py              # opens clients/web
  python main.py --ui

CLI (script / debug):
  python main.py --chat [--agent pi] [--tts edge]
  python main.py --text "..."
  python main.py --record 5
  python main.py --wav path/to/audio.wav

Chat mode (CLI):
  > 你好          发送文字
  >               空行 = 开始录音；再空行 = 结束并发送
  > /r [秒]       定时录音
  > /cancel       取消当前轮
  > /q            退出

Env: AGENTDOCK_URL, AGENTDOCK_TOKEN, AGENTDOCK_DEVICE
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import wave
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

# Local protocol.py re-exports clients/shared; turn_view lives in shared/
_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "shared"
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_SHARED) not in sys.path:
    sys.path.append(str(_SHARED))

from protocol import (  # noqa: E402
    agents_list,
    audio_end,
    audio_start,
    device_hello,
    ping,
    session_cancel,
    tts_list,
    tts_select,
    user_message,
)
from turn_view import TurnView  # noqa: E402

_TURN_END = {"agent.done", "agent.cancel", "agent.error", "error"}
CHUNK = 4096
SAMPLE_RATE = 16000


async def connect_with_retry(url: str, *, retries: int = 5, base_delay: float = 0.5):
    last_err: Exception | None = None
    for i in range(retries):
        try:
            return await websockets.connect(
                url, ping_interval=20, ping_timeout=20, max_size=16 * 1024 * 1024
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            delay = base_delay * (2**i)
            print(f"[reconnect] {exc} — retry in {delay:.1f}s ({i + 1}/{retries})")
            await asyncio.sleep(delay)
    raise RuntimeError(f"failed to connect to {url}: {last_err}")


async def _drain_hello_extras(ws) -> None:
    """Runtime may push tts/pets catalogs right after session.accept."""
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.25)
        except asyncio.TimeoutError:
            return
        if isinstance(raw, (bytes, bytearray)):
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        mtype = msg.get("type")
        if mtype in ("tts.list.result", "pets.list.result", "agents.list.result", "device.pong"):
            if mtype == "tts.list.result":
                print(f"[tts] providers={[p.get('id') for p in (msg.get('payload') or {}).get('providers') or []]} default={(msg.get('payload') or {}).get('default')}")
            elif mtype == "pets.list.result":
                print(f"[pets] default={(msg.get('payload') or {}).get('default')}")
            continue
        print(f"[warn] unexpected after accept: {mtype}")


async def run(
    *,
    url: str,
    device_id: str,
    token: str | None,
    text: str | None = None,
    wav_path: str | None = None,
    record_secs: float | None = None,
    list_agents: bool = False,
    list_tts: bool = False,
    cancel_after: float | None = None,
    agent_id: str | None = None,
    tts_id: str | None = None,
    tts_model: str | None = None,
    heartbeat: bool = False,
    play: bool = True,
    chat: bool = False,
    record_default: float = 5.0,
) -> None:
    ws = await connect_with_retry(url)
    view = TurnView()
    try:
        # Thin client: do not configure TTS via hello; Runtime pushes defaults.
        await ws.send(device_hello(device_id, "voice_client", token=token))
        resp = json.loads(await ws.recv())
        if resp["type"] == "error":
            print("auth/error:", resp)
            return
        assert resp["type"] == "session.accept", f"Unexpected: {resp}"
        session_id = resp["payload"]["session_id"]
        print(f"[connected] session={session_id} url={url}")
        if resp["payload"].get("advertise_url"):
            print(f"[advertise] {resp['payload']['advertise_url']}")
        if resp["payload"].get("tts_id"):
            print(f"[tts] session default={resp['payload']['tts_id']}")
        if resp["payload"].get("pet_id"):
            print(f"[pet] session default={resp['payload']['pet_id']}")
        await _drain_hello_extras(ws)

        hb_task = asyncio.create_task(_heartbeat(ws)) if heartbeat else None

        if list_agents:
            await ws.send(agents_list())
            _print_raw(json.loads(await ws.recv()))
            return

        if list_tts:
            await ws.send(tts_list())
            _print_raw(json.loads(await ws.recv()))
            return

        if tts_id:
            # Optional CLI override only — normal clients never select TTS.
            await ws.send(tts_select(session_id, tts_id, tts_model))
            msg = json.loads(await ws.recv())
            if msg.get("type") == "tts.selected":
                print(f"[tts] selected={msg['payload'].get('tts_id')}")
            else:
                _print_raw(msg)

        if chat:
            await _chat_loop(
                ws,
                session_id=session_id,
                view=view,
                agent_id=agent_id,
                tts_id=tts_id,
                tts_model=tts_model,
                record_default=record_default,
                play=play,
            )
            if hb_task:
                hb_task.cancel()
            return

        # --- single-shot input ---
        if text is not None:
            await ws.send(
                user_message(
                    session_id, text, agent_id=agent_id, tts_id=tts_id, tts_model=tts_model
                )
            )
            print(f"你：{text}")
        elif wav_path or record_secs is not None:
            audio = _load_or_record(wav_path, record_secs or record_default)
            await ws.send(audio_start(session_id))
            for i in range(0, len(audio), CHUNK):
                await ws.send(audio[i : i + CHUNK])
            await ws.send(audio_end(session_id))
            print(f"[sent audio] {len(audio)} bytes")
        else:
            print(
                "ERROR: provide --chat / --text / --record / --wav / --list-agents / --list-tts",
                file=sys.stderr,
            )
            sys.exit(1)

        if cancel_after is not None:

            async def _cancel() -> None:
                await asyncio.sleep(cancel_after)
                await ws.send(session_cancel(session_id))
                print(f"[cancel] after {cancel_after}s")

            asyncio.create_task(_cancel())

        await _recv_turn(ws, view=view, play=play)
        if hb_task:
            hb_task.cancel()
    finally:
        await ws.close()


async def _chat_loop(
    ws,
    *,
    session_id: str,
    view: TurnView,
    agent_id: str | None,
    tts_id: str | None,
    tts_model: str | None,
    record_default: float,
    play: bool,
) -> None:
    print("聊天：文字回车；空行开始录音、再空行结束；/r [秒]；/cancel；/q")
    while True:
        try:
            line = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        cmd = line.strip()
        if cmd in ("/q", "/quit", "/exit", "quit", "exit"):
            print("再见")
            break
        if cmd in ("/cancel", "/c"):
            await ws.send(session_cancel(session_id))
            print("已发送取消")
            continue

        record_secs: float | None = None
        text: str | None = None
        toggle_record = False
        if cmd.startswith("/r") or cmd.startswith("/record"):
            parts = cmd.split()
            if len(parts) >= 2:
                try:
                    record_secs = float(parts[1])
                except ValueError:
                    print("用法：/r [秒]")
                    continue
            else:
                record_secs = record_default
        elif cmd == "":
            toggle_record = True
        else:
            text = line  # keep original spacing for typed messages

        view.reset_turn()
        if text is not None:
            await ws.send(
                user_message(
                    session_id, text, agent_id=agent_id, tts_id=tts_id, tts_model=tts_model
                )
            )
            print(f"你：{text}")
        elif toggle_record:
            try:
                audio = await _record_until_enter()
            except SystemExit:
                continue
            await ws.send(audio_start(session_id))
            for i in range(0, len(audio), CHUNK):
                await ws.send(audio[i : i + CHUNK])
            await ws.send(audio_end(session_id))
            print(f"[录音] {len(audio)} bytes")
        else:
            assert record_secs is not None
            try:
                audio = await asyncio.to_thread(_record_wav, record_secs)
            except SystemExit:
                continue
            await ws.send(audio_start(session_id))
            for i in range(0, len(audio), CHUNK):
                await ws.send(audio[i : i + CHUNK])
            await ws.send(audio_end(session_id))
            print(f"[录音] {len(audio)} bytes · {record_secs}s")

        await _recv_turn(ws, view=view, play=play)


def _load_or_record(wav_path: str | None, seconds: float) -> bytes:
    if wav_path:
        data = Path(wav_path).read_bytes()
        print(f"[wav] loaded {wav_path} ({len(data)} bytes)")
        return data
    return _record_wav(seconds)


def _record_wav(seconds: float) -> bytes:
    try:
        import sounddevice as sd
    except ImportError:
        print(
            "ERROR: mic recording needs: pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(f"[record] {seconds}s @ {SAMPLE_RATE}Hz — speak now...")
    frames = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(frames.tobytes())
    print("[record] done")
    return buf.getvalue()


async def _record_until_enter(*, max_seconds: float = 60.0) -> bytes:
    """Click-toggle style: already started by empty line; wait for next Enter to stop."""
    import threading

    try:
        import sounddevice as sd
    except ImportError:
        print(
            "ERROR: mic recording needs: pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    stop = threading.Event()
    chunks: list[bytes] = []
    max_frames = int(max_seconds * SAMPLE_RATE)
    got = 0

    def _callback(indata, frames, time, status) -> None:  # noqa: ARG001
        nonlocal got
        if stop.is_set() or got >= max_frames:
            raise sd.CallbackStop
        chunks.append(indata[:frames].tobytes())
        got += frames

    print("[record] 录音中 · 再按回车结束")

    def _capture() -> bytes:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=1024,
            callback=_callback,
        ):
            while not stop.is_set() and got < max_frames:
                stop.wait(0.05)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(chunks))
        return buf.getvalue()

    rec_task = asyncio.create_task(asyncio.to_thread(_capture))
    try:
        await asyncio.to_thread(input, "")
    except (EOFError, KeyboardInterrupt):
        pass
    stop.set()
    audio = await rec_task
    print("[record] done")
    return audio


def _launch_web_ui(*, port: int = 8090, no_open: bool = False) -> None:
    web_root = Path(__file__).resolve().parents[1] / "web"
    serve = web_root / "serve.py"
    if not serve.is_file():
        print(f"ERROR: Web UI missing at {web_root}", file=sys.stderr)
        raise SystemExit(1)
    import runpy

    sys.argv = [str(serve), "--port", str(port)]
    if no_open:
        sys.argv.append("--no-open")
    runpy.run_path(str(serve), run_name="__main__")


async def _heartbeat(ws, interval: float = 15.0) -> None:
    try:
        while True:
            await asyncio.sleep(interval)
            await ws.send(ping())
    except (asyncio.CancelledError, ConnectionClosed):
        return


def _print_raw(msg: dict) -> None:
    print(f"  <- {msg['type']}: {json.dumps(msg.get('payload', {}), ensure_ascii=False)}")


async def _recv_turn(ws, *, view: TurnView, play: bool = True) -> None:
    tts_audio = bytearray()
    audio_format = "wav"
    seg_n = 0

    while True:
        raw = await ws.recv()
        if isinstance(raw, bytes):
            tts_audio.extend(raw)
            continue
        msg = json.loads(raw)
        mtype = msg["type"]
        payload = msg.get("payload", {})
        view.handle(mtype, payload)

        if mtype == "tts.start":
            audio_format = payload.get("format") or "wav"
            tts_audio.clear()
            continue
        if mtype == "tts.end":
            if tts_audio:
                seg_n += 1
                ext = (
                    "mp3"
                    if audio_format == "mp3" or tts_audio[:3] == b"ID3" or tts_audio[:2] == b"\xff\xfb"
                    else "wav"
                )
                if tts_audio[:4] == b"RIFF":
                    ext = "wav"
                out = Path(f"response-{seg_n}.{ext}" if seg_n > 1 else f"response.{ext}")
                out.write_bytes(tts_audio)
                print(f"[tts] saved {out} ({len(tts_audio)} bytes)")
                if play:
                    await asyncio.to_thread(_play_file, out)
                tts_audio.clear()
            continue
        if mtype in _TURN_END:
            break


def _play_file(path: Path) -> None:
    try:
        if path.suffix.lower() == ".wav":
            import sounddevice as sd
            import soundfile as sf

            data, sr = sf.read(str(path), dtype="float32")
            sd.play(data, sr)
            sd.wait()
            print("[tts] playback done")
            return
    except Exception as exc:  # noqa: BLE001
        print(f"[tts] sounddevice play failed: {exc}")

    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            os.system(f'afplay "{path}"')  # noqa: S605
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')  # noqa: S605
        print(f"[tts] opened with system player: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[tts] could not play: {exc}")


def _parse_args(argv: list[str]) -> dict:
    out: dict = {
        "text": None,
        "wav_path": None,
        "record_secs": None,
        "list_agents": False,
        "list_tts": False,
        "cancel_after": None,
        "agent_id": None,
        "tts_id": None,
        "tts_model": None,
        "url": os.environ.get("AGENTDOCK_URL", "ws://localhost:8765"),
        "token": os.environ.get("AGENTDOCK_TOKEN"),
        "device_id": os.environ.get("AGENTDOCK_DEVICE", "cli-001"),
        "heartbeat": False,
        "play": True,
        "chat": False,
        "ui": False,
        "ui_port": 8090,
        "record_default": 5.0,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--text":
            i += 1
            out["text"] = argv[i]
        elif a == "--wav":
            i += 1
            out["wav_path"] = argv[i]
        elif a == "--record":
            i += 1
            if i < len(argv) and not argv[i].startswith("--"):
                out["record_secs"] = float(argv[i])
            else:
                out["record_secs"] = 5.0
                i -= 1
        elif a == "--chat":
            out["chat"] = True
        elif a == "--ui":
            out["ui"] = True
        elif a == "--ui-port":
            i += 1
            out["ui_port"] = int(argv[i])
        elif a == "--list-agents":
            out["list_agents"] = True
        elif a == "--list-tts":
            out["list_tts"] = True
        elif a == "--cancel-after":
            i += 1
            out["cancel_after"] = float(argv[i])
        elif a == "--agent":
            i += 1
            out["agent_id"] = argv[i]
        elif a == "--tts":
            i += 1
            out["tts_id"] = argv[i]
        elif a == "--tts-model":
            i += 1
            out["tts_model"] = argv[i]
        elif a == "--url":
            i += 1
            out["url"] = argv[i]
        elif a == "--token":
            i += 1
            out["token"] = argv[i]
        elif a == "--device":
            i += 1
            out["device_id"] = argv[i]
        elif a == "--heartbeat":
            out["heartbeat"] = True
        elif a == "--no-play":
            out["play"] = False
        elif a == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            print(f"unknown arg: {a}", file=sys.stderr)
            sys.exit(1)
        i += 1
    return out


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    has_input = (
        args["chat"]
        or args["ui"]
        or args["list_agents"]
        or args["list_tts"]
        or args["text"] is not None
        or args["wav_path"] is not None
        or args["record_secs"] is not None
    )
    # No args → unified Web UI
    if not has_input:
        args["ui"] = True
    if args["ui"]:
        _launch_web_ui(port=int(args["ui_port"]))
        raise SystemExit(0)
    asyncio.run(run(**{k: v for k, v in args.items() if k not in ("ui", "ui_port")}))
