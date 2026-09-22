"""Session Manager — live device WS sessions (not chat history)."""

from __future__ import annotations

import uuid

from loguru import logger

from runtime.session.models import Session


class SessionManager:
    def __init__(self, *, max_context: int = 40) -> None:
        self._sessions: dict[str, Session] = {}
        self._by_device: dict[str, str] = {}
        self.max_context = max_context

    def create(self, device_id: str, device_type: str = "unknown") -> Session:
        old_sid = self._by_device.get(device_id)
        if old_sid:
            self.remove(old_sid)
        sid = uuid.uuid4().hex[:12]
        session = Session(
            session_id=sid,
            device_id=device_id,
            device_type=device_type,
            max_context=self.max_context,
        )
        self._sessions[sid] = session
        self._by_device[device_id] = sid
        logger.info("Session created: {} for device {}", sid, device_id)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_by_device(self, device_id: str) -> Session | None:
        sid = self._by_device.get(device_id)
        return self._sessions.get(sid) if sid else None

    def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session and self._by_device.get(session.device_id) == session_id:
            self._by_device.pop(session.device_id, None)

    def list(self) -> list[Session]:
        return list(self._sessions.values())

    def list_dicts(self) -> list[dict]:
        out = []
        for s in self._sessions.values():
            out.append(
                {
                    "session_id": s.session_id,
                    "device_id": s.device_id,
                    "device_type": s.device_type,
                    "agent_id": s.agent_id,
                    "tts_id": s.tts_id,
                    "tts_model": s.tts_model,
                    "created_at": s.created_at,
                    "context_turns": len(s.context),
                    "cancel_pending": s.cancel_event.is_set(),
                }
            )
        return out

    @property
    def active_count(self) -> int:
        return len(self._sessions)
