"""Human-readable turn rendering for Device clients (collapse thinking spam)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


PrintFn = Callable[[str], None]


@dataclass
class TurnView:
    """
    Fold agent/stt/tts wire events into short console / OLED lines.

    thinking tokens are merged and throttled (not one print per token).
    """

    print: PrintFn = field(default=lambda s: print(s, flush=True))
    thinking_min_interval: float = 0.4
    thinking_max_len: int = 56
    oled_width: int = 21

    _thinking_buf: str = field(default="", init=False, repr=False)
    _last_thinking_flush: float = field(default=0.0, init=False, repr=False)
    _thinking_printed: bool = field(default=False, init=False, repr=False)
    last_oled_line: str = field(default="", init=False)
    last_user_text: str | None = field(default=None, init=False)
    last_assistant_text: str | None = field(default=None, init=False)

    def reset_turn(self) -> None:
        self._emit_thinking(final=True)
        self._thinking_buf = ""
        self._thinking_printed = False
        self.last_user_text = None
        self.last_assistant_text = None

    def handle(self, mtype: str, payload: dict[str, Any] | None = None) -> str | None:
        """Process one event; return a short OLED-friendly line if UI should update."""
        payload = payload or {}
        if mtype == "device.pong":
            return None

        if mtype == "stt.final":
            self._emit_thinking(final=True)
            text = (payload.get("text") or "").strip()
            self.last_user_text = text
            return None

        if mtype == "agent.thinking":
            chunk = payload.get("content") or payload.get("text") or ""
            if not chunk:
                return None
            self._thinking_buf += str(chunk)
            now = time.monotonic()
            if self._last_thinking_flush <= 0:
                self._last_thinking_flush = now
            elif (now - self._last_thinking_flush) >= self.thinking_min_interval:
                self._emit_thinking(final=False)
            shown = self._thinking_buf.strip()
            # Console stays compact; OLED gets full text and scrolls itself.
            self.last_oled_line = shown
            return shown

        if mtype in ("agent.tool_call", "agent.tool_result"):
            self._emit_thinking(final=True)
            line = _native_line(mtype, payload)
            if not line:
                return None
            self.print(line)
            self.last_oled_line = line
            return line

        if mtype == "agent.message":
            self._emit_thinking(final=True)
            text = (payload.get("content") or payload.get("text") or "").strip()
            self.last_assistant_text = text
            if not text:
                return None
            self.print(text)
            self.last_oled_line = text
            return text

        if mtype == "agent.start":
            self._emit_thinking(final=True)
            return None

        if mtype == "tts.start":
            self._emit_thinking(final=True)
            tid = payload.get("tts_id") or ""
            self.print(f"播放中… ({tid})" if tid else "播放中…")
            # Do not replace OLED body with "播放中"
            return None

        if mtype == "tts.end":
            self.print("播放结束")
            return None

        if mtype in ("agent.error", "error"):
            self._emit_thinking(final=True)
            detail = payload.get("content") or payload.get("detail") or payload.get("text") or "error"
            self.print(f"错误：{detail}")
            line = f"错误:{detail}"
            self.last_oled_line = line
            return line

        if mtype == "agent.cancel":
            self._emit_thinking(final=True)
            self.print("已取消")
            self.last_oled_line = "已取消"
            return self.last_oled_line

        if mtype == "agent.done":
            self._emit_thinking(final=True)
            return None

        return None

    def _emit_thinking(self, *, final: bool) -> None:
        shown = self._thinking_buf.strip()
        if not shown:
            if final:
                self._thinking_buf = ""
                self._thinking_printed = False
            return
        if len(shown) > self.thinking_max_len:
            shown = "…" + shown[-(self.thinking_max_len - 1) :]
        # Only print when we have new content; final emits once more if never printed
        if not final and shown:
            self.print(shown)
            self._thinking_printed = True
            self._last_thinking_flush = time.monotonic()
        elif final and shown and not self._thinking_printed:
            self.print(shown)
            self._thinking_printed = True
        if final:
            self._thinking_buf = ""
            self._thinking_printed = False
            self._last_thinking_flush = time.monotonic()


def _native_line(mtype: str, payload: dict[str, Any]) -> str:
    """Agent payload as-is. No invented prefixes."""
    content = str(payload.get("content") or payload.get("text") or "").strip()
    if content:
        return content
    if mtype == "agent.tool_call":
        tool = str(payload.get("tool") or "").strip()
        args = payload.get("args")
        if isinstance(args, dict) and args:
            dumped = str(args)
            return f"{tool} {dumped}".strip() if tool else dumped
        return tool
    return ""
