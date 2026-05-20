import sqlite3
from pathlib import Path

import pytest

from tests.conftest import make_fm
from brainiac.core.index import index_note, reindex_all
from brainiac.core.note import write_note


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
        n = reindex_all(conn, fake_brainiac)
        assert n == 0

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

        n = reindex_all(conn, fake_brainiac)
        assert n == 3

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

        n = reindex_all(conn, fake_brainiac)
        assert n == 1

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

        n = reindex_all(conn, fake_brainiac)
        assert n == 1  # só a boa contou
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
        n = reindex_all(conn, fake_brainiac)
        assert n == 0
        rows = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
        assert rows == (0,)
