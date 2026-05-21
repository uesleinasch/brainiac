from datetime import datetime, timedelta, timezone

import pytest


NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_add_sensory_inserts_with_generated_id(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="rascunho rápido", title="ideia", now=NOW)
    assert sid.startswith("sensory-")
    row = conn.execute(
        "SELECT body, title FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    assert row[0] == "rascunho rápido"
    assert row[1] == "ideia"


def test_add_sensory_sets_expires_at(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="x", now=NOW, ttl_minutes=10)
    row = conn.execute(
        "SELECT expires_at FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    expected = (NOW + timedelta(minutes=10)).isoformat()
    assert row[0] == expected


def test_list_sensory_excludes_expired_by_default(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, list_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid_fresh = add_sensory(conn, body="fresh", now=NOW, ttl_minutes=5)
    sid_old = add_sensory(conn, body="old", now=NOW - timedelta(minutes=30), ttl_minutes=5)

    fresh = list_sensory(conn, now=NOW)
    ids = {e["id"] for e in fresh}
    assert sid_fresh in ids
    assert sid_old not in ids


def test_list_sensory_includes_expired_when_flag(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, list_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid_old = add_sensory(conn, body="old", now=NOW - timedelta(minutes=30), ttl_minutes=5)
    all_items = list_sensory(conn, now=NOW, include_expired=True)
    ids = {e["id"] for e in all_items}
    assert sid_old in ids


def test_commit_sensory_creates_real_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.sensory import add_sensory, commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="# Title\n\nbody content", title="Title", now=NOW)
    final_id = commit_sensory(
        conn, fake_brainiac, sid, note_type="semantic", final_id="2026-05-20-committed"
    )
    assert final_id == "2026-05-20-committed"
    assert (fake_brainiac / "semanticMemory" / "2026-05-20-committed.md").exists()


def test_commit_sensory_deletes_buffer_entry(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="# x\n\nbody", title="x", now=NOW)
    commit_sensory(conn, fake_brainiac, sid, note_type="semantic", final_id="2026-05-20-c")
    row = conn.execute(
        "SELECT id FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    assert row is None


def test_commit_sensory_raises_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        commit_sensory(conn, fake_brainiac, "sensory-ghost", note_type="semantic", final_id="x")


def test_expire_sensory_deletes_old_entries(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, expire_sensory

    conn = connect(index_db_path(fake_brainiac))
    add_sensory(conn, body="fresh", now=NOW, ttl_minutes=5)
    add_sensory(conn, body="old1", now=NOW - timedelta(minutes=30), ttl_minutes=5)
    add_sensory(conn, body="old2", now=NOW - timedelta(minutes=60), ttl_minutes=5)

    deleted = expire_sensory(conn, now=NOW)
    assert deleted == 2

    remaining = conn.execute("SELECT COUNT(*) FROM sensory_buffer").fetchone()[0]
    assert remaining == 1


def test_get_sensory_returns_entry(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, get_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="body", title="t", now=NOW)
    entry = get_sensory(conn, sid)
    assert entry["id"] == sid
    assert entry["body"] == "body"
    assert entry["title"] == "t"


def test_get_sensory_returns_none_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import get_sensory

    conn = connect(index_db_path(fake_brainiac))
    assert get_sensory(conn, "sensory-ghost") is None
