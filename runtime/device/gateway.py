"""Device Gateway — WebSocket entry for Device Protocol."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import websockets
from loguru import logger

from runtime.agent.registry import AgentRegistry
from runtime.bridge.bus import EventBus, client_disconnected
from runtime.bridge.pipeline import BridgePipeline
from runtime.device.connection import DeviceConnection
from runtime.pets import list_pets
from runtime.protocol.agent import agent_cancel
from runtime.protocol.device import (
    DeviceMessageType,
    agents_list_result,
    error_msg,
    pets_list_result,
    pong,
    session_accept,
    stt_final,
    tts_list_result,
    tts_selected,
)
from runtime.protocol.wire import decode_message, encode_message
from runtime.security.auth import DeviceAuth
from runtime.session.manager import SessionManager
from runtime.session.models import Session
from runtime.transport.speech.base import STTProvider
from runtime.transport.speech.registry import TTSRegistry


class DeviceGateway:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        sessions: SessionManager,
        auth: DeviceAuth,
        pipeline: BridgePipeline,
        registry: AgentRegistry,
        tts_registry: TTSRegistry,
        stt: STTProvider | None = None,
        advertise_url: str | None = None,
        pets_root: Path | None = None,
        assets_port: int | None = None,
        assets_base_url: str | None = None,
        default_agent_id: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.sessions = sessions
        self.auth = auth
        self.pipeline = pipeline
        self.registry = registry
        self.tts_registry = tts_registry
        self.stt = stt
        self.advertise_url = advertise_url
        self.pets_root = pets_root
        self.assets_port = assets_port
        self.assets_base_url = assets_base_url
        self.default_agent_id = default_agent_id
        self._connections: dict[str, DeviceConnection] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        # Match websockets.serve max_size so a single frame cannot overshoot the buffer.
        self._max_audio_bytes = 16 * 1024 * 1024

    def list_devices(self) -> list[dict]:
        return [c.snapshot() for c in self._connections.values() if c.device_id]

    def schedule(self, coro: Any) -> Any:
        """Run a coroutine on the gateway event loop (safe from admin HTTP threads)."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("gateway loop not running")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def disconnect_device(self, device_id: str) -> bool:
        conn = self._connections.get(device_id)
        if not conn:
            return False
        await self._stop_turn(conn)
        if conn.session:
            conn.session.request_cancel()
        try:
            await conn.ws.close()
        except Exception:  # noqa: BLE001
            logger.debug("disconnect close failed for {}", device_id)
        return True

    async def broadcast_defaults(self, kind: str | None = None) -> None:
        pets: list = []
        pet_default = None
        if self.pets_root is not None:
            pets, pet_default = list_pets(self.pets_root)
        messages = [
            encode_message(
                tts_list_result(
                    self.tts_registry.list_dicts(),
                    self.tts_registry.default_id,
                )
            ),
            encode_message(
                pets_list_result(
                    pets,
                    default_id=pet_default,
                    base_url=self.assets_base_url,
                    assets_port=self.assets_port,
                )
            ),
        ]
        for conn in list(self._connections.values()):
            busy = bool(conn.turn_task and not conn.turn_task.done())
            # Never mutate an in-flight turn's routing keys mid-utterance.
            if conn.session and not busy:
                if kind == "tts":
                    new_tts = self.tts_registry.default_id
                    if new_tts != conn.session.tts_id:
                        conn.session.tts_model = None
                    conn.session.tts_id = new_tts
                if kind == "agent":
                    conn.session.agent_id = self.default_agent_id
            for message in messages:
                try:
                    await conn.send(message)
                except Exception:  # noqa: BLE001
                    logger.debug("failed to push defaults to {}", conn.device_id)
                    break

    async def cancel_session(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        session.request_cancel()
        for conn in list(self._connections.values()):
            if conn.session and conn.session.session_id == session_id:
                await self._stop_turn(conn)
                break
        logger.info("[{}] cancel requested (admin)", session_id)
        return True

    async def _retire(self, conn: DeviceConnection) -> None:
        await self._stop_turn(conn)
        if conn.session:
            conn.session.request_cancel()
        try:
            await conn.ws.close()
        except Exception:  # noqa: BLE001
            logger.debug("close previous device socket failed")

    async def _stop_turn(self, conn: DeviceConnection) -> None:
        task = conn.turn_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                if client_disconnected(exc):
                    logger.info("turn ended; client disconnected")
                else:
                    logger.exception("turn ended with error during cancel")
        conn.turn_task = None

    def _own_session(self, conn: DeviceConnection, session_id: str) -> Session | None:
        session = self.sessions.get(session_id) if session_id else None
        if session is None or conn.session is None:
            return None
        if conn.session.session_id != session.session_id:
            return None
        return session

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        logger.info("DeviceGateway on ws://{}:{}", self.host, self.port)
        if self.advertise_url:
            logger.info("Advertise URL (Tailscale/public): {}", self.advertise_url)
        async with websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=self._max_audio_bytes,
        ):
            await asyncio.Future()

    async def _handler(self, ws: websockets.WebSocketServerProtocol) -> None:
        conn = DeviceConnection(ws=ws)
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    if (
                        conn.session is None
                        or not conn.recording
                        or conn.audio_overflow
                    ):
                        continue
                    if len(conn.audio_buf) + len(raw) > self._max_audio_bytes:
                        conn.audio_buf.clear()
                        conn.audio_overflow = True
                        conn.recording = False
                        logger.warning(
                            "[{}] audio exceeded {} bytes; drop this take",
                            conn.device_id,
                            self._max_audio_bytes,
                        )
                        await conn.send(
                            encode_message(error_msg("audio buffer exceeded"))
                        )
                        continue
                    conn.audio_buf.extend(raw)
                    continue
                conn.turn_task = await self._dispatch(conn, raw, conn.turn_task)
        except websockets.ConnectionClosed:
            logger.info("Device disconnected: {}", conn.device_id)
        except Exception as exc:  # noqa: BLE001
            if not client_disconnected(exc):
                logger.exception("device connection failed")
            else:
                logger.info("Device disconnected: {}", conn.device_id)
        finally:
            if conn.device_id and self._connections.get(conn.device_id) is conn:
                self._connections.pop(conn.device_id, None)
            await self._stop_turn(conn)
            if conn.session:
                conn.session.request_cancel()
                self.sessions.remove(conn.session.session_id)

    @staticmethod
    async def _replace_turn(
        session: Session | None,
        turn_task: asyncio.Task | None,
    ) -> None:
        """Cancel in-flight turn so a new user/audio turn does not pile up."""
        if turn_task and not turn_task.done():
            turn_task.cancel()
            try:
                await turn_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                if client_disconnected(exc):
                    logger.info("previous turn ended; client disconnected")
                else:
                    logger.exception("previous turn ended with error during cancel")
        if session is not None:
            session.request_cancel()
            session.reset_cancel()

    async def _dispatch(
        self,
        conn: DeviceConnection,
        raw: str,
        turn_task: asyncio.Task | None,
    ) -> asyncio.Task | None:
        try:
            msg = decode_message(raw)
        except Exception as exc:  # noqa: BLE001
            await conn.send(encode_message(error_msg(f"bad message: {exc}")))
            return turn_task

        if msg.type == DeviceMessageType.DEVICE_HELLO:
            device_id = msg.payload.get("device_id", "unknown")
            token = msg.payload.get("token")
            result = self.auth.authenticate(device_id, token)
            if not result.ok:
                await conn.send(encode_message(error_msg(result.reason or "auth failed")))
                await conn.ws.close()
                return turn_task
            # Always stop any in-flight turn on this socket before swapping sessions.
            await self._replace_turn(conn.session, turn_task)
            conn.recording = False
            conn.audio_buf.clear()
            conn.audio_overflow = False
            conn.device_id = device_id
            conn.device_type = msg.payload.get("device_type", "unknown")
            previous = self._connections.pop(device_id, None)
            if previous is not None and previous is not conn:
                await self._retire(previous)
            conn.session = self.sessions.create(device_id, conn.device_type)
            # Thin clients: Runtime owns TTS/agent/pet defaults (ignore hello.tts_id).
            preferred_tts = self.tts_registry.default_id
            if preferred_tts and self.tts_registry.get(preferred_tts):
                conn.session.tts_id = preferred_tts
            if self.default_agent_id:
                conn.session.agent_id = self.default_agent_id
            pets: list = []
            pet_default = None
            if self.pets_root is not None:
                pets, pet_default = list_pets(self.pets_root)
            self._connections[device_id] = conn
            await conn.send(
                encode_message(
                    session_accept(
                        conn.session.session_id,
                        device_id,
                        advertise_url=self.advertise_url,
                        tts_id=conn.session.tts_id,
                        pet_id=pet_default,
                        agent_id=conn.session.agent_id,
                        assets_port=self.assets_port,
                        assets_base_url=self.assets_base_url,
                    )
                )
            )
            # Push catalogs so shells need not request or configure them.
            await conn.send(
                encode_message(
                    tts_list_result(self.tts_registry.list_dicts(), self.tts_registry.default_id)
                )
            )
            await conn.send(
                encode_message(
                    pets_list_result(
                        pets,
                        default_id=pet_default,
                        base_url=self.assets_base_url,
                        assets_port=self.assets_port,
                    )
                )
            )
            logger.info("Device connected: {} ({})", device_id, conn.device_type)
            return None

        if msg.type == DeviceMessageType.PING:
            await conn.send(encode_message(pong(msg.payload.get("ping_id") or msg.id)))
            return turn_task

        if msg.type == DeviceMessageType.AGENTS_LIST:
            await conn.send(encode_message(agents_list_result(self.registry.list_dicts())))
            return turn_task

        if msg.type == DeviceMessageType.TTS_LIST:
            await conn.send(
                encode_message(
                    tts_list_result(self.tts_registry.list_dicts(), self.tts_registry.default_id)
                )
            )
            return turn_task

        if msg.type == DeviceMessageType.PETS_LIST:
            pets: list = []
            default_id = None
            if self.pets_root is not None:
                pets, default_id = list_pets(self.pets_root)
            await conn.send(
                encode_message(
                    pets_list_result(
                        pets,
                        default_id=default_id,
                        base_url=self.assets_base_url,
                        assets_port=self.assets_port,
                    )
                )
            )
            return turn_task

        if msg.type == DeviceMessageType.TTS_SELECT:
            sid = msg.payload.get("session_id", "")
            tts_id = msg.payload.get("tts_id", "")
            model = msg.payload.get("model")
            session = self._own_session(conn, sid)
            if not session:
                await conn.send(encode_message(error_msg("unknown session")))
                return turn_task
            if tts_id and not self.tts_registry.get(tts_id):
                await conn.send(encode_message(error_msg(f"unknown tts: {tts_id}", sid)))
                return turn_task
            if tts_id and tts_id != session.tts_id:
                session.tts_model = model or None
            else:
                session.tts_model = model
            session.tts_id = tts_id or None
            await conn.send(encode_message(tts_selected(sid, tts_id, model)))
            return turn_task

        if msg.type == DeviceMessageType.SESSION_CANCEL:
            sid = msg.payload.get("session_id", "")
            session = self._own_session(conn, sid)
            if session:
                session.request_cancel()
                logger.info("[{}] cancel requested", sid)
            if turn_task and not turn_task.done():
                turn_task.cancel()
                try:
                    await turn_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    if not client_disconnected(exc):
                        logger.exception("[{}] cancel await failed", sid)
            return None

        if msg.type == DeviceMessageType.USER_MESSAGE:
            sid = msg.payload.get("session_id", "")
            text = msg.payload.get("text", "")
            agent_id = msg.payload.get("agent_id")
            tts_id = msg.payload.get("tts_id")
            tts_model = msg.payload.get("tts_model")
            session = self._own_session(conn, sid)
            if not session:
                await conn.send(encode_message(error_msg("unknown session")))
                return turn_task
            await self._replace_turn(session, turn_task)
            bus = EventBus(conn.send)
            return asyncio.create_task(
                self.pipeline.run_turn(
                    session,
                    text,
                    bus,
                    agent_id=agent_id,
                    tts_id=tts_id,
                    tts_model=tts_model,
                )
            )

        if msg.type == DeviceMessageType.AUDIO_START:
            conn.audio_buf.clear()
            conn.audio_overflow = False
            conn.recording = True
            return turn_task

        if msg.type == DeviceMessageType.AUDIO_END:
            conn.recording = False
            sid = msg.payload.get("session_id", "")
            session = self._own_session(conn, sid)
            if not session:
                conn.audio_buf.clear()
                conn.audio_overflow = False
                await conn.send(encode_message(error_msg("unknown session")))
                return turn_task
            if conn.audio_overflow:
                conn.audio_buf.clear()
                conn.audio_overflow = False
                await conn.send(
                    encode_message(error_msg("recording too long; try a shorter take", sid))
                )
                return turn_task
            if not self.stt:
                conn.audio_buf.clear()
                await conn.send(
                    encode_message(error_msg("STT not configured; use user.message", sid))
                )
                return turn_task
            audio = bytes(conn.audio_buf)
            conn.audio_buf.clear()
            await self._replace_turn(session, turn_task)
            return asyncio.create_task(self._audio_turn(conn, session, sid, audio))

        return turn_task

    async def _audio_turn(
        self,
        conn: DeviceConnection,
        session: Session,
        sid: str,
        audio: bytes,
    ) -> None:
        """STT + pipeline off the WS read loop so cancel/ping stay responsive."""
        assert self.stt is not None
        try:
            text = await self.stt.transcribe(audio)
        except asyncio.CancelledError:
            try:
                bus = EventBus(conn.send)
                await bus.publish(agent_cancel(sid))
            except Exception:  # noqa: BLE001
                logger.debug("[{}] failed to publish agent.cancel after STT cancel", sid)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("STT failed")
            await conn.send(encode_message(error_msg(f"STT failed: {exc}", sid)))
            return
        if not text.strip():
            await conn.send(encode_message(error_msg("STT produced empty text", sid)))
            return
        await conn.send(encode_message(stt_final(sid, text)))
        bus = EventBus(conn.send)
        await self.pipeline.run_turn(session, text, bus, agent_id=session.agent_id)
