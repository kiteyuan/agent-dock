"""OLED / console display."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from loguru import logger

from device.state import DeviceState

_FONT_EN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_CN_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]

# Short chrome on the fixed status row only (Chinese labels).
# Longer debug info (ws URL, session id, retry …) goes to the body area.
_STATUS_HINTS = frozenset(
    {
        "待命",
        "请说",
        "执行",
        "再点结束",
        "空录音",
        "已取消",
        "在线",
        "连接中",
        "连接失败",
    }
)


class Display:
    def show(self, state: DeviceState, line: str | None = None) -> None:
        raise NotImplementedError


class ConsoleDisplay(Display):
    def show(self, state: DeviceState, line: str | None = None) -> None:
        extra = f" | {line}" if line is not None else ""
        print(f"[OLED] {state.value}{extra}")


def _font_has_cjk(font, sample: str = "待命") -> bool:
    try:
        mask = font.getmask(sample)
        return bool(getattr(mask, "size", (0, 0))[0] and mask.size[1])
    except Exception:
        return False


def _load_truetype(ImageFont, path: str, size: int):
    p = Path(path)
    if not p.is_file():
        return None
    suffix = p.suffix.lower()
    indices = range(0, 8) if suffix in {".ttc", ".otc"} else (0,)
    for idx in indices:
        try:
            font = ImageFont.truetype(str(p), size=size, index=idx)
        except OSError:
            break
        except Exception:
            continue
        if _font_has_cjk(font):
            return font, f"{p}#{idx}" if suffix in {".ttc", ".otc"} else str(p)
        if suffix not in {".ttc", ".otc"}:
            return None
    return None


def _discover_cjk_paths(explicit: str | None) -> list[str]:
    out: list[str] = []
    if explicit:
        out.append(explicit)
    out.extend(_FONT_CN_CANDIDATES)
    roots = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
    ]
    keywords = ("noto", "cjk", "wqy", "droid", "uming", "ukai", "sourcehan", "cn", "sc")
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc"}:
                continue
            name = path.name.lower()
            if any(k in name for k in keywords) or "fallback" in name:
                out.append(str(path))
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _sanitize_display_text(text: str) -> str:
    """Strip CR/controls that break OLED layout; collapse whitespace."""
    parts: list[str] = []
    for ch in text or "":
        o = ord(ch)
        if ch in "\r\n\t":
            parts.append(" ")
        elif o < 32 or o == 127:
            continue
        else:
            parts.append(ch)
    return " ".join("".join(parts).split())


def _is_status_hint(line: str) -> bool:
    """True only for short status-row labels. URLs / session ids are body content."""
    s = (line or "").strip()
    if not s:
        return True
    return s in _STATUS_HINTS


class SH1106Display(Display):
    """SH1106 / SSD1306: fixed status row + scrolling body (no brand line)."""

    def __init__(
        self,
        port: int = 1,
        address: int = 0x3C,
        width: int = 128,
        height: int = 64,
        chip: str = "sh1106",
        font: str | None = None,
        font_size: int = 12,
        rotate: int = 0,
        scroll_px: int = 2,
        scroll_interval_s: float = 0.08,
        scroll_pause_s: float = 0.8,
    ) -> None:
        import smbus2
        from PIL import Image, ImageDraw, ImageFont

        self._bus = smbus2.SMBus(port)
        self._addr = address
        self.width = width
        self.height = height
        self.chip = str(chip)
        self._rotate = rotate
        self._Image = Image
        self._ImageDraw = ImageDraw
        self._scroll_px = max(1, int(scroll_px))
        self._scroll_interval_s = max(0.04, float(scroll_interval_s))
        self._scroll_pause_s = max(0.2, float(scroll_pause_s))

        try:
            self._font_en = ImageFont.truetype(_FONT_EN, font_size)
        except Exception:
            self._font_en = ImageFont.load_default()

        small = max(10, font_size - 1)
        loaded = None
        for candidate in _discover_cjk_paths(font):
            loaded = _load_truetype(ImageFont, candidate, font_size)
            if loaded:
                break
        if loaded:
            self._font_cn, label = loaded
            base, _, idx_s = label.partition("#")
            idx = int(idx_s) if idx_s else 0
            try:
                self._font_body = ImageFont.truetype(base, size=small, index=idx)
            except Exception:
                self._font_body = self._font_cn
            logger.info("OLED CJK font: {}", label)
        else:
            self._font_cn = self._font_en
            self._font_body = self._font_en
            logger.warning(
                "OLED: no CJK font found — Chinese will show as tofu. "
                "On Pi: sudo apt install -y fonts-wqy-microhei"
            )

        self._lock = threading.Lock()
        self._state = DeviceState.BOOT
        self._hint = ""
        self._body = ""
        self._scroll_stop = threading.Event()
        self._scroll_thread: threading.Thread | None = None
        self._scroll_offset = 0
        # Leave a compact status band; rest of the panel is for the reply.
        self._status_h = 14
        self._body_top = self._status_h
        self._init()

    def _cmd(self, *vals):
        for v in vals:
            self._bus.write_byte_data(self._addr, 0x00, v)

    def _init(self):
        if str(self.chip).lower() == "sh1106":
            self._cmd(0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40)
            self._cmd(0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40)
            self._cmd(0xA4, 0xA6, 0xAF)
            self._col_low = 0x02
        else:
            self._cmd(0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14)
            self._cmd(0x20, 0x02, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40)
            self._cmd(0xA4, 0xA6, 0xAF)
            self._col_low = 0x00

    def _display(self, img):
        if self._rotate:
            img = img.rotate(self._rotate * 90)
        pages = (self.height + 7) // 8
        fb = bytearray(self.width * pages)
        for y in range(self.height):
            for x in range(self.width):
                if img.getpixel((x, y)):
                    fb[(y // 8) * self.width + x] |= 1 << (y % 8)
        for page in range(pages):
            self._cmd(0xB0 + page)
            self._cmd(self._col_low, 0x10)
            chunk = fb[page * self.width : (page + 1) * self.width]
            for i in range(0, self.width, 32):
                self._bus.write_i2c_block_data(self._addr, 0x40, list(chunk[i : i + 32]))

    def _stop_scroll_locked(self) -> None:
        self._scroll_stop.set()
        self._scroll_thread = None

    def _scroll_alive_locked(self) -> bool:
        t = self._scroll_thread
        return t is not None and t.is_alive()

    def _line_height(self, font) -> int:
        try:
            ascent, descent = font.getmetrics()
            return int(ascent + descent + 2)
        except Exception:
            return 14

    def _text_width(self, draw, text: str, font) -> float:
        """Prefer ink bounds — textlength under-reports some CJK faces and clips the right edge."""
        if not text:
            return 0.0
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return float(bbox[2] - bbox[0])
        except Exception:
            try:
                return float(draw.textlength(text, font=font))
            except Exception:
                return float(len(text) * 12)

    def _wrap_lines(self, draw, text: str, font, max_width: int) -> list[str]:
        """Wrap by pixel width (CJK-safe). Control chars already sanitized."""
        text = _sanitize_display_text(text)
        if not text:
            return []
        # Keep a real margin: SH1106 + CJK often draw wider than metrics claim.
        max_w = max(8, int(max_width) - 10)
        lines: list[str] = []
        cur = ""
        for ch in text:
            trial = cur + ch
            if self._text_width(draw, trial, font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                if self._text_width(draw, ch, font) > max_w:
                    lines.append(ch)
                    cur = ""
                else:
                    cur = ch
        if cur:
            lines.append(cur)
        return lines

    def _visible_body_rows(self) -> int:
        lh = self._line_height(self._font_body)
        avail = self.height - self._body_top
        return max(1, avail // max(1, lh))

    def _paint_locked(self, line_offset: int | None = None) -> None:
        if line_offset is None:
            line_offset = self._scroll_offset
        img = self._Image.new("1", (self.width, self.height))
        draw = self._ImageDraw.Draw(img)

        # Fixed status row: ASCII state in EN font, Chinese hint in CJK font.
        x = 0
        state_s = f"* {self._state.value}"
        draw.text((x, 0), state_s, font=self._font_en, fill=255)
        x += int(draw.textlength(state_s, font=self._font_en))
        if self._hint:
            gap = " "
            draw.text((x, 0), gap, font=self._font_body, fill=255)
            x += int(self._text_width(draw, gap, self._font_body))
            room = self.width - 6 - x
            hint = _sanitize_display_text(self._hint)
            while hint and self._text_width(draw, hint, self._font_body) > room:
                hint = hint[:-1]
            if hint:
                draw.text((x, 0), hint, font=self._font_body, fill=255)

        body = _sanitize_display_text(self._body or "")
        if body:
            lines = self._wrap_lines(draw, body, self._font_body, self.width - 2)
            lh = self._line_height(self._font_body)
            rows = self._visible_body_rows()
            max_off = max(0, len(lines) - rows)
            line_offset = max(0, min(int(line_offset), max_off))
            self._scroll_offset = line_offset
            window = lines[line_offset : line_offset + rows]
            y = self._body_top
            for row in window:
                draw.text((1, y), row, font=self._font_body, fill=255)
                y += lh

        self._display(img)

    def _ensure_scroll_locked(self) -> None:
        """Start vertical scroll if body overflows; do not restart if already running."""
        if self._scroll_alive_locked():
            return
        body = _sanitize_display_text(self._body or "")
        if not body:
            return
        img = self._Image.new("1", (1, 1))
        draw = self._ImageDraw.Draw(img)
        lines = self._wrap_lines(draw, body, self._font_body, self.width - 2)
        if len(lines) <= self._visible_body_rows():
            self._scroll_offset = 0
            self._paint_locked(0)
            return
        self._start_scroll_locked()

    def _start_scroll_locked(self) -> None:
        self._scroll_stop.clear()
        start_off = self._scroll_offset

        def _run() -> None:
            off = start_off
            while not self._scroll_stop.is_set():
                with self._lock:
                    body = _sanitize_display_text(self._body or "")
                    if not body:
                        return
                    img = self._Image.new("1", (1, 1))
                    draw = self._ImageDraw.Draw(img)
                    lines = self._wrap_lines(draw, body, self._font_body, self.width - 2)
                    rows = self._visible_body_rows()
                    if len(lines) <= rows:
                        self._scroll_offset = 0
                        self._paint_locked(0)
                        return
                    max_off = len(lines) - rows
                    if off > max_off:
                        off = 0
                    self._scroll_offset = off
                    self._paint_locked(off)
                # Hold at top briefly when looping back
                pause = self._scroll_pause_s if off == 0 else max(0.45, self._scroll_interval_s * 5)
                if self._scroll_stop.wait(pause):
                    return
                off += 1
                if off > max_off:
                    # Pause on last page, then loop
                    if self._scroll_stop.wait(self._scroll_pause_s):
                        return
                    off = 0

        self._scroll_thread = threading.Thread(target=_run, name="oled-scroll", daemon=True)
        self._scroll_thread.start()

    def show(self, state: DeviceState, line: str | None = None) -> None:
        """Update OLED.

        - Status row is always `* STATE` (+ optional short hint, CJK font).
        - `line=None` / `待命`: only refresh status — keep reply + scroll position.
        - `请说` / new listen: clear body for the new turn.
        - New agent text: replace body and restart scroll from top.
        """
        with self._lock:
            self._state = state

            # State-only update (TTS start/end, ONLINE, …): never reset scroll.
            if line is None:
                self._paint_locked(self._scroll_offset)
                self._ensure_scroll_locked()
                return

            text = _sanitize_display_text(str(line))
            if _is_status_hint(text):
                self._hint = text
                if text in {"请说", "再点结束", "空录音"}:
                    self._stop_scroll_locked()
                    self._body = ""
                    self._scroll_offset = 0
                    self._paint_locked(0)
                    return
                # 待命 / connect crumbs: keep body, keep scroll offset
                self._paint_locked(self._scroll_offset)
                self._ensure_scroll_locked()
                return

            # New reply text — only reset scroll if content actually changed
            if text == _sanitize_display_text(self._body or ""):
                self._hint = ""
                self._paint_locked(self._scroll_offset)
                self._ensure_scroll_locked()
                return

            self._stop_scroll_locked()
            self._hint = ""
            self._body = text
            self._scroll_offset = 0
            self._paint_locked(0)
            self._ensure_scroll_locked()


def build_display(cfg: dict) -> Display:
    if not cfg.get("enabled", True):
        return ConsoleDisplay()
    driver = cfg.get("driver", "console")
    if driver in ("ssd1306", "sh1106", "oled"):
        try:
            chip = "sh1106" if driver in ("sh1106", "oled") else "ssd1306"
            return SH1106Display(
                port=int(cfg.get("i2c_port", 1)),
                address=int(cfg.get("i2c_address", 0x3C)),
                width=int(cfg.get("width", 128)),
                height=int(cfg.get("height", 64)),
                chip=str(cfg.get("chip", chip)),
                font=cfg.get("font"),
                font_size=int(cfg.get("font_size", 12)),
                rotate=int(cfg.get("rotate", 0)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OLED init failed ({}), fallback console", exc)
    return ConsoleDisplay()
