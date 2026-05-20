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
