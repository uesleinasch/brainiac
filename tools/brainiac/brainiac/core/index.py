import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from brainiac.core.models import NoteFrontmatter
from brainiac.core.note import parse_note, write_note

_MEMORY_DIRS = ("shortMemory", "longMemory", "semanticMemory")

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


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
) -> list[dict]:
    """Top-k search via FTS5 + BM25 ranking."""
    rows = conn.execute(
        """
        SELECT n.id, n.path, n.type, fts.title,
               snippet(notes_fts, 2, '[', ']', '...', 32) as snippet
        FROM notes_fts fts
        JOIN notes n ON n.id = fts.id
        WHERE notes_fts MATCH ?
        ORDER BY bm25(notes_fts)
        LIMIT ?
        """,
        (query, k),
    ).fetchall()
    return [
        {"id": r[0], "path": r[1], "type": r[2], "title": r[3], "snippet": r[4]}
        for r in rows
    ]


def reindex_all(conn: sqlite3.Connection, root: Path) -> int:
    """Wipe and rebuild index from .md files in memory dirs. Returns count.

    Idempotent: result depends only on filesystem state, not previous index state.
    """
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM notes_fts")
    conn.execute("DELETE FROM links WHERE kind = 'explicit'")

    count = 0
    for md_file in root.rglob("*.md"):
        rel = md_file.relative_to(root)
        if not rel.parts or rel.parts[0] not in _MEMORY_DIRS:
            continue
        try:
            fm, body = parse_note(md_file)
            index_note(conn, fm, body, str(rel))
            count += 1
        except Exception as exc:
            print(f"skipping {rel}: {exc}")

    conn.commit()
    return count


def get_note(conn: sqlite3.Connection, root: Path, note_id: str) -> dict:
    """Read a note, increment access_count, update last_access, reindex."""
    row = conn.execute(
        "SELECT path, type FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Note not found: {note_id}")

    rel_path, note_type = row
    full = root / rel_path
    fm, body = parse_note(full)

    fm.access_count += 1
    fm.last_access = datetime.now(timezone.utc)

    write_note(full, fm, body)
    index_note(conn, fm, body, rel_path)

    return {
        "id": fm.id,
        "type": fm.type,
        "path": rel_path,
        "frontmatter": fm.model_dump(mode="json"),
        "body": body,
    }


def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Return notes ordered by last_access desc."""
    rows = conn.execute(
        """
        SELECT id, path, type, last_access, access_count
        FROM notes
        ORDER BY last_access DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "path": r[1], "type": r[2],
            "last_access": r[3], "access_count": r[4],
        }
        for r in rows
    ]


def add_link(
    conn: sqlite3.Connection,
    root: Path,
    src: str,
    dst: str,
) -> None:
    """Add explicit link src→dst. Updates both frontmatter and index. Idempotent."""
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ?", (src,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Source note not found: {src}")

    rel_path = row[0]
    full = root / rel_path
    fm, body = parse_note(full)

    if dst not in fm.links:
        fm.links.append(dst)
        write_note(full, fm, body)
        index_note(conn, fm, body, rel_path)
