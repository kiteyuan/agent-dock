"""HTTP Agent — public Agent Protocol (agentdock.agent/1.0) client."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
from typing import Any, Iterator
from urllib.request import Request

from runtime.agent.base import AgentAdapter
from runtime.protocol.agent import (
    PROTOCOL_VERSION,
    AgentEventStream,
    AgentEventType,
    AgentInfo,
    AgentRequest,
    agent_cancel,
    agent_error,
    agent_start,
    agent_thinking,
)
from runtime.protocol.agent_codec import (
    iter_json_body_events,
    iter_ndjson_events,
    iter_sse_events,
    parse_event,
    parse_sse_data_line,
    request_to_http_body,
)

# How long to wait for the HTTP worker after we stop consuming events.
# Closing the socket should unblock readline almost immediately.
_WORKER_JOIN_TIMEOUT_S = 2.0


def _expand_secret(value: str | None) -> str | None:
    """Expand ${ENV} placeholders in tokens."""
    if not value:
        return value
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _close_response(resp: Any) -> None:
    """Force-close urllib response so a blocked readline() wakes up."""
    if resp is None:
        return
    try:
        resp.close()
    except Exception:  # noqa: BLE001
        pass
    fp = getattr(resp, "fp", None)
    raw = getattr(fp, "raw", None) if fp is not None else None
    sock = getattr(raw, "_sock", None) if raw is not None else None
    if sock is not None:
        try:
            sock.shutdown(2)  # socket.SHUT_RDWR
        except Exception:  # noqa: BLE001
            pass
        try:
            sock.close()
        except Exception:  # noqa: BLE001
            pass


class HTTPAgent(AgentAdapter):
    """
    Modes:
      - stream: prefer NDJSON / SSE streaming (public protocol default)
      - events: batch JSON {events:[...]} or NDJSON buffer
      - text:   {text|reply|content}
      - auto:   detect from Content-Type / body shape
    """

    def __init__(
        self,
        url: str,
        agent_id: str = "http",
        *,
        name: str = "HTTP Agent",
        capabilities: list[str] | None = None,
        mode: str = "auto",
        headers: dict[str, str] | None = None,
        auth_token: str | None = None,
        timeout: float = 120,
        cancel_url: str | None = None,
        description: str | None = None,
    ) -> None:
        self.url = url
        self._id = agent_id
        self._name = name
        self._capabilities = capabilities or ["http"]
        self.mode = mode
        self.headers = dict(headers or {})
        token = _expand_secret(auth_token)
        if token and "Authorization" not in self.headers:
            self.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout
        self.cancel_url = cancel_url
        self._description = description or f"HTTP Agent Protocol → {url}"

    @property
    def info(self) -> AgentInfo:
        return AgentInfo(
            id=self._id,
            name=self._name,
            capabilities=list(self._capabilities),
            description=self._description,
        )

    async def run(self, request: AgentRequest) -> AgentEventStream:
        sid = request.session_id
        yield agent_start(sid)
        yield agent_thinking(sid, f"calling {self.url}")

        cancel = request.cancel_event
        if cancel and cancel.is_set():
            yield agent_cancel(sid, "cancelled before HTTP call")
            return

        prefer_stream = self.mode in ("stream", "auto")
        try:
            async for event in self._run_http(request, prefer_stream=prefer_stream):
                if cancel and cancel.is_set():
                    self._best_effort_cancel(sid)
                    yield agent_cancel(sid)
                    return
                yield event
                if event.type in (
                    AgentEventType.DONE,
                    AgentEventType.CANCEL,
                    AgentEventType.ERROR,
                ):
                    return
        except asyncio.CancelledError:
            self._best_effort_cancel(sid)
            raise
        except Exception as exc:  # noqa: BLE001
            yield agent_error(sid, str(exc))

    async def _run_http(
        self,
        request: AgentRequest,
        *,
        prefer_stream: bool,
    ) -> AgentEventStream:
        """Stream agent events; always release the HTTP socket when the consumer stops.

        Previously ``finally: await task`` could block the event loop forever while the
        worker sat in ``readline()`` (sidecar still running after a terminal event or
        mid-LLM-call). That left the device ``busy`` and made admin cancel hang.
        """
        sid = request.session_id
        queue: asyncio.Queue[Any] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop = threading.Event()
        resp_holder: list[Any] = []

        def worker() -> None:
            try:
                for item in self._fetch_stream(
                    request,
                    prefer_stream=prefer_stream,
                    stop=stop,
                    resp_holder=resp_holder,
                ):
                    if stop.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, ("event", item))
                loop.call_soon_threadsafe(queue.put_nowait, ("end", None))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "end":
                    break
                if kind == "error":
                    raise payload
                yield payload
                if getattr(payload, "type", None) in (
                    AgentEventType.DONE,
                    AgentEventType.CANCEL,
                    AgentEventType.ERROR,
                ):
                    break
        finally:
            stop.set()
            if resp_holder:
                _close_response(resp_holder[0])
            try:
                await asyncio.wait_for(task, timeout=_WORKER_JOIN_TIMEOUT_S)
            except asyncio.TimeoutError:
                if resp_holder:
                    _close_response(resp_holder[0])
                # Thread may outlive us briefly; do not block the event loop.
            except asyncio.CancelledError:
                if resp_holder:
                    _close_response(resp_holder[0])
                raise

    def _build_headers(self, *, accept: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": accept,
            "X-AgentDock-Protocol": PROTOCOL_VERSION,
            **self.headers,
        }
        return headers

    def _fetch_stream(
        self,
        request: AgentRequest,
        *,
        prefer_stream: bool,
        stop: threading.Event | None = None,
        resp_holder: list[Any] | None = None,
    ) -> Iterator[Any]:
        body = json.dumps(request_to_http_body(request, stream=prefer_stream)).encode()
        accept = (
            "application/x-ndjson, text/event-stream, application/json"
            if prefer_stream
            else "application/json, application/x-ndjson"
        )
        req = Request(
            self.url,
            data=body,
            headers=self._build_headers(accept=accept),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc

        if resp_holder is not None:
            resp_holder.append(resp)
        try:
            if stop is not None and stop.is_set():
                return
            ctype = (resp.headers.get("Content-Type") or "").lower()
            sid = request.session_id

            if "text/event-stream" in ctype:
                yield from self._read_sse_live(sid, resp, stop=stop)
                return
            if "ndjson" in ctype or "x-ndjson" in ctype:
                yield from self._read_ndjson_live(sid, resp, stop=stop)
                return

            # Buffered JSON / text / unknown — read all then decode
            raw = resp.read().decode("utf-8", errors="replace")
            if self.mode == "stream" and raw.lstrip().startswith("{"):
                # might still be NDJSON without proper content-type
                if "\n" in raw.strip() and '"type"' in raw:
                    yield from iter_ndjson_events(sid, raw)
                    return

            if "json" in ctype or raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    if "\n" in raw.strip():
                        yield from iter_ndjson_events(sid, raw)
                        return
                    yield from iter_json_body_events(sid, raw)
                    return
                yield from iter_json_body_events(sid, data)
                return

            if "\n" in raw.strip() and raw.lstrip().startswith("{"):
                yield from iter_ndjson_events(sid, raw)
                return

            # SSE without content-type
            if raw.lstrip().startswith("data:"):
                yield from iter_sse_events(sid, raw)
                return

            yield from iter_json_body_events(sid, raw)
        finally:
            _close_response(resp)

    def _read_ndjson_live(
        self,
        session_id: str,
        resp: Any,
        *,
        stop: threading.Event | None = None,
    ) -> Iterator[Any]:
        saw_terminal = False
        while True:
            if stop is not None and stop.is_set():
                break
            line = resp.readline()
            if not line:
                break
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            ev = parse_event(session_id, item)
            if ev:
                yield ev
                if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                    saw_terminal = True
                    return
        if not saw_terminal:
            from runtime.protocol.agent import agent_done

            yield agent_done(session_id)

    def _read_sse_live(
        self,
        session_id: str,
        resp: Any,
        *,
        stop: threading.Event | None = None,
    ) -> Iterator[Any]:
        saw_terminal = False
        data_lines: list[str] = []
        while True:
            if stop is not None and stop.is_set():
                break
            line = resp.readline()
            if not line:
                break
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.rstrip("\r\n")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
                continue
            if line == "":
                if not data_lines:
                    continue
                blob = "\n".join(data_lines)
                data_lines = []
                ev = parse_sse_data_line(session_id, blob)
                if ev:
                    yield ev
                    if ev.type in (
                        AgentEventType.DONE,
                        AgentEventType.CANCEL,
                        AgentEventType.ERROR,
                    ):
                        saw_terminal = True
                        return
                continue
        if data_lines:
            ev = parse_sse_data_line(session_id, "\n".join(data_lines))
            if ev:
                yield ev
                if ev.type in (AgentEventType.DONE, AgentEventType.CANCEL, AgentEventType.ERROR):
                    saw_terminal = True
        if not saw_terminal:
            from runtime.protocol.agent import agent_done

            yield agent_done(session_id)

    def _best_effort_cancel(self, session_id: str) -> None:
        if not self.cancel_url:
            return
        body = json.dumps(
            {"protocol": PROTOCOL_VERSION, "session_id": session_id}
        ).encode()
        req = Request(
            self.cancel_url,
            data=body,
            headers=self._build_headers(accept="application/json"),
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=min(5.0, self.timeout)).read()
        except Exception:  # noqa: BLE001
            pass
