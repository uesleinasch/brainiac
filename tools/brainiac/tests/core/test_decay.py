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
