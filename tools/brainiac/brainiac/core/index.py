import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec

from brainiac.core import embeddings
from brainiac.core.graph import NEIGHBOR_DECAY, neighbors_of
from brainiac.core.models import NoteFrontmatter
from brainiac.core.note import parse_note, write_note

_MEMORY_DIRS = ("shortMemory", "longMemory", "semanticMemory")
_ARCHIVE_SUBDIR = ("memoryTransfer", "archive")

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
    body_hash TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    id UNINDEXED, title, body,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0(
    id TEXT PRIMARY KEY,
    embedding FLOAT[384]
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
    """Open SQLite connection, load sqlite-vec, ensure schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(_SCHEMA)
    # idempotent migration for existing DBs created before Phase 2
    try:
        conn.execute("ALTER TABLE notes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Phase 5: accesses table for ACT-R activation
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('get', 'review', 'recall_hit', 'link_in')),
            weight REAL NOT NULL DEFAULT 1.0
        );
        CREATE INDEX IF NOT EXISTS idx_accesses_note_ts ON accesses(note_id, ts);
    """)
    conn.commit()
    return conn


def _existing_body_hash(conn: sqlite3.Connection, note_id: str) -> str | None:
    row = conn.execute("SELECT body_hash FROM notes WHERE id = ?", (note_id,)).fetchone()
    return row[0] if row else None


def _store_embedding(conn: sqlite3.Connection, note_id: str, title: str, body: str) -> None:
    text = f"{title}\n\n{body}" if title else body
    try:
        vec = embeddings.embed_texts([text])[0]
    except Exception:
        return  # fail-soft: vec index stays stale; FTS5 still works
    payload = sqlite_vec.serialize_float32(vec.tolist())
    conn.execute("DELETE FROM notes_vec WHERE id = ?", (note_id,))
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        (note_id, payload),
    )


def index_note(
    conn: sqlite3.Connection,
    fm: NoteFrontmatter,
    body: str,
    rel_path: str,
    *,
    archived: bool = False,
) -> None:
    """Insert or replace a note in all index tables. Syncs explicit links."""
    title = _extract_title(body)
    bh = _body_hash(body)
    prev_hash = _existing_body_hash(conn, fm.id)
    needs_embed = prev_hash != bh

    conn.execute(
        """
        INSERT OR REPLACE INTO notes
        (id, path, type, created, last_access, access_count, strength,
         tags, sm2_json, body_hash, archived)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fm.id, rel_path, fm.type,
            fm.created.isoformat(), fm.last_access.isoformat(),
            fm.access_count, fm.strength,
            json.dumps(fm.tags),
            fm.sm2.model_dump_json() if fm.sm2 else None,
            bh,
            1 if archived else 0,
        ),
    )

    conn.execute("DELETE FROM notes_fts WHERE id = ?", (fm.id,))
    conn.execute(
        "INSERT INTO notes_fts (id, title, body) VALUES (?, ?, ?)",
        (fm.id, title, body),
    )

    conn.execute(
        "DELETE FROM links WHERE src = ? AND kind = 'explicit'", (fm.id,)
    )
    for dst in fm.links:
        conn.execute(
            "INSERT OR IGNORE INTO links (src, dst, kind, weight) "
            "VALUES (?, ?, 'explicit', 1.0)",
            (fm.id, dst),
        )

    if needs_embed:
        _store_embedding(conn, fm.id, title, body)

    conn.commit()


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    include_archived: bool = False,
) -> list[dict]:
    """Top-k search via FTS5 + BM25 ranking."""
    sql = """
        SELECT n.id, n.path, n.type, fts.title,
               snippet(notes_fts, 2, '[', ']', '...', 32) as snippet
        FROM notes_fts fts
        JOIN notes n ON n.id = fts.id
        WHERE notes_fts MATCH ?
    """
    if not include_archived:
        sql += " AND n.archived = 0"
    sql += " ORDER BY bm25(notes_fts) LIMIT ?"
    rows = conn.execute(sql, (query, k)).fetchall()
    return [
        {"id": r[0], "path": r[1], "type": r[2], "title": r[3], "snippet": r[4]}
        for r in rows
    ]


def search_vec(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    include_archived: bool = False,
) -> list[dict]:
    """Top-k semantic search via cosine distance over notes_vec."""
    qvec = embeddings.embed_query(query)
    payload = sqlite_vec.serialize_float32(qvec.tolist())
    sql = """
        SELECT n.id, n.path, n.type,
               vec_distance_cosine(v.embedding, ?) as dist,
               (SELECT title FROM notes_fts f WHERE f.id = n.id) as title
        FROM notes_vec v JOIN notes n ON n.id = v.id
    """
    if not include_archived:
        sql += " WHERE n.archived = 0"
    sql += " ORDER BY dist ASC LIMIT ?"
    rows = conn.execute(sql, (payload, k)).fetchall()
    return [
        {
            "id": r[0], "path": r[1], "type": r[2],
            "title": r[4] or "",
            "score": float(1.0 - r[3]),
        }
        for r in rows
    ]


def reindex_all(conn: sqlite3.Connection, root: Path) -> tuple[int, int]:
    """Wipe and rebuild index from .md files. Returns (active_count, archived_count).

    Idempotent: scans both active memory dirs and memoryTransfer/archive/.
    """
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM notes_fts")
    conn.execute("DELETE FROM links WHERE kind = 'explicit'")
    conn.execute("DELETE FROM notes_vec")

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

    archived_count = 0
    archive_root = root / _ARCHIVE_SUBDIR[0] / _ARCHIVE_SUBDIR[1]
    if archive_root.exists():
        for md_file in archive_root.rglob("*.md"):
            rel = md_file.relative_to(root)
            try:
                fm, body = parse_note(md_file)
                index_note(conn, fm, body, str(rel), archived=True)
                archived_count += 1
            except Exception as exc:
                print(f"skipping archive {rel}: {exc}")

    conn.commit()
    return count, archived_count


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

    from brainiac.core.activation import record_access
    record_access(conn, fm.id, "get")

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

        from brainiac.core.activation import record_access
        record_access(conn, dst, "link_in")


def _fallback_fts(
    conn: sqlite3.Connection,
    query: str,
    k: int,
    include_archived: bool = False,
) -> list[dict]:
    out = []
    for r in search_fts(conn, query, k=k, include_archived=include_archived):
        out.append({
            "id": r["id"], "path": r["path"], "type": r["type"],
            "title": r["title"], "snippet": r.get("snippet", ""),
            "score": 0.0, "origin": "fts",
        })
    return out


def recall(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    include_archived: bool = False,
) -> list[dict]:
    """Recall associativo: semantic top-k + 1-hop expansion + badges.

    Falls back to FTS5 if embeddings model unavailable.
    Archived notes excluded by default; pass include_archived=True to include.
    """
    if not embeddings.model_available():
        try:
            embeddings.embed_query("warmup")
        except Exception:
            return _fallback_fts(conn, query, k, include_archived=include_archived)

    try:
        seeds = search_vec(conn, query, k=k, include_archived=include_archived)
    except Exception:
        return _fallback_fts(conn, query, k, include_archived=include_archived)

    scored: dict[str, dict] = {}
    for s in seeds:
        scored[s["id"]] = {
            "id": s["id"],
            "path": s["path"],
            "type": s["type"],
            "title": s["title"],
            "score": float(s["score"]),
            "origin": "semantic",
        }

    # Phase 6: N-hop spreading activation (replaces Phase 1's 1-hop)
    from brainiac.core.config import load_config
    from brainiac.core.paths import find_root
    from brainiac.core.spreading import load_edges, spread_activation

    try:
        config = load_config(find_root())
    except Exception:
        from brainiac.core.config import Config
        config = Config()

    # Ensure seeds always have enough activation to propagate (cosine may be 0
    # in orthogonal/near-orthogonal embeddings, which would silence spreading).
    seed_dict = {
        s["id"]: max(float(s["score"]), config.spreading_floor)
        for s in seeds
    }
    edges = load_edges(conn)
    spread_result = spread_activation(
        seed_dict, edges,
        max_hops=config.spreading_max_hops,
        decay=config.spreading_decay,
        epsilon=config.spreading_epsilon,
        floor=config.spreading_floor,
    )

    for nid, score in spread_result.items():
        if nid in scored:
            scored[nid]["score"] = max(scored[nid]["score"], score)
            if scored[nid]["origin"] == "semantic":
                scored[nid]["origin"] = "both"
        else:
            row = conn.execute(
                "SELECT path, type, archived FROM notes WHERE id = ?", (nid,)
            ).fetchone()
            if row is None:
                continue
            if not include_archived and row[2] == 1:
                continue
            title_row = conn.execute(
                "SELECT title FROM notes_fts WHERE id = ?", (nid,)
            ).fetchone()
            scored[nid] = {
                "id": nid,
                "path": row[0],
                "type": row[1],
                "title": title_row[0] if title_row else "",
                "score": score,
                "origin": "implicit",  # came via spreading
            }

    # Phase 5: combine semantic score with ACT-R activation (z-score normalized per query)
    import statistics
    from brainiac.core.activation import activation_batch, record_access

    candidate_ids = list(scored.keys())
    acts = activation_batch(conn, candidate_ids)
    finite_vals = [v for v in acts.values() if v != float("-inf")]
    mean = statistics.fmean(finite_vals) if finite_vals else 0.0
    stdev = statistics.stdev(finite_vals) if len(finite_vals) > 1 else 1.0

    ALPHA, BETA = 0.7, 0.3
    for nid, item in scored.items():
        a = acts.get(nid, float("-inf"))
        # Notes with no access history (-inf) get -1.0 (one stdev below mean),
        # ensuring any note with real activation outranks un-accessed notes.
        a_norm = -1.0 if a == float("-inf") else (a - mean) / (stdev or 1.0)
        item["score"] = ALPHA * item["score"] + BETA * a_norm

    results = sorted(scored.values(), key=lambda r: r["score"], reverse=True)
    top_k = results[:k]

    # Record recall_hit AFTER reorder (the current query already saw the previous state)
    for hit in top_k:
        record_access(conn, hit["id"], "recall_hit")

    return top_k
