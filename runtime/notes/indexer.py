"""Markdown notes under ``vault/notes`` — wikilink graph for Admin."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# [[target]] or [[target|alias]]; skip http(s) targets
_WIKILINK = re.compile(r"\[\[([^\]]+?)\]\]")


@dataclass
class _Cache:
    signature: tuple[Any, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    built_at: float = 0.0


class NotesIndexer:
    """Scan ``notes/**/*.md`` into a force-graph friendly node/edge payload."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cache = _Cache()

    def graph(self) -> dict[str, Any]:
        sig = self._signature()
        if sig == self._cache.signature and self._cache.payload:
            return self._cache.payload
        payload = self._build()
        self._cache = _Cache(signature=sig, payload=payload, built_at=time.time())
        return payload

    def doc(self, note_id: str) -> dict[str, Any]:
        """Read one note by id (relative path without ``.md``). Path-safe under root."""
        raw = (note_id or "").strip().replace("\\", "/")
        if not raw or any(part in ("", ".", "..") for part in raw.split("/")):
            return {"ok": False, "error": "invalid id", "exists": False, "content": ""}
        if raw.lower().endswith(".md"):
            raw = raw[:-3]
        root = self.root.resolve()
        candidate = (self.root / f"{raw}.md").resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return {"ok": False, "error": "outside notes root", "exists": False, "content": ""}
        title = Path(raw).name
        rel = f"{raw}.md"
        if not candidate.is_file():
            return {
                "ok": True,
                "id": raw,
                "title": title,
                "path": rel,
                "exists": False,
                "content": "",
            }
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "error": str(exc), "exists": False, "content": ""}
        return {
            "ok": True,
            "id": raw,
            "title": candidate.stem,
            "path": candidate.relative_to(root).as_posix(),
            "exists": True,
            "content": text,
        }

    def _signature(self) -> tuple[Any, ...]:
        if not self.root.is_dir():
            return ("missing",)
        latest = 0.0
        count = 0
        try:
            latest = self.root.stat().st_mtime
        except OSError:
            pass
        for path in self._iter_md():
            count += 1
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
        return (str(self.root.resolve()), count, latest)

    def _iter_md(self):
        if not self.root.is_dir():
            return
        for path in self.root.rglob("*.md"):
            try:
                rel_parts = path.relative_to(self.root).parts
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel_parts):
                continue
            if not path.is_file():
                continue
            yield path

    def _build(self) -> dict[str, Any]:
        root = self.root
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str]] = []
        edge_keys: set[tuple[str, str]] = set()
        by_name: dict[str, str] = {}

        files: list[tuple[Path, str, str, str]] = []
        for path in self._iter_md():
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            note_id = rel[:-3] if rel.lower().endswith(".md") else rel
            # Display name is always the file stem (Obsidian-style), not in-doc H1.
            title = path.stem
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            files.append((path, note_id, title, text))
            nodes[note_id] = {
                "id": note_id,
                "title": title,
                "path": rel,
                "exists": True,
            }
            by_name[path.stem.lower()] = note_id
            by_name[note_id.lower()] = note_id

        for _path, note_id, _title, text in files:
            for target_raw in _extract_wikilinks(text):
                target_id = _resolve_link(target_raw, note_id, by_name)
                if target_id not in nodes:
                    nodes[target_id] = {
                        "id": target_id,
                        "title": Path(target_id).name,
                        "path": f"{target_id}.md",
                        "exists": False,
                    }
                key = (note_id, target_id)
                if key in edge_keys or note_id == target_id:
                    continue
                edge_keys.add(key)
                edges.append({"source": note_id, "target": target_id})

        return {
            "ok": True,
            "root": str(root.resolve()),
            "nodes": list(nodes.values()),
            "edges": edges,
            "stats": {
                "notes": sum(1 for n in nodes.values() if n.get("exists")),
                "placeholders": sum(1 for n in nodes.values() if not n.get("exists")),
                "links": len(edges),
            },
        }


def _extract_wikilinks(text: str) -> list[str]:
    out: list[str] = []
    for match in _WIKILINK.finditer(text or ""):
        inner = match.group(1).strip()
        if not inner:
            continue
        target = inner.split("|", 1)[0].strip()
        target = target.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith(("http://", "https://")):
            continue
        out.append(target.replace("\\", "/"))
    return out


def _resolve_link(raw: str, source_id: str, by_name: dict[str, str]) -> str:
    cleaned = raw.strip().replace("\\", "/")
    if cleaned.lower().endswith(".md"):
        cleaned = cleaned[:-3]
    key = cleaned.lower()
    if key in by_name:
        return by_name[key]
    if "/" in source_id:
        parent = "/".join(source_id.split("/")[:-1])
        candidate = f"{parent}/{cleaned}".lower()
        if candidate in by_name:
            return by_name[candidate]
    base = cleaned.split("/")[-1].lower()
    if base in by_name:
        return by_name[base]
    return cleaned
