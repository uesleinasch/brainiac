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


# --- I/O: record_access ---

def test_record_access_inserts_row_with_default_weight(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-a", "get", now=NOW)
    row = conn.execute(
        "SELECT note_id, source, weight FROM accesses WHERE note_id = ?",
        ("2026-05-20-a",),
    ).fetchone()
    assert row[0] == "2026-05-20-a"
    assert row[1] == "get"
    assert row[2] == 1.0


def test_record_access_respects_explicit_weight(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-b", "recall_hit", now=NOW, weight=0.75)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-b",)
    ).fetchone()
    assert row[0] == 0.75


def test_record_access_uses_config_weight_for_recall_hit(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    config = Config(actr_recall_hit_weight=0.42)
    record_access(conn, "2026-05-20-c", "recall_hit", now=NOW, config=config)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-c",)
    ).fetchone()
    assert row[0] == 0.42


def test_record_access_uses_config_weight_for_link_in(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    config = Config(actr_link_in_weight=0.65)
    record_access(conn, "2026-05-20-d", "link_in", now=NOW, config=config)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-d",)
    ).fetchone()
    assert row[0] == 0.65


def test_record_access_rejects_invalid_source(fake_brainiac):
    import sqlite3
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(sqlite3.IntegrityError):
        record_access(conn, "2026-05-20-e", "bogus", now=NOW)


# --- I/O: activation ---

def test_activation_zero_events_returns_neg_infinity(fake_brainiac):
    from brainiac.core.activation import activation
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    assert activation(conn, "2026-05-20-never", now=NOW) == float("-inf")


def test_activation_reads_full_history(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in [1, 2, 3]:
        record_access(conn, "2026-05-20-hist", "get", now=NOW - timedelta(hours=h))
    a = activation(conn, "2026-05-20-hist", now=NOW)
    expected = math.log(1.0 ** -0.5 + 2.0 ** -0.5 + 3.0 ** -0.5)
    assert a == pytest.approx(expected, abs=1e-6)


def test_activation_uses_config_decay(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-d2", "get", now=NOW - timedelta(hours=10))
    a_d03 = activation(conn, "2026-05-20-d2", now=NOW, config=Config(actr_decay=0.3))
    a_d07 = activation(conn, "2026-05-20-d2", now=NOW, config=Config(actr_decay=0.7))
    assert a_d03 > a_d07


def test_activation_now_injectable_for_determinism(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-det", "get", now=NOW - timedelta(hours=1))
    a1 = activation(conn, "2026-05-20-det", now=NOW)
    a2 = activation(conn, "2026-05-20-det", now=NOW)
    assert a1 == a2  # deterministic when now is fixed


# --- I/O: activation_batch ---

def test_activation_batch_single_query_results_match_individual_calls(fake_brainiac):
    from brainiac.core.activation import activation, activation_batch, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for note_id, hours in [("2026-05-20-a", [1, 5]), ("2026-05-20-b", [2]), ("2026-05-20-c", [10, 20, 30])]:
        for h in hours:
            record_access(conn, note_id, "get", now=NOW - timedelta(hours=h))

    batch = activation_batch(conn, ["2026-05-20-a", "2026-05-20-b", "2026-05-20-c"], now=NOW)
    for nid in ["2026-05-20-a", "2026-05-20-b", "2026-05-20-c"]:
        assert batch[nid] == pytest.approx(activation(conn, nid, now=NOW), abs=1e-9)


def test_activation_batch_handles_notes_without_events(fake_brainiac):
    from brainiac.core.activation import activation_batch
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    batch = activation_batch(conn, ["2026-05-20-no-events"], now=NOW)
    assert batch["2026-05-20-no-events"] == float("-inf")


def test_activation_batch_empty_input_returns_empty_dict(fake_brainiac):
    from brainiac.core.activation import activation_batch
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    assert activation_batch(conn, [], now=NOW) == {}


# --- I/O: access_history ---

def test_access_history_ordered_by_ts_desc(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in [5, 1, 3]:
        record_access(conn, "2026-05-20-h", "get", now=NOW - timedelta(hours=h))
    hist = access_history(conn, "2026-05-20-h")
    ts_values = [h["ts"] for h in hist]
    assert ts_values == sorted(ts_values, reverse=True)  # DESC


def test_access_history_respects_limit(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in range(20):
        record_access(conn, "2026-05-20-many", "get", now=NOW - timedelta(hours=h))
    hist = access_history(conn, "2026-05-20-many", limit=5)
    assert len(hist) == 5


def test_access_history_returns_required_fields(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-f", "review", now=NOW)
    hist = access_history(conn, "2026-05-20-f")
    assert len(hist) == 1
    assert set(hist[0].keys()) >= {"ts", "source", "weight"}
    assert hist[0]["source"] == "review"
