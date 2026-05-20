import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


# --- events.py tests ---

def test_log_event_creates_jsonl_file(fake_brainiac):
    from brainiac.core.events import log_event
    log_event(fake_brainiac, "2026-05-20-x", "accessed")
    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    assert events_file.exists()


def test_log_event_appends_valid_json_lines(fake_brainiac):
    from brainiac.core.events import log_event
    log_event(fake_brainiac, "2026-05-20-a", "created", "body")
    log_event(fake_brainiac, "2026-05-20-b", "archived")
    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) == 2
    entry = json.loads(lines[0])
    assert entry["note_id"] == "2026-05-20-a"
    assert entry["action"] == "created"
    assert entry["detail"] == "body"
    assert "ts" in entry


def test_log_event_second_call_appends_not_overwrites(fake_brainiac):
    from brainiac.core.events import log_event
    log_event(fake_brainiac, "2026-05-20-a", "accessed")
    log_event(fake_brainiac, "2026-05-20-a", "accessed")
    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    lines = [l for l in events_file.read_text().strip().split("\n") if l]
    assert len(lines) == 2


import math


# --- decay.py pure functions ---

def test_stability_at_zero_accesses():
    from brainiac.core.decay import S0_HOURS, stability
    assert stability(0) == pytest.approx(S0_HOURS)


def test_stability_grows_with_accesses():
    from brainiac.core.decay import ALPHA, S0_HOURS, stability
    # S = S0 * (1 + alpha * 3) = 24 * (1 + 0.5*3) = 24 * 2.5 = 60
    assert stability(3) == pytest.approx(S0_HOURS * (1 + ALPHA * 3))


def test_retention_at_zero_time_is_one():
    from brainiac.core.decay import retention
    assert retention(0.0, 24.0) == pytest.approx(1.0)


def test_retention_decays_exponentially():
    from brainiac.core.decay import retention
    s = 24.0
    # R(24h) = exp(-24/24) = exp(-1)
    assert retention(24.0, s) == pytest.approx(math.exp(-1), rel=1e-5)


def test_updated_strength_fresh_note_is_near_one():
    from brainiac.core.decay import updated_strength
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)  # 2h ago
    s = updated_strength(last, access_count=0, now=now)
    assert s > 0.9  # 2h decay with S0=24 → exp(-2/24) ≈ 0.92


def test_updated_strength_30days_with_1_access_below_threshold():
    from brainiac.core.decay import ARCHIVE_THRESHOLD, updated_strength
    last = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)  # 30 days = 720h
    s = updated_strength(last, access_count=1, now=now)
    # S = 24*(1+0.5*1) = 36h; R = exp(-720/36) = exp(-20) ≈ 2e-9
    assert s < ARCHIVE_THRESHOLD


def test_updated_strength_frequent_access_stays_above_threshold():
    from brainiac.core.decay import ARCHIVE_THRESHOLD, updated_strength
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    # 10 accesses 7 days ago: S = 24*(1+0.5*10) = 144h; R = exp(-168/144) ≈ 0.31
    last_week = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    s = updated_strength(last_week, access_count=10, now=now)
    assert s > ARCHIVE_THRESHOLD


def test_archive_threshold_is_0_2():
    from brainiac.core.decay import ARCHIVE_THRESHOLD
    assert ARCHIVE_THRESHOLD == pytest.approx(0.2)


def test_s0_and_alpha_defaults():
    from brainiac.core.decay import ALPHA, S0_HOURS
    assert S0_HOURS == pytest.approx(24.0)
    assert ALPHA == pytest.approx(0.5)


# --- archive_note + run_decay integration tests ---

def _seed_note(
    fake_brainiac: Path,
    note_id: str,
    note_type: str = "semantic",
    last_access: datetime | None = None,
    access_count: int = 0,
) -> None:
    """Create and index a note in fake_brainiac."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm(note_id=note_id, note_type=note_type,
                 access_count=access_count, last_access=last_access)
    p = note_path(fake_brainiac, note_id, note_type)
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    rel = str(p.relative_to(fake_brainiac))
    index_note(conn, fm, f"# {note_id}\n\nbody", rel)


def test_archive_note_moves_file_to_archive_dir(fake_brainiac):
    from brainiac.core.decay import archive_note
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    _seed_note(fake_brainiac, "2026-05-20-arc-move", "semantic")
    conn = connect(index_db_path(fake_brainiac))
    archive_note(conn, fake_brainiac, "2026-05-20-arc-move", now=now)

    original = fake_brainiac / "semanticMemory" / "2026-05-20-arc-move.md"
    archived = fake_brainiac / "memoryTransfer" / "archive" / "2026" / "2026-05-20-arc-move.md"
    assert not original.exists()
    assert archived.exists()


def test_archive_note_marks_db_archived(fake_brainiac):
    from brainiac.core.decay import archive_note
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    _seed_note(fake_brainiac, "2026-05-20-arc-db", "semantic")
    conn = connect(index_db_path(fake_brainiac))
    archive_note(conn, fake_brainiac, "2026-05-20-arc-db", now=now)

    row = conn.execute(
        "SELECT archived FROM notes WHERE id = ?", ("2026-05-20-arc-db",)
    ).fetchone()
    assert row is not None
    assert row[0] == 1


def test_archive_note_logs_event(fake_brainiac):
    from brainiac.core.decay import archive_note
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    _seed_note(fake_brainiac, "2026-05-20-arc-log", "semantic")
    conn = connect(index_db_path(fake_brainiac))
    archive_note(conn, fake_brainiac, "2026-05-20-arc-log", now=now)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    assert any(e["note_id"] == "2026-05-20-arc-log" and e["action"] == "archived" for e in entries)


def test_archive_note_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.decay import archive_note
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        archive_note(conn, fake_brainiac, "2026-05-20-nonexistent")


def test_run_decay_archives_note_with_low_strength(fake_brainiac):
    from brainiac.core.decay import run_decay
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    old_access = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)

    _seed_note(fake_brainiac, "2026-03-21-stale", "semantic",
               last_access=old_access, access_count=0)
    conn = connect(index_db_path(fake_brainiac))
    stats = run_decay(conn, fake_brainiac, now=now)

    assert stats["archived"] == 1
    archived_path = fake_brainiac / "memoryTransfer" / "archive" / "2026" / "2026-03-21-stale.md"
    assert archived_path.exists()


def test_run_decay_preserves_strong_note(fake_brainiac):
    from brainiac.core.decay import run_decay
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    recent = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)

    _seed_note(fake_brainiac, "2026-05-19-fresh", "semantic",
               last_access=recent, access_count=10)
    conn = connect(index_db_path(fake_brainiac))
    stats = run_decay(conn, fake_brainiac, now=now)

    assert stats["archived"] == 0
    assert (fake_brainiac / "semanticMemory" / "2026-05-19-fresh.md").exists()


def test_run_decay_returns_stats_dict(fake_brainiac):
    from brainiac.core.decay import run_decay
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    _seed_note(fake_brainiac, "2026-05-20-stat", "semantic")
    conn = connect(index_db_path(fake_brainiac))
    stats = run_decay(conn, fake_brainiac, now=now)

    assert set(stats.keys()) == {"checked", "updated", "archived"}
    assert stats["checked"] >= 1


def test_run_decay_dry_run_does_not_archive(fake_brainiac):
    from brainiac.core.decay import run_decay
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    old_access = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    _seed_note(fake_brainiac, "2026-03-21-dry", "semantic",
               last_access=old_access, access_count=0)
    conn = connect(index_db_path(fake_brainiac))
    stats = run_decay(conn, fake_brainiac, now=now, dry_run=True)

    assert stats["archived"] >= 1
    assert (fake_brainiac / "semanticMemory" / "2026-03-21-dry.md").exists()
