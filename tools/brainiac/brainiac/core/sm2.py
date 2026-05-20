from __future__ import annotations

from datetime import date, timedelta

from brainiac.core.models import SM2

EASE_FLOOR: float = 1.3
INITIAL_EASE: float = 2.5
INITIAL_INTERVAL: int = 1


def start_sm2(today: date | None = None) -> SM2:
    """Build the initial SM2 state for a note entering review.

    next_review = today so the note appears in the next review_queue immediately.
    """
    today = today or date.today()
    return SM2(
        ease=INITIAL_EASE,
        interval=INITIAL_INTERVAL,
        reps=0,
        next_review=today,
    )


def grade(sm2: SM2, q: int, today: date | None = None) -> SM2:
    """Apply a grade (0-5) to an SM2 state. Returns the new state.

    Canonical SuperMemo-2:
      ease' = max(1.3, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
      q < 3      → reps' = 0, interval' = 1
      reps == 0  → reps' = 1, interval' = 1
      reps == 1  → reps' = 2, interval' = 6
      reps >= 2  → reps' = reps + 1, interval' = round(interval * ease')
      next_review = today + interval' days
    """
    if not 0 <= q <= 5:
        raise ValueError(f"grade must be 0-5, got {q}")
    today = today or date.today()

    new_ease = max(
        EASE_FLOOR,
        sm2.ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02),
    )

    if q < 3:
        new_reps = 0
        new_interval = 1
    elif sm2.reps == 0:
        new_reps = 1
        new_interval = 1
    elif sm2.reps == 1:
        new_reps = 2
        new_interval = 6
    else:
        new_reps = sm2.reps + 1
        new_interval = max(1, round(sm2.interval * new_ease))

    return SM2(
        ease=new_ease,
        interval=new_interval,
        reps=new_reps,
        next_review=today + timedelta(days=new_interval),
    )


# --- I/O ---

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def start_review(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    today: date | None = None,
) -> SM2:
    """Enroll an existing note in spaced repetition. Sets initial SM2 state.

    Raises KeyError if note not found or archived.
    """
    from brainiac.core.events import log_event
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note

    today = today or date.today()
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active note not found: {note_id}")

    rel = row[0]
    full = root / rel
    fm, body = parse_note(full)
    fm.sm2 = start_sm2(today=today)
    write_note(full, fm, body)
    index_note(conn, fm, body, rel)

    log_event(
        root,
        note_id,
        "study_enrolled",
        f"next_review={fm.sm2.next_review.isoformat()}",
    )
    return fm.sm2


def review_queue(
    conn: sqlite3.Connection,
    today: date | None = None,
) -> list[dict]:
    """Return active enrolled notes due for review (next_review <= today).

    Ordered: most overdue first; ties broken by lower ease (harder cards first).
    """
    today = today or date.today()
    rows = conn.execute(
        """
        SELECT id, path, type, sm2_json
        FROM notes
        WHERE archived = 0 AND sm2_json IS NOT NULL
        ORDER BY json_extract(sm2_json, '$.next_review') ASC,
                 json_extract(sm2_json, '$.ease') ASC
        """,
    ).fetchall()

    out: list[dict] = []
    for note_id, rel_path, note_type, sm2_json in rows:
        sm2 = SM2.model_validate_json(sm2_json)
        if sm2.next_review > today:
            continue
        out.append({
            "id": note_id,
            "path": rel_path,
            "type": note_type,
            "ease": sm2.ease,
            "interval": sm2.interval,
            "reps": sm2.reps,
            "next_review": sm2.next_review.isoformat(),
            "days_overdue": (today - sm2.next_review).days,
        })
    return out


def grade_review(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    q: int,
    today: date | None = None,
) -> SM2:
    """Apply a grade to a note in review. Also bumps access_count / last_access.

    Raises KeyError if note not found or archived;
    ValueError if note has no sm2 state or q is out of range.
    """
    from brainiac.core.events import log_event
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note

    today = today or date.today()
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active note not found: {note_id}")

    rel = row[0]
    full = root / rel
    fm, body = parse_note(full)
    if fm.sm2 is None:
        raise ValueError(f"Note {note_id} is not enrolled in spaced repetition")

    new_sm2 = grade(fm.sm2, q, today=today)  # may raise ValueError on bad q

    fm.access_count += 1
    fm.last_access = datetime.now(timezone.utc)
    fm.sm2 = new_sm2

    write_note(full, fm, body)
    index_note(conn, fm, body, rel)

    log_event(
        root,
        note_id,
        "reviewed",
        f"q={q} ease={new_sm2.ease:.2f} interval={new_sm2.interval}d "
        f"next={new_sm2.next_review.isoformat()}",
    )
    return new_sm2
