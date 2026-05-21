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


def test_tool_add_note_with_study_enrolls_sm2(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note
    from brainiac.core.note import parse_note

    tool_add_note(
        note_id="2026-05-20-study",
        note_type="semantic",
        title="Studyable",
        body="# Studyable\n\nfact",
        study=True,
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-study.md")
    assert fm.sm2 is not None
    assert fm.sm2.reps == 0
    assert fm.sm2.interval == 1


def test_tool_start_review_enrolls_existing_note(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_start_review

    tool_add_note(
        note_id="2026-05-20-existing",
        note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    result = tool_start_review("2026-05-20-existing")
    assert result["id"] == "2026-05-20-existing"
    assert result["next_review"]  # ISO string
    assert result["reps"] == 0
    assert result["ease"] == 2.5  # SM-2 initial ease
    assert result["interval"] == 1  # SM-2 initial interval


def test_tool_review_queue_returns_due_notes(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_review_queue

    tool_add_note(
        note_id="2026-05-20-q1",
        note_type="semantic",
        title="x", body="# x\n\nbody",
        study=True,
    )
    queue = tool_review_queue()
    assert len(queue) >= 1
    assert any(item["id"] == "2026-05-20-q1" for item in queue)


def test_tool_grade_review_updates_state(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_grade_review

    tool_add_note(
        note_id="2026-05-20-g",
        note_type="semantic",
        title="x", body="# x\n\nbody",
        study=True,
    )
    result = tool_grade_review("2026-05-20-g", grade=5)
    assert result["id"] == "2026-05-20-g"
    assert result["reps"] == 1
    assert result["interval"] == 1  # first successful rep: interval stays at 1
    assert result["ease"] > 2.5  # grade=5 raises ease (2.5 → 2.6)
    assert "next_review" in result


def test_tool_add_note_rejects_working_when_full(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-w-a", note_type="working",
        title="A", body="# A\n\nx",
    )
    tool_add_note(
        note_id="2026-05-20-w-b", note_type="working",
        title="B", body="# B\n\ny",
    )
    result = tool_add_note(
        note_id="2026-05-20-w-c", note_type="working",
        title="C", body="# C\n\nz",
    )
    assert "error" in result
    assert result["count"] == 2
    assert result["limit"] == 2
    assert isinstance(result["suggestion"], list)
    assert len(result["suggestion"]) >= 1
    # file should NOT be created
    assert not (fake_brainiac / "shortMemory" / "2026-05-20-w-c.md").exists()


def test_tool_add_note_allows_semantic_at_working_limit(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 1\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-w-fill", note_type="working",
        title="W", body="# W\n\nbody",
    )
    # semantic note should still go through
    result = tool_add_note(
        note_id="2026-05-20-s-ok", note_type="semantic",
        title="S", body="# S\n\nbody",
    )
    assert "error" not in result
    assert result["type"] == "semantic"


def test_tool_working_status_reports_empty_brainiac(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_working_status

    status = tool_working_status()
    assert status["count"] == 0
    assert status["limit"] == 9  # default
    assert status["full"] is False
    assert status["candidates"] == []


def test_tool_working_status_reports_full_with_candidates(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note, tool_working_status

    tool_add_note(note_id="2026-05-20-ws-a", note_type="working", title="A", body="# A")
    tool_add_note(note_id="2026-05-20-ws-b", note_type="working", title="B", body="# B")

    status = tool_working_status()
    assert status["count"] == 2
    assert status["limit"] == 2
    assert status["full"] is True
    assert len(status["candidates"]) == 2


def test_tool_inspect_note_returns_all_three_axes(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_inspect_note

    tool_add_note(
        note_id="2026-05-20-insp", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    result = tool_inspect_note("2026-05-20-insp")
    assert result["id"] == "2026-05-20-insp"
    assert "activation" in result
    assert "strength" in result
    assert "sm2" in result
    assert "recent_accesses" in result


def test_tool_inspect_note_includes_recent_accesses(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_get_note, tool_inspect_note

    tool_add_note(
        note_id="2026-05-20-h2", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    tool_get_note("2026-05-20-h2")  # records 'get'
    result = tool_inspect_note("2026-05-20-h2")
    assert len(result["recent_accesses"]) >= 1
    sources = {a["source"] for a in result["recent_accesses"]}
    assert "get" in sources


def test_tool_inspect_note_raises_for_unknown_note(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_inspect_note

    with pytest.raises(KeyError):
        tool_inspect_note("2026-05-20-ghost-insp")


def test_tool_add_note_accepts_emotional_weight(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.note import parse_note
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-ew-mcp", note_type="semantic",
        title="x", body="# x\n\nbody",
        emotional_weight=0.85,
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-ew-mcp.md")
    assert fm.emotional_weight == 0.85


def test_tool_add_note_emotional_weight_defaults_to_0_5(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.note import parse_note
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-ew-def", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-ew-def.md")
    assert fm.emotional_weight == 0.5
