from __future__ import annotations

import math
from datetime import datetime

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
