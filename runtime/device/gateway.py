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
    session_reset_ok,
    stt_final,
    tts_list_result,
    tts_selected,
)
from runtime.protocol.wire import decode_message, encode_message
from runtime.security.auth import DeviceAuth
from runtime.session.agent_memory import quarantine_device_sessions
from runtime.session.manager import SessionManager
from runtime.session.models import Session
from runtime.transport.speech.base import STTProvider
from runtime.transport.speech.registry import TTSRegistry

# Bound how long reconnect / cancel may wait on to_thread TTS/STT work.
_TURN_CANCEL_TIMEOUT_S = 1.5
_WS_CLOSE_TIMEOUT_S = 2.0


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
        sessions_root: Path | None = None,
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
        self.sessions_root = sessions_root
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
        await self._force_close(conn.ws)
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
        target: set[str] = set()
        if kind in ("tts", "agent"):
            target.add(kind)
        elif kind is None:
            target.update({"tts", "agent"})
        for conn in list(self._connections.values()):
            if conn.session and target:
                busy = bool(conn.turn_task and not conn.turn_task.done())
                if busy:
                    # Keep current utterance on the old voice/agent; apply after.
                    conn.pending_default_kinds |= target
                else:
                    self._sync_session_defaults(conn, kinds=target)
                    conn.pending_default_kinds -= target
            for message in messages:
                try:
                    await conn.send(message)
                except Exception:  # noqa: BLE001
                    logger.debug("failed to push defaults to {}", conn.device_id)
                    break

    def _sync_session_defaults(self, conn: DeviceConnection, *, kinds: set[str]) -> None:
        """Write registry defaults onto the live session (idle connections only)."""
        if not conn.session or not kinds:
            return
        if "tts" in kinds:
            new_tts = self.tts_registry.default_id
            if new_tts != conn.session.tts_id:
                conn.session.tts_model = None
            conn.session.tts_id = new_tts
        if "agent" in kinds and self.default_agent_id:
            conn.session.agent_id = self.default_agent_id

    def _flush_pending_defaults(self, conn: DeviceConnection) -> None:
        if not conn.pending_default_kinds or not conn.session:
            return
        # Skip if another turn already started (callback raced with a new turn).
        if conn.turn_task and not conn.turn_task.done():
            return
        kinds = set(conn.pending_default_kinds)
        conn.pending_default_kinds.clear()
        self._sync_session_defaults(conn, kinds=kinds)
        logger.info(
            "[{}] applied deferred defaults {}",
            conn.device_id,
            ",".join(sorted(kinds)),
        )

    def _track_turn(
        self,
        conn: DeviceConnection,
        task: asyncio.Task | None,
    ) -> asyncio.Task | None:
        """Attach turn completion so deferred TTS/agent defaults can land."""
        if task is None:
            self._flush_pending_defaults(conn)
            return None

        def _done(finished: asyncio.Task) -> None:
            if conn.turn_task is finished:
                conn.turn_task = None
            self._flush_pending_defaults(conn)

        task.add_done_callback(_done)
        return task

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

    @staticmethod
    async def _force_close(ws: websockets.WebSocketServerProtocol) -> None:
        """Close with a hard deadline so half-closed peers cannot wedge handlers."""
        try:
            await asyncio.wait_for(ws.close(), timeout=_WS_CLOSE_TIMEOUT_S)
        except Exception:  # noqa: BLE001
            logger.debug("ws.close timed out or failed; aborting transport")
        transport = getattr(ws, "transport", None)
        if transport is not None:
            try:
                transport.abort()
            except Exception:  # noqa: BLE001
                pass

    async def _retire(self, conn: DeviceConnection) -> None:
        await self._stop_turn(conn)
        if conn.session:
            conn.session.request_cancel()
        await self._force_close(conn.ws)

    async def _stop_turn(self, conn: DeviceConnection) -> None:
        task = conn.turn_task
        conn.turn_task = None
        await self._await_cancelled(task, label="turn")

    @staticmethod
    async def _await_cancelled(
        task: asyncio.Task | None,
        *,
        label: str = "turn",
    ) -> None:
        """Cancel a turn task but never block forever on to_thread work.

        Uses ``asyncio.wait`` (not ``wait_for``): the latter cancels the waiter
        and then still awaits the task to finish, which re-blocks on TTS/STT
        threads that ignore cancellation until the worker returns.
        """
        if task is None or task.done():
            return
        task.cancel()
        _done, pending = await asyncio.wait({task}, timeout=_TURN_CANCEL_TIMEOUT_S)
        if pending:
            logger.warning(
                "{} cancel timed out after {}s; detaching",
                label,
                _TURN_CANCEL_TIMEOUT_S,
            )
            return
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            if client_disconnected(exc):
                logger.info("{} ended; client disconnected", label)
            else:
                logger.exception("{} ended with error during cancel", label)

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
            close_timeout=5,
            ping_interval=20,
            ping_timeout=20,
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
                conn.turn_task = self._track_turn(
                    conn, await self._dispatch(conn, raw, conn.turn_task)
                )
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
            await self._force_close(ws)

    @staticmethod
    async def _replace_turn(
        session: Session | None,
        turn_task: asyncio.Task | None,
    ) -> None:
        """Cancel in-flight turn so a new user/audio turn does not pile up.

        Does not reset_cancel here — pipeline.run_turn clears the flag at turn start.
        Clearing it immediately would drop cooperative cancel for in-flight TTS.
        """
        await DeviceGateway._await_cancelled(turn_task, label="previous turn")
        if session is not None:
            session.request_cancel()

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
                await self._force_close(conn.ws)
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
                # Never block hello on old teardown (to_thread TTS / half-closed close).
                asyncio.create_task(
                    self._retire(previous),
                    name=f"retire-{device_id}",
                )
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

        if msg.type in (
            DeviceMessageType.AGENTS_LIST,
            DeviceMessageType.TTS_LIST,
            DeviceMessageType.PETS_LIST,
            DeviceMessageType.TTS_SELECT,
            DeviceMessageType.SESSION_CANCEL,
            DeviceMessageType.SESSION_RESET,
            DeviceMessageType.USER_MESSAGE,
            DeviceMessageType.AUDIO_START,
            DeviceMessageType.AUDIO_END,
        ):
            if conn.session is None:
                await conn.send(encode_message(error_msg("hello required")))
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
            # Explicit client pick wins over a deferred admin/MCP default.
            conn.pending_default_kinds.discard("tts")
            await conn.send(encode_message(tts_selected(sid, tts_id, model)))
            return turn_task

        if msg.type == DeviceMessageType.SESSION_CANCEL:
            sid = msg.payload.get("session_id", "")
            session = self._own_session(conn, sid)
            if session:
                session.request_cancel()
                logger.info("[{}] cancel requested", sid)
            await self._await_cancelled(turn_task, label=f"cancel[{sid}]")
            conn.turn_task = None
            return None

        if msg.type == DeviceMessageType.SESSION_RESET:
            return await self._handle_session_reset(conn, turn_task)

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

    def reset_device_memory(self, device_id: str) -> dict[str, Any]:
        """Clear Runtime context + quarantine Agent session files for a device.

        Safe to call from the Admin/MCP thread. Device WS path should use
        ``reset_device_memory_async`` so disk work leaves the event loop.
        """
        did = (device_id or "").strip()
        if not did:
            raise ValueError("device_id 不能为空")
        cleared_live = False
        conn = self._connections.get(did)
        if conn and conn.session:
            conn.session.clear_context()
            cleared_live = True
        quarantined: list[str] = []
        if self.sessions_root is not None:
            quarantined = quarantine_device_sessions(
                self.sessions_root,
                did,
                reason="reset",
            )
        logger.info(
            "session reset device={} live={} quarantined={}",
            did,
            cleared_live,
            len(quarantined),
        )
        return {
            "ok": True,
            "device_id": did,
            "cleared_runtime_context": cleared_live,
            "quarantined": quarantined,
        }

    async def reset_device_memory_async(self, device_id: str) -> dict[str, Any]:
        """Async variant: clear live context on-loop, quarantine off-loop."""
        did = (device_id or "").strip()
        if not did:
            raise ValueError("device_id 不能为空")
        cleared_live = False
        conn = self._connections.get(did)
        if conn and conn.session:
            conn.session.clear_context()
            cleared_live = True
        quarantined: list[str] = []
        root = self.sessions_root
        if root is not None:
            quarantined = await asyncio.to_thread(
                quarantine_device_sessions,
                root,
                did,
                reason="reset",
            )
        logger.info(
            "session reset device={} live={} quarantined={}",
            did,
            cleared_live,
            len(quarantined),
        )
        return {
            "ok": True,
            "device_id": did,
            "cleared_runtime_context": cleared_live,
            "quarantined": quarantined,
        }

    async def _handle_session_reset(
        self,
        conn: DeviceConnection,
        turn_task: asyncio.Task | None,
    ) -> None:
        if not conn.device_id or not conn.session:
            await conn.send(encode_message(error_msg("not connected")))
            return None
        # Stop in-flight turn first (same as cancel) — bounded wait.
        if turn_task and not turn_task.done():
            conn.session.request_cancel()
        await self._await_cancelled(turn_task, label="reset turn")
        conn.turn_task = None
        result = await self.reset_device_memory_async(conn.device_id)
        await conn.send(
            encode_message(
                session_reset_ok(
                    conn.session.session_id,
                    conn.device_id,
                    quarantined=list(result.get("quarantined") or []),
                )
            )
        )
        return None

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
