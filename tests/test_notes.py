"""Notes indexer (wikilinks) and Graph View → notes migration."""

from __future__ import annotations

from pathlib import Path

from runtime.layout_migrate import migrate_notes_dir
from runtime.notes.indexer import NotesIndexer, _extract_wikilinks, _resolve_link
from runtime.paths import NOTES_DIR_NAME, LEGACY_NOTES_DIR_NAME, resolve_notes


def test_extract_wikilinks() -> None:
    text = "See [[Alpha]] and [[Beta|别名]] plus [[https://x.com]] and [[Hub#section]]."
    assert _extract_wikilinks(text) == ["Alpha", "Beta", "Hub"]


def test_resolve_link_by_basename() -> None:
    by_name = {"alpha": "private/Alpha", "private/alpha": "private/Alpha"}
    assert _resolve_link("Alpha", "public/Other", by_name) == "private/Alpha"
    assert _resolve_link("missing", "public/Other", by_name) == "missing"


def test_indexer_builds_graph_and_placeholders(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.md").write_text("# 甲\n\nLink to [[b]] and [[Ghost]].\n", encoding="utf-8")
    (notes / "b.md").write_text("# 乙\n\nBack to [[a]].\n", encoding="utf-8")
    (notes / ".obsidian").mkdir()
    (notes / ".obsidian" / "skip.md").write_text("[[a]]", encoding="utf-8")

    graph = NotesIndexer(notes).graph()
    ids = {n["id"] for n in graph["nodes"]}
    assert "a" in ids and "b" in ids
    assert next(n for n in graph["nodes"] if n["id"] == "a")["title"] == "a"
    assert next(n for n in graph["nodes"] if n["id"] == "b")["title"] == "b"
    assert "Ghost" in ids
    ghost = next(n for n in graph["nodes"] if n["id"] == "Ghost")
    assert ghost["exists"] is False
    assert ghost["title"] == "Ghost"
    assert graph["stats"]["notes"] == 2
    assert graph["stats"]["placeholders"] == 1
    assert graph["stats"]["links"] >= 2
    assert any(e["source"] == "a" and e["target"] == "b" for e in graph["edges"])

    doc_a = NotesIndexer(notes).doc("a")
    assert doc_a["ok"] is True
    assert doc_a["exists"] is True
    assert "Link to [[b]]" in doc_a["content"]
    assert NotesIndexer(notes).doc("Ghost")["exists"] is False
    assert NotesIndexer(notes).doc("../escape")["ok"] is False


def test_migrate_graph_view_to_notes(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    vault = home / "vault"
    legacy = vault / LEGACY_NOTES_DIR_NAME
    legacy.mkdir(parents=True)
    (legacy / "hello.md").write_text("# hi\n", encoding="utf-8")
    monkeypatch.setenv("AGENTDOCK_HOME", str(home))

    actions = migrate_notes_dir({})
    notes = resolve_notes({})
    assert notes.name == NOTES_DIR_NAME
    assert notes.is_dir()
    assert (notes / "hello.md").is_file()
    assert not legacy.exists()
    assert any("notes:" in a for a in actions)

    # Idempotent
    actions2 = migrate_notes_dir({})
    assert actions2 == []
    assert notes.is_dir()


def test_migrate_notes_conflict_keeps_both(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    vault = home / "vault"
    (vault / LEGACY_NOTES_DIR_NAME).mkdir(parents=True)
    (vault / NOTES_DIR_NAME).mkdir(parents=True)
    (vault / LEGACY_NOTES_DIR_NAME / "old.md").write_text("x", encoding="utf-8")
    (vault / NOTES_DIR_NAME / "new.md").write_text("y", encoding="utf-8")
    monkeypatch.setenv("AGENTDOCK_HOME", str(home))

    actions = migrate_notes_dir({})
    assert actions == []
    assert (vault / LEGACY_NOTES_DIR_NAME / "old.md").is_file()
    assert (vault / NOTES_DIR_NAME / "new.md").is_file()
