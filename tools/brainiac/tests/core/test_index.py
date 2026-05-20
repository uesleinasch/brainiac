import sqlite3
from pathlib import Path

import pytest


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
