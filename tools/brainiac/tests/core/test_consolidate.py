import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from brainiac.core.index import connect, index_note
from brainiac.core.note import write_note
from brainiac.core.paths import index_db_path, note_path
from tests.conftest import make_fm


def _seed(
    root: Path,
    note_id: str,
    note_type: str = "working",
    access_count: int = 0,
    last_access: datetime | None = None,
    links_from: list[str] | None = None,
) -> None:
    """Create and index a note; optionally add incoming explicit links."""
    ts = last_access or datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    fm = make_fm(note_id=note_id, note_type=note_type,
                 access_count=access_count, last_access=ts)
    p = note_path(root, note_id, note_type)
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(root))
    rel = str(p.relative_to(root))
    index_note(conn, fm, f"# {note_id}\n\nbody", rel)

    if links_from:
        for src in links_from:
            conn.execute(
                "INSERT OR IGNORE INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
                (src, note_id),
            )
        conn.commit()


NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
RECENT = NOW - timedelta(days=3)
OLD = NOW - timedelta(days=10)


def test_consolidation_candidates_requires_working_type(fake_brainiac):
    from brainiac.core.consolidate import consolidation_candidates

    _seed(fake_brainiac, "2026-05-17-sem", "semantic",
          access_count=5, last_access=RECENT, links_from=["other-note"])
    conn = connect(index_db_path(fake_brainiac))
    candidates = consolidation_candidates(conn, now=NOW)
    assert all(c["id"] != "2026-05-17-sem" for c in candidates)


def test_consolidation_candidates_requires_access_count_ge_3(fake_brainiac):
    from brainiac.core.consolidate import consolidation_candidates

    _seed(fake_brainiac, "2026-05-17-low", "working",
          access_count=2, last_access=RECENT, links_from=["other"])
    conn = connect(index_db_path(fake_brainiac))
    candidates = consolidation_candidates(conn, now=NOW)
    assert all(c["id"] != "2026-05-17-low" for c in candidates)


def test_consolidation_candidates_requires_recent_access(fake_brainiac):
    from brainiac.core.consolidate import consolidation_candidates

    _seed(fake_brainiac, "2026-05-10-old", "working",
          access_count=5, last_access=OLD, links_from=["other"])
    conn = connect(index_db_path(fake_brainiac))
    candidates = consolidation_candidates(conn, now=NOW, window_days=7)
    assert all(c["id"] != "2026-05-10-old" for c in candidates)


def test_consolidation_candidates_requires_incoming_link(fake_brainiac):
    from brainiac.core.consolidate import consolidation_candidates

    _seed(fake_brainiac, "2026-05-17-nolink", "working",
          access_count=5, last_access=RECENT, links_from=[])
    conn = connect(index_db_path(fake_brainiac))
    candidates = consolidation_candidates(conn, now=NOW)
    assert all(c["id"] != "2026-05-17-nolink" for c in candidates)


def test_consolidation_candidates_returns_qualified_note(fake_brainiac):
    from brainiac.core.consolidate import consolidation_candidates

    _seed(fake_brainiac, "2026-05-17-good", "working",
          access_count=4, last_access=RECENT, links_from=["2026-05-17-other"])
    conn = connect(index_db_path(fake_brainiac))
    candidates = consolidation_candidates(conn, now=NOW)
    ids = [c["id"] for c in candidates]
    assert "2026-05-17-good" in ids
    good = next(c for c in candidates if c["id"] == "2026-05-17-good")
    assert set(good.keys()) >= {"id", "path", "access_count", "last_access", "fan_in", "suggested_type"}
    assert good["fan_in"] >= 1
    assert good["suggested_type"] in ("semantic", "episodic")


def test_promote_note_moves_file_to_target_dir(fake_brainiac):
    from brainiac.core.consolidate import promote_note

    _seed(fake_brainiac, "2026-05-17-promo", "working",
          access_count=4, last_access=RECENT)
    conn = connect(index_db_path(fake_brainiac))
    promote_note(conn, fake_brainiac, "2026-05-17-promo", "semantic", now=NOW)

    old_path = fake_brainiac / "shortMemory" / "2026-05-17-promo.md"
    new_path = fake_brainiac / "semanticMemory" / "2026-05-17-promo.md"
    assert not old_path.exists()
    assert new_path.exists()


def test_promote_note_updates_type_in_db(fake_brainiac):
    from brainiac.core.consolidate import promote_note

    _seed(fake_brainiac, "2026-05-17-type", "working",
          access_count=4, last_access=RECENT)
    conn = connect(index_db_path(fake_brainiac))
    promote_note(conn, fake_brainiac, "2026-05-17-type", "semantic", now=NOW)

    row = conn.execute("SELECT type FROM notes WHERE id = ?", ("2026-05-17-type",)).fetchone()
    assert row[0] == "semantic"


def test_promote_note_resets_strength_to_1(fake_brainiac):
    from brainiac.core.consolidate import promote_note

    fm = make_fm("2026-05-17-str", note_type="working",
                 access_count=4, last_access=RECENT, strength=0.5)
    p = note_path(fake_brainiac, "2026-05-17-str", "working")
    write_note(p, fm, "# str\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# str\n\nbody", str(p.relative_to(fake_brainiac)))

    promote_note(conn, fake_brainiac, "2026-05-17-str", "semantic", now=NOW)

    row = conn.execute("SELECT strength FROM notes WHERE id = ?", ("2026-05-17-str",)).fetchone()
    assert row[0] == pytest.approx(1.0)


def test_promote_note_logs_promoted_event(fake_brainiac):
    from brainiac.core.consolidate import promote_note

    _seed(fake_brainiac, "2026-05-17-log", "working",
          access_count=4, last_access=RECENT)
    conn = connect(index_db_path(fake_brainiac))
    promote_note(conn, fake_brainiac, "2026-05-17-log", "semantic", now=NOW)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    assert any(
        e["note_id"] == "2026-05-17-log" and e["action"] == "promoted"
        for e in entries
    )


def test_promote_note_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.consolidate import promote_note

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        promote_note(conn, fake_brainiac, "2026-05-17-ghost", "semantic")
