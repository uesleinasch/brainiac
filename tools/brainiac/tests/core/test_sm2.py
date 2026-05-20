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
