from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

from brainiac.core.config import Config

_EPSILON_HOURS = 1e-3  # avoid division by zero / very small Δt


def actr_activation(
    events: list[tuple[datetime, float]],
    now: datetime,
    d: float = 0.5,
) -> float:
    """ACT-R declarative memory activation.

    A(t) = ln( Σ wᵢ · (Δtᵢ)⁻ᵈ )

    where Δtᵢ = max(epsilon, (now - tᵢ)) in hours. Events at or beyond now
    are clamped to epsilon to avoid div-by-zero / negative time.

    Returns float('-inf') when events is empty (no trace yet).
    """
    if not events:
        return float("-inf")

    total = 0.0
    for ts, weight in events:
        delta_hours = (now - ts).total_seconds() / 3600.0
        if delta_hours < _EPSILON_HOURS:
            delta_hours = _EPSILON_HOURS
        total += weight * (delta_hours ** -d)
    return math.log(total)


# --- I/O ---

_SOURCE_LITERAL_DEFAULTS: dict[str, float] = {
    "get": 1.0,
    "review": 1.0,
}


def _resolve_weight(source: str, config: Config, explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    if source in _SOURCE_LITERAL_DEFAULTS:
        return _SOURCE_LITERAL_DEFAULTS[source]
    if source == "recall_hit":
        return config.actr_recall_hit_weight
    if source == "link_in":
        return config.actr_link_in_weight
    # Unknown source: return default; DB CHECK constraint will reject it
    return 1.0


def record_access(
    conn: sqlite3.Connection,
    note_id: str,
    source: str,
    *,
    now: datetime | None = None,
    weight: float | None = None,
    config: Config | None = None,
) -> None:
    """Insert one row into accesses. weight defaults derived from source via Config."""
    now = now or datetime.now(timezone.utc)
    config = config or Config()
    resolved = _resolve_weight(source, config, weight)
    conn.execute(
        "INSERT INTO accesses (note_id, ts, source, weight) VALUES (?, ?, ?, ?)",
        (note_id, now.isoformat(), source, resolved),
    )
    conn.commit()


def activation(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> float:
    """Current A(t) for a note, reading full accesses history."""
    now = now or datetime.now(timezone.utc)
    config = config or Config()
    rows = conn.execute(
        "SELECT ts, weight FROM accesses WHERE note_id = ?",
        (note_id,),
    ).fetchall()
    events = [(datetime.fromisoformat(r[0]), r[1]) for r in rows]
    return actr_activation(events, now, d=config.actr_decay)


def activation_batch(
    conn: sqlite3.Connection,
    note_ids: list[str],
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> dict[str, float]:
    """Compute A(t) for many notes in one query. Notes with no events → -inf."""
    if not note_ids:
        return {}
    now = now or datetime.now(timezone.utc)
    config = config or Config()

    placeholders = ",".join("?" * len(note_ids))
    rows = conn.execute(
        f"SELECT note_id, ts, weight FROM accesses WHERE note_id IN ({placeholders}) ORDER BY note_id, ts",
        note_ids,
    ).fetchall()

    grouped: dict[str, list[tuple[datetime, float]]] = {nid: [] for nid in note_ids}
    for nid, ts, w in rows:
        grouped[nid].append((datetime.fromisoformat(ts), w))

    return {nid: actr_activation(events, now, d=config.actr_decay) for nid, events in grouped.items()}


def access_history(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Last N events for a note, ordered by ts DESC. [{ts, source, weight}]."""
    rows = conn.execute(
        "SELECT ts, source, weight FROM accesses WHERE note_id = ? ORDER BY ts DESC LIMIT ?",
        (note_id, limit),
    ).fetchall()
    return [{"ts": r[0], "source": r[1], "weight": r[2]} for r in rows]
