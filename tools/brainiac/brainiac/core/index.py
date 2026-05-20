import hashlib
import json
import sqlite3
from pathlib import Path

from brainiac.core.models import NoteFrontmatter

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


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection and ensure schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def index_note(
    conn: sqlite3.Connection,
    fm: NoteFrontmatter,
    body: str,
    rel_path: str,
) -> None:
    """Insert or replace a note in all index tables. Syncs explicit links."""
    title = _extract_title(body)
    bh = _body_hash(body)

    conn.execute(
        """
        INSERT OR REPLACE INTO notes
        (id, path, type, created, last_access, access_count, strength,
         tags, sm2_json, body_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fm.id, rel_path, fm.type,
            fm.created.isoformat(), fm.last_access.isoformat(),
            fm.access_count, fm.strength,
            json.dumps(fm.tags),
            fm.sm2.model_dump_json() if fm.sm2 else None,
            bh,
        ),
    )

    # FTS5: delete + insert (FTS5 não suporta INSERT OR REPLACE com UNINDEXED)
    conn.execute("DELETE FROM notes_fts WHERE id = ?", (fm.id,))
    conn.execute(
        "INSERT INTO notes_fts (id, title, body) VALUES (?, ?, ?)",
        (fm.id, title, body),
    )

    # Sync explicit links: replace todos de src=fm.id, kind=explicit
    conn.execute(
        "DELETE FROM links WHERE src = ? AND kind = 'explicit'", (fm.id,)
    )
    for dst in fm.links:
        conn.execute(
            "INSERT OR IGNORE INTO links (src, dst, kind, weight) "
            "VALUES (?, ?, 'explicit', 1.0)",
            (fm.id, dst),
        )

    conn.commit()
