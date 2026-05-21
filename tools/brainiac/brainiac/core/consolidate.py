from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def consolidation_candidates(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    window_days: int = 7,
    *,
    activation_threshold: float = 1.5,
) -> list[dict]:
    """Return working notes ready for promotion.

    Primary criteria (Phase 2): type='working', archived=0, access_count >= 3,
    last_access within window_days, fan_in >= 1.

    Borderline (Phase 5): access_count = 2 + fan_in >= 1 + activation >= threshold.
    """
    from brainiac.core.activation import activation_batch

    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=window_days)).isoformat()

    primary_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.access_count >= 3
          AND n.last_access >= ?
        GROUP BY n.id
        HAVING fan_in >= 1
        ORDER BY n.access_count DESC
        """,
        (cutoff,),
    ).fetchall()

    out = [
        {
            "id": r[0], "path": r[1], "access_count": r[2],
            "last_access": r[3], "fan_in": r[4],
            "suggested_type": "semantic",
        }
        for r in primary_rows
    ]
    seen = {c["id"] for c in out}

    # Borderline path
    borderline_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.access_count = 2
          AND n.last_access >= ?
        GROUP BY n.id
        HAVING fan_in >= 1
        """,
        (cutoff,),
    ).fetchall()

    if borderline_rows:
        borderline_ids = [r[0] for r in borderline_rows if r[0] not in seen]
        if borderline_ids:
            acts = activation_batch(conn, borderline_ids, now=now)
            for r in borderline_rows:
                if r[0] in seen:
                    continue
                if acts.get(r[0], float("-inf")) >= activation_threshold:
                    out.append({
                        "id": r[0], "path": r[1], "access_count": r[2],
                        "last_access": r[3], "fan_in": r[4],
                        "suggested_type": "semantic",
                    })
                    seen.add(r[0])

    # Phase 7: probabilistic path
    import math
    from brainiac.core.config import Config, load_config
    from brainiac.core.novelty import get_or_compute_novelty
    from brainiac.core.paths import find_root

    root = find_root()
    config = load_config(root) if root else Config()

    prob_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               n.emotional_weight, COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.last_access >= ?
        GROUP BY n.id
        """,
        (cutoff,),
    ).fetchall()

    for r in prob_rows:
        nid = r[0]
        if nid in seen:
            continue
        R = r[2]  # access_count
        E = r[4]  # emotional_weight
        n_score = get_or_compute_novelty(conn, nid)
        alpha = config.consolidation_learning_rate
        p = 1.0 - math.exp(-alpha * R * E * n_score)
        if p >= config.consolidation_probability_threshold:
            out.append({
                "id": nid,
                "path": r[1],
                "access_count": R,
                "last_access": r[3],
                "fan_in": r[5],
                "suggested_type": "semantic",
                "consolidation_probability": p,
            })
            seen.add(nid)

    return out


def promote_note(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    target_type: str,
    now: datetime | None = None,
) -> str:
    """Promote a working note to semantic or episodic memory.

    Moves file, updates type and resets strength to 1.0, reindexes, logs event.
    Returns new relative path. Raises KeyError if note not found.
    """
    _VALID_TARGET_TYPES = {"semantic", "episodic"}
    if target_type not in _VALID_TARGET_TYPES:
        raise ValueError(f"target_type must be one of {_VALID_TARGET_TYPES}, got: {target_type!r}")

    from brainiac.core.events import log_event
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note
    from brainiac.core.paths import note_dir

    now = now or datetime.now(timezone.utc)

    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND type = 'working' AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active working note not found: {note_id}")

    old_rel = row[0]
    old_path = root / old_rel
    fm, body = parse_note(old_path)

    target_dir = note_dir(root, target_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    new_path = target_dir / old_path.name
    old_path.rename(new_path)
    new_rel = str(new_path.relative_to(root))

    fm = fm.model_copy(update={"type": target_type, "strength": 1.0})
    write_note(new_path, fm, body)
    index_note(conn, fm, body, new_rel, archived=False)

    log_event(root, note_id, "promoted", f"{old_rel} → {new_rel} (type={target_type})")
    return new_rel
