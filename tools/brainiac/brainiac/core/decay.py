from __future__ import annotations

import math
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

S0_HOURS: float = 24.0
ALPHA: float = 0.5
ARCHIVE_THRESHOLD: float = 0.2


def stability(access_count: int, s0: float = S0_HOURS, alpha: float = ALPHA) -> float:
    """Stability S = S0 * (1 + alpha * access_count). Grows with repetition."""
    return s0 * (1.0 + alpha * access_count)


def retention(delta_hours: float, s: float) -> float:
    """Retention R(Δt) = exp(-Δt / S). Probability of recall after Δt hours."""
    return math.exp(-delta_hours / s)


def updated_strength(
    last_access: datetime,
    access_count: int,
    now: datetime | None = None,
) -> float:
    """Compute current strength based on Ebbinghaus forgetting curve."""
    now = now or datetime.now(timezone.utc)
    delta_hours = (now - last_access).total_seconds() / 3600.0
    s = stability(access_count)
    return retention(delta_hours, s)


def archive_note(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    now: datetime | None = None,
) -> str:
    """Move note to memoryTransfer/archive/<year>/ and mark archived in DB.

    Returns new relative path. Raises KeyError if note not found or already archived.
    """
    from brainiac.core.events import log_event

    now = now or datetime.now(timezone.utc)

    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active note not found: {note_id}")

    old_rel = row[0]
    old_path = root / old_rel

    archive_dir = root / "memoryTransfer" / "archive" / str(now.year)
    archive_dir.mkdir(parents=True, exist_ok=True)

    new_path = archive_dir / old_path.name
    shutil.move(str(old_path), str(new_path))
    new_rel = str(new_path.relative_to(root))

    conn.execute(
        "UPDATE notes SET archived = 1, path = ? WHERE id = ?",
        (new_rel, note_id),
    )
    conn.commit()

    log_event(root, note_id, "archived", f"moved {old_rel} → {new_rel}")
    return new_rel


def run_decay(
    conn: sqlite3.Connection,
    root: Path,
    now: datetime | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    """Run Ebbinghaus decay on all active notes. Archives those below threshold.

    Returns {"checked": int, "updated": int, "archived": int}.
    """
    now = now or datetime.now(timezone.utc)

    rows = conn.execute(
        "SELECT id, last_access, access_count FROM notes WHERE archived = 0"
    ).fetchall()

    stats: dict[str, int] = {"checked": len(rows), "updated": 0, "archived": 0}
    to_archive: list[str] = []

    for note_id, last_access_str, access_count in rows:
        last_access = datetime.fromisoformat(last_access_str)
        new_s = updated_strength(last_access, access_count, now=now)

        if not dry_run:
            conn.execute(
                "UPDATE notes SET strength = ? WHERE id = ?",
                (new_s, note_id),
            )
            stats["updated"] += 1

        if new_s < ARCHIVE_THRESHOLD:
            to_archive.append(note_id)

    if not dry_run:
        conn.commit()
        for note_id in to_archive:
            try:
                archive_note(conn, root, note_id, now=now)
                stats["archived"] += 1
            except (KeyError, FileNotFoundError):
                pass
    else:
        stats["archived"] = len(to_archive)

    return stats
