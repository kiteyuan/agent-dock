"""Bridge pipeline — one turn: intent → route → agent.run → events → device (+ optional TTS)."""

from __future__ import annotations

import asyncio

from loguru import logger

from runtime.agent.router import AgentRouter
from runtime.bridge.bus import EventBus, client_disconnected
from runtime.protocol.agent import AgentEventType, AgentRequest, agent_cancel, agent_error
from runtime.protocol.device import tts_end, tts_start
from runtime.protocol.wire import encode_message
from runtime.session.models import Session
from runtime.transport.speech.registry import TTSRegistry
from runtime.transport.speech.speak_text import SentenceBuffer, is_speakable, speak_text

# Device WS / TTS must not wedge the turn forever (slow or half-closed clients).
_DEVICE_SEND_TIMEOUT_S = 15.0
_TTS_SEGMENT_TIMEOUT_S = 180.0
_TTS_WORKER_JOIN_TIMEOUT_S = 180.0


class BridgePipeline:
    def __init__(
        self,
        router: AgentRouter,
        tts_registry: TTSRegistry | None = None,
        *,
        workspace: str | None = None,
    ) -> None:
        self.router = router
        self.tts_registry = tts_registry or TTSRegistry()
        self.workspace = workspace
        self.prepare_turn = None

    async def _send(self, bus: EventBus, data: str | bytes) -> bool:
        try:
            await asyncio.wait_for(bus._send(data), timeout=_DEVICE_SEND_TIMEOUT_S)
            return True
        except asyncio.TimeoutError:
            logger.warning("device send timed out ({}s)", _DEVICE_SEND_TIMEOUT_S)
            return False
        except Exception as exc:  # noqa: BLE001
            if client_disconnected(exc):
                logger.info("device send skipped; client disconnected")
                return False
            logger.exception("device send failed")
            return False

    async def _publish(self, bus: EventBus, event: object) -> bool:
        try:
            await asyncio.wait_for(bus.publish(event), timeout=_DEVICE_SEND_TIMEOUT_S)  # type: ignore[arg-type]
            return True
        except asyncio.TimeoutError:
            logger.warning("device publish timed out for {}", getattr(event, "type", event))
            return False
        except Exception as exc:  # noqa: BLE001
            if client_disconnected(exc):
                logger.info("device publish skipped; client disconnected")
                return False
            logger.exception("device publish failed")
            return False

    async def _synthesize_segment(
        self,
        session: Session,
        bus: EventBus,
        text: str,
    ) -> None:
        tts = self.tts_registry.get(session.tts_id)
        if not tts or not is_speakable(text):
            if text and not is_speakable(text):
                logger.info("[{}] skip non-speakable TTS chunk {!r}", session.session_id, text)
            return

        audio: bytes | None = None
        used = tts
        try:
            audio = await asyncio.wait_for(
                tts.synthesize(text, model=session.tts_model),
                timeout=_TTS_SEGMENT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("[{}] TTS timed out for {!r}", session.session_id, text[:40])
            return
        except Exception:
            logger.exception("[{}] TTS failed for {!r}", session.session_id, text[:40])
            return

        if not audio:
            logger.warning("[{}] TTS returned empty audio for {!r}", session.session_id, text[:40])
            return

        fmt = used.info.audio_format or "wav"
        started = False
        try:
            if not await self._send(
                bus,
                encode_message(
                    tts_start(session.session_id, used.info.id, format=fmt, text=text)
                ),
            ):
                return
            started = True
            if not await self._send(bus, audio):
                return
        finally:
            if started:
                await self._send(bus, encode_message(tts_end(session.session_id)))

    def _apply_tts_selection(
        self,
        session: Session,
        *,
        tts_id: str | None,
        tts_model: str | None,
    ) -> None:
        """Switch provider/model without leaking a previous provider's model id."""
        if tts_id:
            if tts_id != session.tts_id:
                session.tts_model = tts_model or None
            elif tts_model:
                session.tts_model = tts_model
            session.tts_id = tts_id
        elif tts_model:
            session.tts_model = tts_model

    async def run_turn(
        self,
        session: Session,
        text: str,
        bus: EventBus,
        *,
        agent_id: str | None = None,
        tts_id: str | None = None,
        tts_model: str | None = None,
    ) -> None:
        session.reset_cancel()
        self._apply_tts_selection(session, tts_id=tts_id, tts_model=tts_model)

        if self.prepare_turn is not None:
            try:
                await asyncio.to_thread(
                    self.prepare_turn,
                    agent_id or session.agent_id,
                    session.tts_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[{}] sidecar not ready: {}", session.session_id, exc)
                await self._publish(bus, agent_error(session.session_id, str(exc)))
                return

        try:
            adapter = self.router.resolve(
                device_id=session.device_id,
                agent_id=agent_id or session.agent_id,
            )
        except (KeyError, PermissionError) as exc:
            await self._publish(bus, agent_error(session.session_id, str(exc)))
            return

        # Commit user turn only after routing succeeds; exclude it from context
        # so agents that echo both ``text`` and ``context`` do not double the prompt.
        session.add_turn("user", text)
        session.agent_id = adapter.info.id
        request = AgentRequest(
            session_id=session.session_id,
            text=text,
            context=list(session.context[:-1]),
            device=session.device_info(),
            agent_id=adapter.info.id,
            workspace=self.workspace,
            cancel_event=session.cancel_event,
        )

        speak_buf = SentenceBuffer()
        speak_q: asyncio.Queue[str | None] = asyncio.Queue()
        tts = self.tts_registry.get(session.tts_id)

        async def tts_worker() -> None:
            while True:
                item = await speak_q.get()
                if item is None:
                    break
                if session.cancel_event.is_set():
                    continue
                await self._synthesize_segment(session, bus, item)

        worker: asyncio.Task[None] | None = None
        if tts:
            worker = asyncio.create_task(tts_worker())

        async def enqueue_sentences(parts: list[str]) -> None:
            if not worker:
                return
            for sent in parts:
                if not is_speakable(sent):
                    continue
                logger.info(
                    "[{}] TTS sentence ({} chars) {!r}",
                    session.session_id,
                    len(sent),
                    sent[:40],
                )
                await speak_q.put(sent)

        terminal = None
        cancelled = False
        try:
            async for event in adapter.run(request):
                logger.info("[{}] {}", session.session_id, event.type.value)
                if event.type == AgentEventType.ERROR and event.content:
                    logger.warning("[{}] {}", session.session_id, event.content)

                if event.type in (
                    AgentEventType.DONE,
                    AgentEventType.CANCEL,
                    AgentEventType.ERROR,
                ):
                    # Defer terminal event until after TTS so clients don't hang up early
                    terminal = event
                    break

                if not await self._publish(bus, event):
                    terminal = agent_error(
                        session.session_id, "device send failed; aborting turn"
                    )
                    break

                if event.type == AgentEventType.MESSAGE and event.content:
                    session.add_turn("assistant", event.content)
                    # Dual-channel: only speak=True messages go to TTS
                    if event.speak and worker:
                        piece = speak_text(event.content)
                        if piece and piece != event.content.strip():
                            logger.info(
                                "[{}] speak_text sanitized for TTS", session.session_id
                            )
                        if piece:
                            await enqueue_sentences(speak_buf.push(piece))
        except asyncio.CancelledError:
            session.request_cancel()
            cancelled = True
            terminal = agent_cancel(session.session_id)
            current = asyncio.current_task()
            if current is not None:
                uncancel = getattr(current, "uncancel", None)
                if callable(uncancel):
                    uncancel()
        finally:
            if worker:
                try:
                    if cancelled or session.cancel_event.is_set():
                        cancelled = True
                        worker.cancel()
                        try:
                            await worker
                        except asyncio.CancelledError:
                            pass
                    else:
                        if terminal is None or terminal.type == AgentEventType.DONE:
                            await enqueue_sentences(speak_buf.flush())
                        await speak_q.put(None)
                        await asyncio.wait_for(worker, timeout=_TTS_WORKER_JOIN_TIMEOUT_S)
                except asyncio.TimeoutError:
                    logger.warning("[{}] TTS worker join timed out", session.session_id)
                    worker.cancel()
                except asyncio.CancelledError:
                    cancelled = True
                    terminal = agent_cancel(session.session_id)
                    worker.cancel()
                except Exception:  # noqa: BLE001
                    logger.exception("[{}] TTS worker cleanup failed", session.session_id)

        if cancelled or session.cancel_event.is_set():
            terminal = agent_cancel(session.session_id)
        elif terminal is None:
            terminal = agent_error(
                session.session_id, "agent ended without a terminal event"
            )
        await self._publish(bus, terminal)
