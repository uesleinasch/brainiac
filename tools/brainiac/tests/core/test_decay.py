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
