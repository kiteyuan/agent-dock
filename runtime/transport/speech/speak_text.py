"""Normalize assistant text before TTS so markdown / symbols are not spoken."""

from __future__ import annotations

import re

# Common emoji / pictographs (broad BMP + supplemental ranges used in chat replies)
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001f9ff\U0001fa00-\U0001faff\U00002600-\U000027bf\U0001f1e0-\U0001f1ff]+",
    flags=re.UNICODE,
)

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_ITALIC_RE = re.compile(r"(\*\*|__)(.*?)\1")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\s*\d+[.)、]\s+", re.MULTILINE)
_MULTI_NL_RE = re.compile(r"\n{2,}")
_STRIP_CHARS_RE = re.compile(r"[#*_~>`|{}\[\]<>]")
# Quotation / book-title marks — keep inner text, drop the marks (TTS often voices them)
_QUOTE_CHARS_RE = re.compile(r"[「」『』【】《》〈〉“”‘’\"']")
_SPACES_RE = re.compile(r"[ \t]{2,}")
# Sentence ends for streaming TTS
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")
# Must contain at least one letter / digit / CJK (skip bare "。" etc.)
_SPEAKABLE_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def is_speakable(text: str) -> bool:
    """True if text has something GPT-SoVITS / Edge can actually voice."""
    return bool(text and _SPEAKABLE_RE.search(text))


def speak_text(text: str) -> str:
    """
    Convert reply text into something suitable for TTS.
    Strips markdown / emoji / bullets; keeps CJK, Latin, digits, and punctuation
    for multilingual voices.
    """
    if not text:
        return ""

    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = _CODE_FENCE_RE.sub(lambda m: "。", s)
    s = _MD_IMAGE_RE.sub(r"\1", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _INLINE_CODE_RE.sub(r"\1", s)
    s = _BOLD_ITALIC_RE.sub(r"\2", s)
    s = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", s)
    s = _HEADING_RE.sub("", s)
    s = _BULLET_RE.sub("", s)
    s = _NUMBERED_RE.sub("", s)
    s = _EMOJI_RE.sub("", s)
    s = re.sub(r"[\uFE0E\uFE0F\u200D]", "", s)  # emoji variation / ZWJ leftovers
    s = re.sub(r"（\s*）", "", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = _QUOTE_CHARS_RE.sub("", s)
    s = _MULTI_NL_RE.sub("。", s)
    s = s.replace("\n", "。")
    # Keep Windows paths readable for TTS (do not drop backslashes).
    s = s.replace("\\", "/")
    s = _STRIP_CHARS_RE.sub("", s)
    # Normalize odd punctuation clusters
    s = re.sub(r"[。！？]{2,}", "。", s)
    s = re.sub(r"[，,]{2,}", "，", s)
    s = _SPACES_RE.sub(" ", s)
    s = re.sub(r"\s*。\s*", "。", s)
    s = re.sub(r"。+", "。", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" 。，,")
    return s.strip()


def take_sentences(buf: str, *, force: bool = False, force_at: int = 56) -> tuple[list[str], str]:
    """
    Pull complete sentences from a speak buffer for streaming TTS.

    Splits on 。！？!?；; and newlines. If force=True, returns any remainder.
    If the buffer grows past force_at without a hard end, soft-splits on
    ，/,/space so synthesis can start before the agent finishes the turn.
    """
    if not buf:
        return [], ""

    out: list[str] = []
    rest = buf
    while True:
        m = re.search(r"[。！？!?；;\n]", rest)
        if m:
            sent = rest[: m.end()].strip()
            rest = rest[m.end() :]
            if is_speakable(sent):
                out.append(sent)
            continue
        break

    rest = rest.lstrip()
    if force:
        leftover = rest.strip()
        if is_speakable(leftover):
            out.append(leftover)
        return out, ""

    if len(rest) >= force_at:
        cut = max(rest.rfind("，"), rest.rfind(","), rest.rfind(" "))
        if cut < force_at // 3:
            cut = force_at
        else:
            cut = cut + 1
        sent = rest[:cut].strip()
        rest = rest[cut:].lstrip()
        if is_speakable(sent):
            out.append(sent)

    return out, rest


class SentenceBuffer:
    """Accumulate sanitized speak text and emit sentence chunks."""

    def __init__(self, *, force_at: int = 56) -> None:
        self._buf = ""
        self.force_at = force_at

    def push(self, text: str) -> list[str]:
        if not text:
            return []
        self._buf += text
        sentences, self._buf = take_sentences(self._buf, force=False, force_at=self.force_at)
        return sentences

    def flush(self) -> list[str]:
        sentences, self._buf = take_sentences(self._buf, force=True, force_at=self.force_at)
        return sentences
