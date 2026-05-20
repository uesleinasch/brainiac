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
