from datetime import date, timedelta

import pytest

from brainiac.core.models import SM2


# --- start_sm2 ---

def test_start_sm2_defaults():
    from brainiac.core.sm2 import start_sm2
    today = date(2026, 5, 20)
    sm2 = start_sm2(today=today)
    assert sm2.ease == 2.5
    assert sm2.interval == 1
    assert sm2.reps == 0
    assert sm2.next_review == today


# --- grade pure function ---

def test_grade_rejects_out_of_range():
    from brainiac.core.sm2 import grade
    sm2 = SM2(next_review=date(2026, 5, 20))
    with pytest.raises(ValueError):
        grade(sm2, q=-1)
    with pytest.raises(ValueError):
        grade(sm2, q=6)


def test_grade_5_first_review_sets_interval_1_reps_1():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 20)
    sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=5, today=today)
    assert out.reps == 1
    assert out.interval == 1
    assert out.ease == pytest.approx(2.6, abs=1e-6)
    assert out.next_review == today + timedelta(days=1)


def test_grade_5_second_review_sets_interval_6_reps_2():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 21)
    sm2 = SM2(ease=2.6, interval=1, reps=1, next_review=today)
    out = grade(sm2, q=5, today=today)
    assert out.reps == 2
    assert out.interval == 6
    assert out.next_review == today + timedelta(days=6)


def test_grade_5_third_review_uses_new_ease_multiplier():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 27)
    sm2 = SM2(ease=2.6, interval=6, reps=2, next_review=today)
    out = grade(sm2, q=5, today=today)
    # new_ease = 2.6 + 0.1 = 2.7; interval = round(6 * 2.7) = 16
    assert out.reps == 3
    assert out.ease == pytest.approx(2.7, abs=1e-6)
    assert out.interval == 16
    assert out.next_review == today + timedelta(days=16)


def test_grade_0_resets_reps_and_interval():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.4, interval=16, reps=3, next_review=today)
    out = grade(sm2, q=0, today=today)
    assert out.reps == 0
    assert out.interval == 1
    # ease dropped: 2.4 + 0.1 - 5 * (0.08 + 5 * 0.02) = 2.4 + 0.1 - 0.9 = 1.6
    assert out.ease == pytest.approx(1.6, abs=1e-6)
    assert out.next_review == today + timedelta(days=1)


def test_grade_2_treated_as_failure():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.5, interval=6, reps=2, next_review=today)
    out = grade(sm2, q=2, today=today)
    assert out.reps == 0
    assert out.interval == 1
    # ease = 2.5 + 0.1 - 3*(0.08 + 3*0.02) = 2.6 - 0.42 = 2.18
    assert out.ease == pytest.approx(2.18, abs=1e-6)


def test_grade_3_passes_minimally():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=3, today=today)
    assert out.reps == 1  # success, reps++
    # ease: 2.5 + 0.1 - 2*(0.08+2*0.02) = 2.5 + 0.1 - 0.24 = 2.36
    assert out.ease == pytest.approx(2.36, abs=1e-6)


def test_ease_floor_at_1_3():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=1.3, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=0, today=today)
    assert out.ease == pytest.approx(1.3, abs=1e-6)  # floor holds


import json
from datetime import datetime, timezone
from pathlib import Path


def _seed(
    root: Path,
    note_id: str,
    note_type: str = "semantic",
    sm2: SM2 | None = None,
    access_count: int = 0,
) -> None:
    """Create a .md note + index, optionally with sm2 enrolled."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm(note_id=note_id, note_type=note_type, access_count=access_count)
    if sm2 is not None:
        fm.sm2 = sm2
    p = note_path(root, note_id, note_type)
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(root))
    index_note(conn, fm, f"# {note_id}\n\nbody", str(p.relative_to(root)))


# --- start_review ---

def test_start_review_enrolls_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.note import parse_note
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import start_review

    today = date(2026, 5, 20)
    _seed(fake_brainiac, "2026-05-20-study-me")
    conn = connect(index_db_path(fake_brainiac))
    sm2 = start_review(conn, fake_brainiac, "2026-05-20-study-me", today=today)

    assert sm2.next_review == today
    assert sm2.reps == 0
    p = fake_brainiac / "semanticMemory" / "2026-05-20-study-me.md"
    fm, _ = parse_note(p)
    assert fm.sm2 is not None
    assert fm.sm2.next_review == today


def test_start_review_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import start_review

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        start_review(conn, fake_brainiac, "2026-05-20-ghost")


# --- review_queue ---

def test_review_queue_empty_when_no_enrolled_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    _seed(fake_brainiac, "2026-05-20-not-enrolled")
    conn = connect(index_db_path(fake_brainiac))
    assert review_queue(conn, today=date(2026, 5, 20)) == []


def test_review_queue_returns_overdue_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    yesterday = date(2026, 5, 19)
    _seed(
        fake_brainiac,
        "2026-05-19-due",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=yesterday),
    )
    conn = connect(index_db_path(fake_brainiac))
    queue = review_queue(conn, today=today)
    assert len(queue) == 1
    assert queue[0]["id"] == "2026-05-19-due"
    assert queue[0]["days_overdue"] == 1


def test_review_queue_excludes_future_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    future = date(2026, 5, 25)
    _seed(
        fake_brainiac,
        "2026-05-25-future",
        sm2=SM2(ease=2.5, interval=5, reps=2, next_review=future),
    )
    conn = connect(index_db_path(fake_brainiac))
    assert review_queue(conn, today=today) == []


def test_review_queue_ordered_by_urgency_then_ease(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-15-old",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 15)),
    )
    _seed(
        fake_brainiac,
        "2026-05-19-hard",
        sm2=SM2(ease=1.5, interval=1, reps=0, next_review=date(2026, 5, 19)),
    )
    _seed(
        fake_brainiac,
        "2026-05-19-easy",
        sm2=SM2(ease=2.8, interval=1, reps=0, next_review=date(2026, 5, 19)),
    )
    conn = connect(index_db_path(fake_brainiac))
    queue = review_queue(conn, today=today)
    ids = [c["id"] for c in queue]
    # most overdue first, then within tie: lower ease first
    assert ids == ["2026-05-15-old", "2026-05-19-hard", "2026-05-19-easy"]


def test_review_queue_excludes_archived_notes(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.sm2 import review_queue
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    fm = make_fm("2026-05-19-arc", "semantic")
    fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
    p = note_path(fake_brainiac, "2026-05-19-arc", "semantic")
    write_note(p, fm, "# arc\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# arc\n\nbody", str(p.relative_to(fake_brainiac)), archived=True)
    assert review_queue(conn, today=today) == []


# --- grade_review ---

def test_grade_review_updates_sm2_in_frontmatter_and_db(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.note import parse_note
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-grade",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    new_sm2 = grade_review(conn, fake_brainiac, "2026-05-20-grade", q=5, today=today)

    assert new_sm2.reps == 1
    p = fake_brainiac / "semanticMemory" / "2026-05-20-grade.md"
    fm, _ = parse_note(p)
    assert fm.sm2.reps == 1
    assert fm.sm2.next_review == today + timedelta(days=1)


def test_grade_review_bumps_access_count_and_last_access(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-acc",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
        access_count=2,
    )
    conn = connect(index_db_path(fake_brainiac))
    grade_review(conn, fake_brainiac, "2026-05-20-acc", q=4, today=today)

    row = conn.execute(
        "SELECT access_count FROM notes WHERE id = ?", ("2026-05-20-acc",)
    ).fetchone()
    assert row[0] == 3


def test_grade_review_logs_reviewed_event(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-evt",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    grade_review(conn, fake_brainiac, "2026-05-20-evt", q=5, today=today)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    assert any(
        e["note_id"] == "2026-05-20-evt" and e["action"] == "reviewed"
        for e in entries
    )


def test_grade_review_raises_for_note_without_sm2(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(fake_brainiac, "2026-05-20-noenroll")  # no sm2
    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(ValueError):
        grade_review(conn, fake_brainiac, "2026-05-20-noenroll", q=5, today=today)


def test_grade_review_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        grade_review(conn, fake_brainiac, "2026-05-20-ghost", q=5)


def test_grade_review_rejects_invalid_grade(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-bad",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(ValueError):
        grade_review(conn, fake_brainiac, "2026-05-20-bad", q=7, today=today)


def test_start_review_raises_if_already_enrolled(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import start_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-double-enroll",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(ValueError):
        start_review(conn, fake_brainiac, "2026-05-20-double-enroll", today=today)
