from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class NoteState(str, Enum):
    SENSORY = "sensory"
    WORKING = "working"
    LONG_TERM = "long_term"
    ARCHIVED = "archived"


VALID_TRANSITIONS: dict[NoteState, set[NoteState]] = {
    NoteState.SENSORY: {NoteState.WORKING},
    NoteState.WORKING: {NoteState.LONG_TERM},
    NoteState.LONG_TERM: {NoteState.ARCHIVED},
    NoteState.ARCHIVED: {NoteState.LONG_TERM},
}


def current_state(conn: sqlite3.Connection, note_id: str) -> NoteState:
    """Derive state from notes table + sensory_buffer."""
    sensory_row = conn.execute(
        "SELECT id FROM sensory_buffer WHERE id = ?", (note_id,)
    ).fetchone()
    if sensory_row is not None:
        return NoteState.SENSORY

    note_row = conn.execute(
        "SELECT type, archived FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if note_row is None:
        raise KeyError(f"Note not found: {note_id}")

    note_type, archived = note_row
    if archived == 1:
        return NoteState.ARCHIVED
    if note_type == "working":
        return NoteState.WORKING
    if note_type in ("semantic", "episodic"):
        return NoteState.LONG_TERM
    raise ValueError(f"Unknown type for {note_id}: {note_type}")


def transition_note(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    target: NoteState,
    *,
    now: datetime | None = None,
    target_type: str = "semantic",
) -> NoteState:
    """Transition note to target state. Raises ValueError if invalid transition.

    target_type only used for working → long_term (determines if semantic or episodic).
    """
    from brainiac.core.consolidate import promote_note
    from brainiac.core.decay import archive_note
    from brainiac.core.events import log_event

    now = now or datetime.now(timezone.utc)
    cur = current_state(conn, note_id)

    if target not in VALID_TRANSITIONS[cur]:
        raise ValueError(f"invalid transition: {cur.value} → {target.value}")

    if cur == NoteState.WORKING and target == NoteState.LONG_TERM:
        promote_note(conn, root, note_id, target_type, now=now)
    elif cur == NoteState.LONG_TERM and target == NoteState.ARCHIVED:
        archive_note(conn, root, note_id, now=now)
    elif cur == NoteState.ARCHIVED and target == NoteState.LONG_TERM:
        _resurrect(conn, root, note_id, now=now)
    elif cur == NoteState.SENSORY and target == NoteState.WORKING:
        raise ValueError("Use commit_sensory(sensory_id, note_type, final_id) for sensory → working")

    log_event(
        root, note_id, "state_transition",
        f"{cur.value} → {target.value}",
    )
    return target


def _resurrect(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    *,
    now: datetime,
) -> None:
    """Move note from archive back to active (long-term)."""
    import shutil
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note
    from brainiac.core.paths import note_path

    row = conn.execute(
        "SELECT path, type FROM notes WHERE id = ? AND archived = 1",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Archived note not found: {note_id}")

    old_rel, note_type = row
    old_path = root / old_rel
    fm, body = parse_note(old_path)
    new_path = note_path(root, note_id, note_type)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_path), str(new_path))
    new_rel = str(new_path.relative_to(root))

    conn.execute(
        "UPDATE notes SET archived = 0, path = ? WHERE id = ?",
        (new_rel, note_id),
    )
    conn.commit()
    write_note(new_path, fm, body)
    index_note(conn, fm, body, new_rel)


def transition_probabilities(conn: sqlite3.Connection, note_id: str) -> dict:
    """Compute probability + reason for each possible transition from current state."""
    from brainiac.core.config import Config, load_config
    from brainiac.core.novelty import get_or_compute_novelty
    from brainiac.core.paths import find_root

    cur = current_state(conn, note_id)
    result: dict = {"current_state": cur.value, "transitions": {}}

    if cur == NoteState.SENSORY:
        result["transitions"]["working"] = {
            "probability": 1.0,
            "reason": "P_enc=1.0 on user commit_sensory",
        }
        return result

    if cur == NoteState.WORKING:
        root = find_root()
        config = load_config(root) if root else Config()
        row = conn.execute(
            "SELECT access_count, emotional_weight FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if row:
            R, E = row
            n_score = get_or_compute_novelty(conn, note_id)
            alpha = config.consolidation_learning_rate
            p = 1.0 - math.exp(-alpha * R * E * n_score)
        else:
            p = 0.0
        result["transitions"]["long_term"] = {
            "probability": p,
            "reason": "P_cons = 1 - exp(-α·R·E·n)",
        }
        return result

    if cur == NoteState.LONG_TERM:
        row = conn.execute(
            "SELECT strength FROM notes WHERE id = ?", (note_id,),
        ).fetchone()
        strength = row[0] if row else 0.5
        p_forget = 1.0 - strength
        result["transitions"]["archived"] = {
            "probability": p_forget,
            "reason": "P_forget = 1 - retention(Ebbinghaus)",
        }
        return result

    if cur == NoteState.ARCHIVED:
        result["transitions"]["long_term"] = {
            "probability": None,
            "reason": "manual via transition_note(target=LONG_TERM)",
        }
        return result

    return result
