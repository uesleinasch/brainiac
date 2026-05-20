from datetime import datetime, timezone
from pathlib import Path

import pytest

from brainiac.core.config import Config
from brainiac.core.index import connect, index_note
from brainiac.core.note import write_note
from brainiac.core.paths import index_db_path, note_path
from tests.conftest import make_fm


def _seed_working(root: Path, note_id: str, access_count: int = 0, strength: float = 1.0) -> None:
    fm = make_fm(note_id=note_id, note_type="working", access_count=access_count, strength=strength)
    p = note_path(root, note_id, "working")
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(root))
    index_note(conn, fm, f"# {note_id}\n\nbody", str(p.relative_to(root)))


# --- working_count ---

def test_working_count_zero_for_empty(fake_brainiac):
    from brainiac.core.working_memory import working_count

    conn = connect(index_db_path(fake_brainiac))
    assert working_count(conn) == 0


def test_working_count_only_counts_type_working(fake_brainiac):
    from brainiac.core.working_memory import working_count

    _seed_working(fake_brainiac, "2026-05-20-w1")
    fm = make_fm("2026-05-20-s1", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-s1", "semantic")
    write_note(p, fm, "# s1\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# s1\n\nbody", str(p.relative_to(fake_brainiac)))

    assert working_count(conn) == 1


def test_working_count_excludes_archived(fake_brainiac):
    from brainiac.core.working_memory import working_count

    fm = make_fm("2026-05-20-arc", "working")
    p = note_path(fake_brainiac, "2026-05-20-arc", "working")
    write_note(p, fm, "# arc\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# arc\n\nbody", str(p.relative_to(fake_brainiac)), archived=True)

    assert working_count(conn) == 0


# --- candidates_for_eviction ---

def test_candidates_orders_by_access_count_desc(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    _seed_working(fake_brainiac, "2026-05-20-cold", access_count=0)
    _seed_working(fake_brainiac, "2026-05-20-hot", access_count=10)
    _seed_working(fake_brainiac, "2026-05-20-warm", access_count=3)

    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=3)
    ids = [c["id"] for c in cands]
    assert ids == ["2026-05-20-hot", "2026-05-20-warm", "2026-05-20-cold"]


def test_candidates_respects_limit(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    for i in range(5):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=2)
    assert len(cands) == 2


def test_candidates_returns_required_fields(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    _seed_working(fake_brainiac, "2026-05-20-fields", access_count=5, strength=0.7)
    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=5)
    assert len(cands) == 1
    c = cands[0]
    assert set(c.keys()) >= {"id", "path", "access_count", "strength"}


# --- check_working_capacity ---

def test_check_working_capacity_passes_when_below_limit(fake_brainiac):
    from brainiac.core.working_memory import check_working_capacity

    _seed_working(fake_brainiac, "2026-05-20-w1")
    conn = connect(index_db_path(fake_brainiac))
    # Does not raise
    check_working_capacity(conn, Config(working_memory_limit=9))


def test_check_working_capacity_raises_when_at_limit(fake_brainiac):
    from brainiac.core.working_memory import (
        WorkingMemoryFullError,
        check_working_capacity,
    )

    for i in range(3):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))

    with pytest.raises(WorkingMemoryFullError) as excinfo:
        check_working_capacity(conn, Config(working_memory_limit=3))
    err = excinfo.value
    assert err.count == 3
    assert err.limit == 3
    assert len(err.candidates) >= 1


# --- working_status ---

def test_working_status_reports_empty_state(fake_brainiac):
    from brainiac.core.working_memory import working_status

    conn = connect(index_db_path(fake_brainiac))
    status = working_status(conn, Config(working_memory_limit=9))
    assert status == {"count": 0, "limit": 9, "full": False, "candidates": []}


def test_working_status_reports_full_state_with_candidates(fake_brainiac):
    from brainiac.core.working_memory import working_status

    for i in range(3):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))
    status = working_status(conn, Config(working_memory_limit=3))
    assert status["count"] == 3
    assert status["limit"] == 3
    assert status["full"] is True
    assert len(status["candidates"]) == 3
