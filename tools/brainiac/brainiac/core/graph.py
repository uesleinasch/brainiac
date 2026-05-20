"""Grafo de notas: links explícitos (persistidos) + implícitos (cosine em runtime)."""

from __future__ import annotations

import sqlite3

import sqlite_vec

IMPLICIT_THRESHOLD: float = 0.75
NEIGHBOR_DECAY: float = 0.5


def _explicit_neighbors(conn: sqlite3.Connection, note_id: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT dst, weight FROM links WHERE src = ? AND kind = 'explicit'",
        (note_id,),
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _implicit_neighbors(
    conn: sqlite3.Connection,
    note_id: str,
    threshold: float = IMPLICIT_THRESHOLD,
    limit: int = 20,
) -> dict[str, float]:
    row = conn.execute(
        "SELECT embedding FROM notes_vec WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        return {}
    payload = row[0]
    rows = conn.execute(
        """
        SELECT id, vec_distance_cosine(embedding, ?) as dist
        FROM notes_vec
        WHERE id != ?
        ORDER BY dist ASC
        LIMIT ?
        """,
        (payload, note_id, limit),
    ).fetchall()
    out: dict[str, float] = {}
    for rid, dist in rows:
        sim = 1.0 - float(dist)
        if sim >= threshold:
            out[rid] = sim
    return out


def neighbors_of(
    conn: sqlite3.Connection,
    note_id: str,
    threshold: float = IMPLICIT_THRESHOLD,
) -> dict[str, dict]:
    """Retorna mapa id → {kind, weight}. Explícitos prevalecem sobre implícitos."""
    expl = _explicit_neighbors(conn, note_id)
    impl = _implicit_neighbors(conn, note_id, threshold=threshold)
    out: dict[str, dict] = {}
    for dst, w in impl.items():
        out[dst] = {"kind": "implicit", "weight": w}
    for dst, w in expl.items():
        out[dst] = {"kind": "explicit", "weight": w}
    return out
