from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _gen_id(now: datetime) -> str:
    """sensory-<timestamp>-<short_uuid>."""
    ts = now.strftime("%Y%m%d-%H%M%S")
    suf = uuid.uuid4().hex[:8]
    return f"sensory-{ts}-{suf}"


def add_sensory(
    conn: sqlite3.Connection,
    body: str,
    *,
    title: str | None = None,
    proposed_type: str | None = None,
    proposed_id: str | None = None,
    now: datetime | None = None,
    ttl_minutes: int = 5,
) -> str:
    """Insert a sensory draft. Returns generated id."""
    now = now or datetime.now(timezone.utc)
    sid = _gen_id(now)
    expires = now + timedelta(minutes=ttl_minutes)
    conn.execute(
        """
        INSERT INTO sensory_buffer (id, title, body, created, expires_at, proposed_type, proposed_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, title, body, now.isoformat(), expires.isoformat(), proposed_type, proposed_id),
    )
    conn.commit()
    return sid


def list_sensory(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    include_expired: bool = False,
) -> list[dict]:
    """List sensory buffer entries. Excludes expired unless include_expired=True."""
    now = now or datetime.now(timezone.utc)
    if include_expired:
        sql = "SELECT id, title, body, created, expires_at, proposed_type, proposed_id FROM sensory_buffer ORDER BY created DESC"
        params: tuple = ()
    else:
        sql = """
            SELECT id, title, body, created, expires_at, proposed_type, proposed_id
            FROM sensory_buffer WHERE expires_at > ? ORDER BY created DESC
        """
        params = (now.isoformat(),)
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": r[0], "title": r[1], "body": r[2],
            "created": r[3], "expires_at": r[4],
            "proposed_type": r[5], "proposed_id": r[6],
        }
        for r in rows
    ]


def get_sensory(conn: sqlite3.Connection, sensory_id: str) -> dict | None:
    """Return one entry, or None if missing."""
    row = conn.execute(
        "SELECT id, title, body, created, expires_at, proposed_type, proposed_id FROM sensory_buffer WHERE id = ?",
        (sensory_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "title": row[1], "body": row[2],
        "created": row[3], "expires_at": row[4],
        "proposed_type": row[5], "proposed_id": row[6],
    }


def commit_sensory(
    conn: sqlite3.Connection,
    root: Path,
    sensory_id: str,
    *,
    note_type: str,
    final_id: str,
) -> str:
    """Promote sensory draft → working note. Returns final_id.

    Raises KeyError if sensory_id not found.
    """
    from brainiac.core.index import index_note
    from brainiac.core.note import new_note, write_note
    from brainiac.core.paths import note_path

    entry = get_sensory(conn, sensory_id)
    if entry is None:
        raise KeyError(f"sensory entry not found: {sensory_id}")

    fm = new_note(note_id=final_id, note_type=note_type)
    body = entry["body"]
    if not body.lstrip().startswith("#"):
        title = entry["title"] or final_id
        body = f"# {title}\n\n{body}"

    path = note_path(root, final_id, note_type)
    write_note(path, fm, body)
    rel = str(path.relative_to(root))
    index_note(conn, fm, body, rel)

    conn.execute("DELETE FROM sensory_buffer WHERE id = ?", (sensory_id,))
    conn.commit()
    return final_id


def expire_sensory(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Delete expired entries. Returns count deleted."""
    now = now or datetime.now(timezone.utc)
    cur = conn.execute(
        "DELETE FROM sensory_buffer WHERE expires_at <= ?",
        (now.isoformat(),),
    )
    conn.commit()
    return cur.rowcount
