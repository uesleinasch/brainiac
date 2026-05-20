import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.conftest import make_fm
from brainiac.core.index import add_link, get_note, index_note, reindex_all, search_fts
from brainiac.core.models import NoteFrontmatter
from brainiac.core.note import parse_note, write_note


class TestIndexNote:
    def test_inserts_into_notes(self, conn):
        fm = make_fm(note_id="2026-05-20-a", tags=["x"])
        index_note(conn, fm, "# Título\n\n- bullet", "semanticMemory/2026-05-20-a.md")

        row = conn.execute("SELECT id, path, type, access_count FROM notes WHERE id=?",
                           (fm.id,)).fetchone()
        assert row == ("2026-05-20-a", "semanticMemory/2026-05-20-a.md", "semantic", 0)

    def test_inserts_into_fts(self, conn):
        fm = make_fm(note_id="2026-05-20-b")
        index_note(conn, fm, "# Distributed Key Generation\n\nDKG protocol", "x.md")

        hit = conn.execute(
            "SELECT id FROM notes_fts WHERE notes_fts MATCH 'distributed'"
        ).fetchone()
        assert hit == ("2026-05-20-b",)

    def test_explicit_links_synced(self, conn):
        fm = make_fm(note_id="2026-05-20-c", links=["2026-05-20-other"])
        index_note(conn, fm, "# t", "x.md")

        row = conn.execute(
            "SELECT src, dst, kind FROM links WHERE src=?", (fm.id,)
        ).fetchone()
        assert row == ("2026-05-20-c", "2026-05-20-other", "explicit")

    def test_replace_on_reindex(self, conn):
        fm = make_fm(note_id="2026-05-20-d", links=["a"])
        index_note(conn, fm, "# v1", "x.md")
        fm2 = make_fm(note_id="2026-05-20-d", links=["b"])
        index_note(conn, fm2, "# v2", "x.md")

        # link antigo desapareceu, novo presente
        links = {r[1] for r in conn.execute(
            "SELECT src, dst FROM links WHERE src=?", (fm.id,)
        ).fetchall()}
        assert links == {"b"}

    def test_extracts_title_from_body(self, conn):
        fm = make_fm(note_id="2026-05-20-e")
        index_note(conn, fm, "# Meu Título\n\ncorpo", "x.md")

        title = conn.execute(
            "SELECT title FROM notes_fts WHERE id=?", (fm.id,)
        ).fetchone()
        assert title == ("Meu Título",)


class TestConnect:
    def test_creates_db_file(self, fake_brainiac: Path):
        from brainiac.core.index import connect

        db = fake_brainiac / "memoryTransfer" / "index.sqlite"
        assert not db.exists()
        conn = connect(db)
        assert db.exists()
        conn.close()

    def test_creates_required_tables(self, conn: sqlite3.Connection):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()}
        assert "notes" in names
        assert "notes_fts" in names
        assert "links" in names

    def test_idempotent(self, fake_brainiac: Path):
        from brainiac.core.index import connect

        db = fake_brainiac / "memoryTransfer" / "index.sqlite"
        connect(db).close()
        connect(db).close()  # segundo connect não deve falhar


class TestReindexAll:
    def test_empty_brainiac_returns_zero(self, conn, fake_brainiac):
        active, archived = reindex_all(conn, fake_brainiac)
        assert active == 0
        assert archived == 0

    def test_indexes_notes_in_correct_dirs(self, conn, fake_brainiac):
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a", note_type="semantic"),
            "# A\n",
        )
        write_note(
            fake_brainiac / "shortMemory" / "2026-05-20-b.md",
            make_fm(note_id="2026-05-20-b", note_type="working"),
            "# B\n",
        )
        write_note(
            fake_brainiac / "longMemory" / "episodic" / "2026-05-20-c.md",
            make_fm(note_id="2026-05-20-c", note_type="episodic"),
            "# C\n",
        )

        active, _ = reindex_all(conn, fake_brainiac)
        assert active == 3

        ids = {r[0] for r in conn.execute("SELECT id FROM notes").fetchall()}
        assert ids == {"2026-05-20-a", "2026-05-20-b", "2026-05-20-c"}

    def test_ignores_files_outside_memory_dirs(self, conn, fake_brainiac):
        # nota legítima
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a"),
            "# A\n",
        )
        # arquivo fora de memory dirs — não deve ser indexado
        (fake_brainiac / "docs").mkdir()
        (fake_brainiac / "docs" / "random.md").write_text("# not a note\n")
        (fake_brainiac / "README.md").write_text("# repo readme\n")

        active, _ = reindex_all(conn, fake_brainiac)
        assert active == 1

    def test_skips_invalid_frontmatter_without_crashing(self, conn, fake_brainiac, capsys):
        # nota válida
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-good.md",
            make_fm(note_id="2026-05-20-good"),
            "# good\n",
        )
        # nota com frontmatter quebrado
        (fake_brainiac / "semanticMemory" / "broken.md").write_text(
            "---\nid: invalid format\n---\n# x\n", encoding="utf-8"
        )

        active, _ = reindex_all(conn, fake_brainiac)
        assert active == 1  # só a boa contou
        captured = capsys.readouterr()
        assert "broken.md" in captured.out  # log do skip

    def test_idempotent_wipes_before_rebuild(self, conn, fake_brainiac):
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a"),
            "# A\n",
        )
        reindex_all(conn, fake_brainiac)

        # remove o arquivo e roda de novo
        (fake_brainiac / "semanticMemory" / "2026-05-20-a.md").unlink()
        active, _ = reindex_all(conn, fake_brainiac)
        assert active == 0
        rows = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
        assert rows == (0,)


class TestSearchFts:
    def test_returns_matching_notes(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# Pizza\n\nfood from Italy", "x.md")
        index_note(conn, make_fm("2026-05-20-b"), "# Code\n\nPython programming", "y.md")

        results = search_fts(conn, "pizza", k=5)
        assert len(results) == 1
        assert results[0]["id"] == "2026-05-20-a"
        assert results[0]["type"] == "semantic"
        assert "title" in results[0]
        assert "snippet" in results[0]

    def test_respects_k_limit(self, conn):
        for i in range(5):
            index_note(conn, make_fm(f"2026-05-20-n{i}"),
                       f"# Topic {i}\n\nshared keyword across all", "x.md")
        results = search_fts(conn, "shared", k=3)
        assert len(results) == 3

    def test_empty_corpus(self, conn):
        assert search_fts(conn, "anything", k=5) == []

    def test_no_matches(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# foo", "x.md")
        assert search_fts(conn, "bar", k=5) == []

    def test_diacritic_insensitive(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# café da manhã", "x.md")
        results = search_fts(conn, "cafe", k=5)
        assert len(results) == 1


class TestGetNote:
    def test_returns_note_data(self, conn, fake_brainiac):
        fm = make_fm(note_id="2026-05-20-a")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md", fm,
                   "# Title\n\ncorpo da nota")
        reindex_all(conn, fake_brainiac)

        result = get_note(conn, fake_brainiac, "2026-05-20-a")
        assert result["id"] == "2026-05-20-a"
        assert result["type"] == "semantic"
        assert "Title" in result["body"]
        assert result["frontmatter"]["access_count"] == 1  # incrementado

    def test_increments_access_count_on_disk(self, conn, fake_brainiac):
        path = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        write_note(path, make_fm(note_id="2026-05-20-a", access_count=2), "# x")
        reindex_all(conn, fake_brainiac)

        get_note(conn, fake_brainiac, "2026-05-20-a")

        fm_after, _ = parse_note(path)
        assert fm_after.access_count == 3

    def test_updates_last_access(self, conn, fake_brainiac):
        path = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        write_note(path, make_fm(note_id="2026-05-20-a"), "# x")
        reindex_all(conn, fake_brainiac)

        before = datetime.now(timezone.utc)
        get_note(conn, fake_brainiac, "2026-05-20-a")

        fm_after, _ = parse_note(path)
        assert fm_after.last_access >= before

    def test_raises_for_missing_note(self, conn, fake_brainiac):
        with pytest.raises(KeyError):
            get_note(conn, fake_brainiac, "2026-05-20-nonexistent")


class TestAddLink:
    def test_adds_link_in_frontmatter(self, conn, fake_brainiac):
        path_a = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        path_b = fake_brainiac / "semanticMemory" / "2026-05-20-b.md"
        write_note(path_a, make_fm(note_id="2026-05-20-a"), "# A")
        write_note(path_b, make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(path_a)
        assert "2026-05-20-b" in fm_a.links

    def test_adds_link_in_db(self, conn, fake_brainiac):
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
                   make_fm(note_id="2026-05-20-a"), "# A")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md",
                   make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        row = conn.execute(
            "SELECT src, dst, kind FROM links WHERE src=? AND dst=?",
            ("2026-05-20-a", "2026-05-20-b"),
        ).fetchone()
        assert row == ("2026-05-20-a", "2026-05-20-b", "explicit")

    def test_idempotent_no_duplicates(self, conn, fake_brainiac):
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
                   make_fm(note_id="2026-05-20-a"), "# A")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md",
                   make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")
        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md")
        assert fm_a.links.count("2026-05-20-b") == 1

    def test_raises_for_missing_source(self, conn, fake_brainiac):
        with pytest.raises(KeyError):
            add_link(conn, fake_brainiac, "2026-05-20-missing", "2026-05-20-other")


class TestListRecent:
    def test_orders_by_last_access_desc(self, conn):
        from datetime import datetime, timezone, timedelta
        base = datetime(2026, 5, 20, 10, tzinfo=timezone.utc)
        for i in range(3):
            fm = NoteFrontmatter(
                id=f"2026-05-20-n{i}",
                type="semantic",
                created=base,
                last_access=base + timedelta(hours=i),
                access_count=0,
                strength=1.0,
            )
            index_note(conn, fm, f"# {i}", f"x{i}.md")

        from brainiac.core.index import list_recent
        results = list_recent(conn, limit=10)
        ids = [r["id"] for r in results]
        assert ids == ["2026-05-20-n2", "2026-05-20-n1", "2026-05-20-n0"]

    def test_respects_limit(self, conn):
        for i in range(5):
            index_note(conn, make_fm(f"2026-05-20-n{i}"), f"# {i}", "x.md")
        from brainiac.core.index import list_recent
        results = list_recent(conn, limit=2)
        assert len(results) == 2

    def test_empty_returns_empty(self, conn):
        from brainiac.core.index import list_recent
        assert list_recent(conn, limit=10) == []
