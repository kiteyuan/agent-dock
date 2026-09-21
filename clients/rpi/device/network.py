"""WebSocket runtime connection with reconnect + heartbeat."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import websockets
from loguru import logger
from websockets.exceptions import ConnectionClosed

from device.audio import play_bytes, record_until_stop
from device.display import Display
from device.protocol import audio_end, audio_start, device_hello, ping, session_cancel
from device.state import DeviceState

_SHARED = Path(__file__).resolve().parents[2] / "shared"
if str(_SHARED) not in sys.path:
    sys.path.append(str(_SHARED))
from turn_view import TurnView  # noqa: E402


class RuntimeConnection:
    def __init__(
        self,
        *,
        url: str,
        device_id: str,
        device_type: str = "pi",
        token: str | None = None,
        display: Display,
        sample_rate: int = 16000,
        record_seconds: float = 5,
        audio_device: int | str | None = None,
        playback_device: int | str | None = None,
        heartbeat_seconds: float = 0,
        reconnect_retries: int = 20,
        reconnect_delay: float = 1.0,
        ws_ping_interval: float | None = 30.0,
    ) -> None:
        self.url = url
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.display = display
        self.sample_rate = sample_rate
        self.record_seconds = record_seconds
        self.audio_device = audio_device
        self.playback_device = playback_device
        # 0 = rely on websockets protocol ping only (preferred on Zero 2 W)
        self.heartbeat_seconds = heartbeat_seconds
        self.reconnect_retries = reconnect_retries
        self.reconnect_delay = reconnect_delay
        self.ws_ping_interval = ws_ping_interval
        self._ws: Any = None
        self.session_id: str | None = None
        self._hb: asyncio.Task | None = None
        self._view = TurnView(print=lambda s: logger.info("{}", s))
        self._turn_reply = ""

    def _set(self, state: DeviceState, line: str | None = None) -> None:
        self.display.show(state, line)

    async def connect(self) -> None:
        if self._hb:
            self._hb.cancel()
            self._hb = None
        # Long text (URL) goes to body; status row stays "* CONNECTING"
        self._set(DeviceState.CONNECTING, self.url)
        last: Exception | None = None
        for i in range(self.reconnect_retries):
            try:
                ping_interval = self.ws_ping_interval
                self._ws = await websockets.connect(
                    self.url,
                    ping_interval=ping_interval,
                    # Long TTS turns need headroom; playing used to block recv.
                    ping_timeout=60 if ping_interval else None,
                    max_size=16 * 1024 * 1024,
                )
                await self._ws.send(
                    device_hello(
                        self.device_id,
                        self.device_type,
                        token=self.token,
                    )
                )
                resp = json.loads(await self._ws.recv())
                if resp.get("type") == "error":
                    raise RuntimeError(resp.get("payload", {}).get("detail", "auth error"))
                if resp.get("type") != "session.accept":
                    raise RuntimeError(f"unexpected: {resp}")
                self.session_id = resp["payload"]["session_id"]
                await self._drain_hello_extras()
                # Session id in body (cleared on next 请说)
                self._set(DeviceState.ONLINE, f"会话 {self.session_id}")
                logger.info(
                    "Connected session={} tts={} pet={}",
                    self.session_id,
                    resp["payload"].get("tts_id"),
                    resp["payload"].get("pet_id"),
                )
                if self.heartbeat_seconds and self.heartbeat_seconds > 0:
                    self._hb = asyncio.create_task(self._heartbeat())
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
                delay = self.reconnect_delay * (2 ** min(i, 5))
                self._set(DeviceState.CONNECTING, f"重试 {i + 1}/{self.reconnect_retries}")
                logger.warning("connect failed: {} — wait {:.1f}s", exc, delay)
                await asyncio.sleep(delay)
        self._set(DeviceState.ERROR, "连接失败")
        raise RuntimeError(f"cannot connect: {last}")

    async def _drain_hello_extras(self) -> None:
        """Consume catalog pushes that follow session.accept (short timeout)."""
        assert self._ws
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=0.25)
            except asyncio.TimeoutError:
                return
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype in ("tts.list.result", "pets.list.result", "agents.list.result", "device.pong"):
                continue
            logger.debug("hello drain saw {}; ignoring", mtype)

    async def close(self) -> None:
        if self._hb:
            self._hb.cancel()
            self._hb = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.heartbeat_seconds)
                if self._ws:
                    await self._ws.send(ping())
        except (asyncio.CancelledError, ConnectionClosed):
            return

    async def ensure_connected(self) -> None:
        if self._ws is not None and self.session_id:
            return
        await self.connect()

    async def talk_once(self, stop_event) -> None:
        """Record until stop_event (second click / Enter), then send + recv."""
        try:
            await self.ensure_connected()
            assert self._ws and self.session_id
            self._set(DeviceState.LISTENING, "再点结束")
            audio = await asyncio.to_thread(
                record_until_stop,
                stop_event,
                self.sample_rate,
                max_seconds=max(self.record_seconds, 60.0),
                device=self.audio_device,
            )
            await self._send_wav_and_recv(audio)
        except ConnectionClosed:
            logger.warning("connection lost during talk — reconnecting")
            self._ws = None
            self.session_id = None
            try:
                await self.connect()
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError("连接中断，请再按一次") from None

    async def talk_wav(self, audio: bytes) -> None:
        """Send a captured WAV (wake/VAD path) and wait for the turn."""
        try:
            await self.ensure_connected()
            await self._send_wav_and_recv(audio)
        except ConnectionClosed:
            logger.warning("connection lost during talk — reconnecting")
            self._ws = None
            self.session_id = None
            try:
                await self.connect()
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError("连接中断，请再说一次唤醒词") from None

    async def _send_wav_and_recv(self, audio: bytes) -> None:
        assert self._ws and self.session_id
        if not audio:
            self._set(DeviceState.ONLINE, "空录音")
            return
        await self._ws.send(audio_start(self.session_id))
        mv = memoryview(audio)
        chunk = 4096
        for i in range(0, len(mv), chunk):
            await self._ws.send(mv[i : i + chunk])
        await self._ws.send(audio_end(self.session_id))
        self._set(DeviceState.PROCESSING, "执行")
        await self._recv_turn()

    async def cancel(self) -> None:
        if self._ws and self.session_id:
            await self._ws.send(session_cancel(self.session_id))

    def _merge_reply(self, chunk: str) -> str:
        """Accumulate agent.message pieces into one OLED body."""
        text = (chunk or "").strip()
        if not text:
            return self._turn_reply
        prev = self._turn_reply
        if not prev:
            self._turn_reply = text
        elif text.startswith(prev):
            self._turn_reply = text
        elif prev.endswith(text):
            pass
        else:
            self._turn_reply = f"{prev}{text}"
        return self._turn_reply

    async def _recv_turn(self) -> None:
        """Receive one turn; keep reading the socket while audio plays in parallel."""
        assert self._ws
        tts_buf = bytearray()
        fmt = "wav"
        end = {"agent.done", "agent.cancel", "agent.error", "error"}
        self._view.reset_turn()
        self._turn_reply = ""

        play_q: asyncio.Queue[tuple[bytes, str] | None] = asyncio.Queue()

        async def _player() -> None:
            while True:
                item = await play_q.get()
                if item is None:
                    return
                data, _fmt = item
                self._set(DeviceState.SPEAKING, None)
                try:
                    await asyncio.to_thread(play_bytes, data, self.playback_device)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("playback failed: {}", exc)

        player_task = asyncio.create_task(_player())
        try:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    tts_buf.extend(raw)
                    continue
                msg = json.loads(raw)
                mtype = msg["type"]
                payload = msg.get("payload", {})
                if mtype == "device.pong":
                    continue

                oled = self._view.handle(mtype, payload)
                if mtype == "stt.final":
                    # Prefer payload; getattr for older turn_view on device
                    user = (
                        payload.get("text")
                        or getattr(self._view, "last_user_text", None)
                        or ""
                    )
                    user = str(user).strip()
                    if user:
                        self._set(DeviceState.PROCESSING, user)
                    self._set(DeviceState.PROCESSING, "执行")
                elif mtype in ("agent.thinking", "agent.tool_call", "agent.tool_result"):
                    self._set(DeviceState.PROCESSING, "执行")
                elif mtype == "agent.message":
                    full = self._merge_reply(oled or self._view.last_oled_line or "")
                    if full:
                        self._set(DeviceState.PROCESSING, full)
                elif mtype == "tts.start":
                    fmt = payload.get("format") or "wav"
                    tts_buf.clear()
                    self._set(DeviceState.SPEAKING, None)
                elif mtype == "tts.end":
                    if tts_buf:
                        await play_q.put((bytes(tts_buf), fmt))
                        tts_buf.clear()
                    self._set(DeviceState.SPEAKING, None)
                elif mtype in end:
                    break
        finally:
            await play_q.put(None)
            try:
                await player_task
            except Exception:  # noqa: BLE001
                logger.exception("player task failed")

        # Preserve last reply; main loop sets 待命 without clearing body
        self._set(DeviceState.ONLINE, None)
