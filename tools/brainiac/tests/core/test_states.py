import pytest


def test_current_state_working_for_working_type(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-w", "working")
    p = note_path(fake_brainiac, "2026-05-20-w", "working")
    write_note(p, fm, "# w")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# w", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-w") == NoteState.WORKING


def test_current_state_long_term_for_semantic(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-s", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-s", "semantic")
    write_note(p, fm, "# s")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# s", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-s") == NoteState.LONG_TERM


def test_current_state_long_term_for_episodic(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-e", "episodic")
    p = note_path(fake_brainiac, "2026-05-20-e", "episodic")
    write_note(p, fm, "# e")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# e", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-e") == NoteState.LONG_TERM


def test_current_state_archived(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-a", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-a", "semantic")
    write_note(p, fm, "# a")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# a", str(p.relative_to(fake_brainiac)), archived=True)

    assert current_state(conn, "2026-05-20-a") == NoteState.ARCHIVED


def test_current_state_sensory_when_in_buffer(fake_brainiac):
    from datetime import datetime, timezone
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory
    from brainiac.core.states import NoteState, current_state

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="x", now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    assert current_state(conn, sid) == NoteState.SENSORY


def test_current_state_raises_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.states import current_state

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        current_state(conn, "2026-05-20-ghost-state")


def test_transition_working_to_long_term_succeeds(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-wlt", "working")
    p = note_path(fake_brainiac, "2026-05-20-wlt", "working")
    write_note(p, fm, "# wlt")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# wlt", str(p.relative_to(fake_brainiac)))

    new_state = transition_note(conn, fake_brainiac, "2026-05-20-wlt", NoteState.LONG_TERM)
    assert new_state == NoteState.LONG_TERM
    assert current_state(conn, "2026-05-20-wlt") == NoteState.LONG_TERM


def test_transition_working_to_archived_rejected(fake_brainiac):
    """Markov enforcement: can't skip from working directly to archived."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-wskip", "working")
    p = note_path(fake_brainiac, "2026-05-20-wskip", "working")
    write_note(p, fm, "# x")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# x", str(p.relative_to(fake_brainiac)))

    with pytest.raises(ValueError, match="invalid transition"):
        transition_note(conn, fake_brainiac, "2026-05-20-wskip", NoteState.ARCHIVED)


def test_transition_long_term_to_archived_succeeds(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-lta", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-lta", "semantic")
    write_note(p, fm, "# lta")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# lta", str(p.relative_to(fake_brainiac)))

    transition_note(conn, fake_brainiac, "2026-05-20-lta", NoteState.ARCHIVED)
    assert current_state(conn, "2026-05-20-lta") == NoteState.ARCHIVED


def test_transition_archived_to_long_term_resurrects(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-res", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-res", "semantic")
    write_note(p, fm, "# res")
    conn = connect(index_db_path(fake_brainiac))
    # Insert as archived
    index_note(conn, fm, "# res", str(p.relative_to(fake_brainiac)), archived=True)
    # Move file to archive dir to match
    import shutil
    archive_dir = fake_brainiac / "memoryTransfer" / "archive" / "2026"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(archive_dir / "2026-05-20-res.md"))
    # Fix path in DB
    conn.execute(
        "UPDATE notes SET path = ? WHERE id = ?",
        ("memoryTransfer/archive/2026/2026-05-20-res.md", "2026-05-20-res"),
    )
    conn.commit()

    assert current_state(conn, "2026-05-20-res") == NoteState.ARCHIVED
    transition_note(conn, fake_brainiac, "2026-05-20-res", NoteState.LONG_TERM)
    assert current_state(conn, "2026-05-20-res") == NoteState.LONG_TERM


def test_transition_creates_audit_event(fake_brainiac):
    import json
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-aud", "working")
    p = note_path(fake_brainiac, "2026-05-20-aud", "working")
    write_note(p, fm, "# aud")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# aud", str(p.relative_to(fake_brainiac)))

    transition_note(conn, fake_brainiac, "2026-05-20-aud", NoteState.LONG_TERM)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    transitions = [e for e in entries if e["action"] == "state_transition"]
    assert len(transitions) >= 1
    assert "working" in transitions[-1]["detail"]
    assert "long_term" in transitions[-1]["detail"]


def test_transition_probabilities_working_note(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import transition_probabilities
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-prob", "working")
    p = note_path(fake_brainiac, "2026-05-20-prob", "working")
    write_note(p, fm, "# prob")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# prob", str(p.relative_to(fake_brainiac)))

    result = transition_probabilities(conn, "2026-05-20-prob")
    assert result["current_state"] == "working"
    assert "long_term" in result["transitions"]
    assert 0.0 <= result["transitions"]["long_term"]["probability"] <= 1.0
    assert "reason" in result["transitions"]["long_term"]
