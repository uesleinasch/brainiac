from __future__ import annotations

import sqlite3

from brainiac.core.config import Config


class WorkingMemoryFullError(Exception):
    """Raised when adding a working note would exceed the configured limit."""

    def __init__(self, count: int, limit: int, candidates: list[dict]):
        self.count = count
        self.limit = limit
        self.candidates = candidates
        super().__init__(f"shortMemory at capacity ({count}/{limit})")


def working_count(conn: sqlite3.Connection) -> int:
    """Count of active (non-archived) working notes."""
    row = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE type='working' AND archived=0"
    ).fetchone()
    return int(row[0])


def candidates_for_eviction(
    conn: sqlite3.Connection,
    limit: int = 5,
) -> list[dict]:
    """Top-N working notes most likely worth promoting or discarding.

    Sorted by access_count DESC (most-touched first — strong promotion candidates),
    tiebroken by strength ASC (weakest first — discard candidates).
    """
    rows = conn.execute(
        """
        SELECT id, path, access_count, strength
        FROM notes
        WHERE type='working' AND archived=0
        ORDER BY access_count DESC, strength ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {"id": r[0], "path": r[1], "access_count": r[2], "strength": r[3]}
        for r in rows
    ]


def check_working_capacity(conn: sqlite3.Connection, config: Config) -> None:
    """Raise WorkingMemoryFullError if adding a new working note would exceed limit."""
    count = working_count(conn)
    if count >= config.working_memory_limit:
        candidates = candidates_for_eviction(conn, limit=5)
        raise WorkingMemoryFullError(count, config.working_memory_limit, candidates)


def working_status(conn: sqlite3.Connection, config: Config) -> dict:
    """Snapshot of working memory occupancy and eviction candidates."""
    count = working_count(conn)
    limit = config.working_memory_limit
    is_full = count >= limit
    return {
        "count": count,
        "limit": limit,
        "full": is_full,
        "candidates": candidates_for_eviction(conn, limit=5) if is_full else [],
    }
