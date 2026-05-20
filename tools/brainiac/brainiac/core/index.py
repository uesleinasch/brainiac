import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('episodic','semantic','working')),
    created TEXT NOT NULL,
    last_access TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    strength REAL NOT NULL DEFAULT 1.0,
    tags TEXT,
    sm2_json TEXT,
    body_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    id UNINDEXED, title, body,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS links (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('explicit','implicit')),
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src, dst, kind)
);

CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_last_access ON notes(last_access);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection and ensure schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
