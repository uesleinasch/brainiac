import math
from datetime import datetime, timedelta, timezone

import pytest


# --- Pure function actr_activation ---

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_actr_activation_empty_events_returns_negative_infinity():
    from brainiac.core.activation import actr_activation
    assert actr_activation([], NOW) == float("-inf")


def test_actr_activation_single_event_one_hour_ago_returns_zero():
    from brainiac.core.activation import actr_activation
    # 1h ago, weight 1.0, d=0.5: ln(1.0 * 1^-0.5) = ln(1) = 0
    events = [(NOW - timedelta(hours=1), 1.0)]
    assert actr_activation(events, NOW) == pytest.approx(0.0, abs=1e-6)


def test_actr_activation_more_recent_event_higher_activation():
    from brainiac.core.activation import actr_activation
    a_recent = actr_activation([(NOW - timedelta(minutes=10), 1.0)], NOW)
    a_old = actr_activation([(NOW - timedelta(hours=10), 1.0)], NOW)
    assert a_recent > a_old


def test_actr_activation_weight_scales_contribution():
    from brainiac.core.activation import actr_activation
    e = NOW - timedelta(hours=1)
    a_full = actr_activation([(e, 1.0)], NOW)
    a_half = actr_activation([(e, 0.5)], NOW)
    # ln(1*1^-0.5) = 0, ln(0.5*1^-0.5) = ln(0.5) ≈ -0.693
    assert a_full == pytest.approx(0.0, abs=1e-6)
    assert a_half == pytest.approx(math.log(0.5), abs=1e-6)


def test_actr_activation_decay_constant_changes_persistence():
    from brainiac.core.activation import actr_activation
    e = NOW - timedelta(hours=24)
    a_d03 = actr_activation([(e, 1.0)], NOW, d=0.3)
    a_d07 = actr_activation([(e, 1.0)], NOW, d=0.7)
    # higher d → faster decay → lower activation for the same old event
    assert a_d03 > a_d07


def test_actr_activation_event_at_now_uses_epsilon_no_div_error():
    from brainiac.core.activation import actr_activation
    # ts == now should not raise; treated as Δt = epsilon
    a = actr_activation([(NOW, 1.0)], NOW)
    assert a > 0  # epsilon^-0.5 is very large; ln of it is positive


def test_actr_activation_very_old_events_dont_underflow():
    from brainiac.core.activation import actr_activation
    # 1 year ago — should produce a small positive number, not crash
    a = actr_activation([(NOW - timedelta(days=365), 1.0)], NOW)
    assert math.isfinite(a)
    assert a < 0  # very small contribution → negative log


def test_actr_activation_many_events_sum_correctly():
    from brainiac.core.activation import actr_activation
    events = [(NOW - timedelta(hours=i + 1), 1.0) for i in range(50)]
    a = actr_activation(events, NOW)
    # expected = ln(sum_{i=1..50} i^-0.5)
    expected = math.log(sum(i ** -0.5 for i in range(1, 51)))
    assert a == pytest.approx(expected, abs=1e-6)


def test_actr_activation_negative_delta_t_clamped_to_epsilon():
    from brainiac.core.activation import actr_activation
    # event in the "future" (clock skew) — treated as epsilon, not crash
    a = actr_activation([(NOW + timedelta(seconds=10), 1.0)], NOW)
    assert math.isfinite(a)


def test_actr_activation_recent_frequency_beats_single_recent():
    from brainiac.core.activation import actr_activation
    a_many = actr_activation(
        [(NOW - timedelta(hours=h), 1.0) for h in [1, 2, 3, 4, 5]],
        NOW,
    )
    a_single = actr_activation([(NOW - timedelta(hours=1), 1.0)], NOW)
    assert a_many > a_single
