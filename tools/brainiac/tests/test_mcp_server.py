from pathlib import Path

import pytest

from brainiac.core.note import parse_note, write_note
from brainiac.mcp_server import (
    tool_add_note,
    tool_get_note,
    tool_link,
    tool_list_recent,
    tool_recall,
)
from tests.conftest import make_fm


class TestToolAddNote:
    def test_creates_note_and_indexes(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = tool_add_note(
            note_id="2026-05-20-new",
            note_type="semantic",
            title="Pizza",
            body="# Pizza\n\nItalian food",
            tags=["food"],
        )
        assert result["id"] == "2026-05-20-new"
        assert (fake_brainiac / "semanticMemory" / "2026-05-20-new.md").exists()


class TestToolRecall:
    def test_finds_notes(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(
            note_id="2026-05-20-a", note_type="semantic",
            title="x", body="# Pizza\n\nfood", tags=[],
        )
        results = tool_recall("pizza", k=5)
        assert any(r["id"] == "2026-05-20-a" for r in results)


class TestToolGetNote:
    def test_returns_body_and_increments(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(
            note_id="2026-05-20-a", note_type="semantic",
            title="x", body="# A\n\ncorpo", tags=[],
        )
        result = tool_get_note("2026-05-20-a")
        assert "corpo" in result["body"]
        assert result["frontmatter"]["access_count"] == 1


class TestToolLink:
    def test_creates_link(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(note_id="2026-05-20-a", note_type="semantic", title="A", body="# A", tags=[])
        tool_add_note(note_id="2026-05-20-b", note_type="semantic", title="B", body="# B", tags=[])
        tool_link("2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md")
        assert "2026-05-20-b" in fm_a.links


class TestToolListRecent:
    def test_returns_recent(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(note_id="2026-05-20-a", note_type="semantic", title="A", body="# A", tags=[])
        results = tool_list_recent(limit=10)
        assert len(results) == 1
        assert results[0]["id"] == "2026-05-20-a"


def test_tool_recall_returns_origin_badge(fake_brainiac, embedder_stub, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))

    from brainiac.mcp_server import tool_add_note, tool_recall

    tool_add_note(
        note_id="2026-05-20-recall-mcp",
        note_type="semantic",
        title="DKG protocol",
        body="distributed key generation",
        tags=["crypto"],
    )
    results = tool_recall(query="DKG", k=3)
    assert len(results) >= 1
    assert all("origin" in r for r in results)


from datetime import datetime, timedelta, timezone


def test_tool_forget_archives_note(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_forget

    tool_add_note(
        note_id="2026-05-20-forget-me",
        note_type="semantic",
        title="Forget Me",
        body="# Forget Me\n\nconteúdo temporário",
    )
    result = tool_forget("2026-05-20-forget-me")

    assert result["id"] == "2026-05-20-forget-me"
    assert result["action"] == "archived"
    assert "archived_path" in result
    archived = fake_brainiac / "memoryTransfer" / "archive"
    assert any(archived.rglob("2026-05-20-forget-me.md"))


def test_tool_forget_unknown_note_returns_error(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_forget

    with pytest.raises(KeyError):
        tool_forget("2026-05-20-ghost")


def test_tool_consolidate_check_returns_candidates(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.mcp_server import tool_consolidate_check

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    fm = make_fm("2026-05-18-cand", note_type="working",
                 access_count=5, last_access=recent)
    p = note_path(fake_brainiac, "2026-05-18-cand", "working")
    write_note(p, fm, "# cand\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    rel = str(p.relative_to(fake_brainiac))
    index_note(conn, fm, "# cand\n\nbody", rel)
    conn.execute(
        "INSERT OR IGNORE INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-15-other", "2026-05-18-cand"),
    )
    conn.commit()

    candidates = tool_consolidate_check(window_days=7)
    assert any(c["id"] == "2026-05-18-cand" for c in candidates)
