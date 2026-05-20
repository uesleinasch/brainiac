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
