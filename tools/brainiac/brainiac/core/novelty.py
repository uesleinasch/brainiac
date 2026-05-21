from __future__ import annotations

import sqlite3

_DEFAULT_NOVELTY = 0.5  # used when no embedding is available


def compute_novelty(conn: sqlite3.Connection, note_id: str) -> float:
    """1 - max(cosine_similarity) with top-3 nearest neighbors, excluding self.

    Returns 1.0 if corpus has no other notes; 0.5 if note has no embedding.
    Bounded to [0.0, 1.0].
    """
    emb_row = conn.execute(
        "SELECT embedding FROM notes_vec WHERE id = ?", (note_id,)
    ).fetchone()
    if emb_row is None:
        return _DEFAULT_NOVELTY

    embedding = emb_row[0]

    rows = conn.execute(
        """
        SELECT vec_distance_cosine(embedding, ?) as dist
        FROM notes_vec
        WHERE id != ?
        ORDER BY dist ASC
        LIMIT 3
        """,
        (embedding, note_id),
    ).fetchall()

    if not rows:
        return 1.0  # alone in corpus

    min_dist = min(r[0] for r in rows)  # closest neighbor
    max_sim = 1.0 - min_dist  # cosine_sim = 1 - cosine_dist
    novelty = 1.0 - max_sim
    return max(0.0, min(1.0, novelty))


def cache_novelty(conn: sqlite3.Connection, note_id: str, value: float) -> None:
    """UPDATE notes SET novelty_score = ? WHERE id = ?"""
    conn.execute(
        "UPDATE notes SET novelty_score = ? WHERE id = ?",
        (value, note_id),
    )
    conn.commit()


def get_or_compute_novelty(conn: sqlite3.Connection, note_id: str) -> float:
    """Read from cache; if NULL, compute and cache."""
    row = conn.execute(
        "SELECT novelty_score FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is not None and row[0] is not None:
        return float(row[0])

    n = compute_novelty(conn, note_id)
    if row is not None:  # note exists in DB
        cache_novelty(conn, note_id, n)
    return n
