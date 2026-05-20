import re
import sqlite3

import pytest
import sqlite_vec

from brainiac.core.index import connect, index_note, recall, reindex_all, search_vec
from brainiac.core.note import write_note
from tests.conftest import make_fm


def test_connect_loads_sqlite_vec_and_creates_notes_vec(fake_brainiac):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    row = conn.execute("SELECT vec_version()").fetchone()
    assert re.match(r"^v\d+\.\d+", row[0])


def test_notes_vec_accepts_384_float_vector(fake_brainiac):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    payload = sqlite_vec.serialize_float32([0.1] * 384)
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        ("2026-05-20-x", payload),
    )
    n = conn.execute("SELECT COUNT(*) FROM notes_vec").fetchone()[0]
    assert n == 1


def test_index_note_persists_embedding(fake_brainiac, embedder_stub):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    fm = make_fm(note_id="2026-05-20-foo")
    index_note(conn, fm, "# Foo\n\nbody texto", "semanticMemory/2026-05-20-foo.md")
    n = conn.execute("SELECT COUNT(*) FROM notes_vec WHERE id = ?", (fm.id,)).fetchone()[0]
    assert n == 1


def test_index_note_skips_embed_when_body_hash_unchanged(fake_brainiac, embedder_stub, monkeypatch):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    fm = make_fm(note_id="2026-05-20-bar")
    body = "# Bar\n\noriginal"
    index_note(conn, fm, body, "semanticMemory/2026-05-20-bar.md")

    calls = {"n": 0}
    from brainiac.core import embeddings
    original = embeddings.embed_texts

    def counting(texts):
        calls["n"] += 1
        return original(texts)

    monkeypatch.setattr(embeddings, "embed_texts", counting)
    # mesma body → não deve re-embedar
    index_note(conn, fm, body, "semanticMemory/2026-05-20-bar.md")
    assert calls["n"] == 0
    # body diferente → deve re-embedar
    index_note(conn, fm, "# Bar\n\nALTERADA", "semanticMemory/2026-05-20-bar.md")
    assert calls["n"] == 1


def test_reindex_all_repopulates_notes_vec(fake_brainiac, embedder_stub):
    fm1 = make_fm(note_id="2026-05-20-a")
    fm2 = make_fm(note_id="2026-05-20-b")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md", fm1, "# A\n\ntexto a")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md", fm2, "# B\n\ntexto b")

    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    # populate stale data to ensure reindex clears it
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        ("stale-id", sqlite_vec.serialize_float32([0.0] * 384)),
    )
    conn.commit()

    active, _ = reindex_all(conn, fake_brainiac)
    assert active == 2

    ids = {r[0] for r in conn.execute("SELECT id FROM notes_vec").fetchall()}
    assert ids == {"2026-05-20-a", "2026-05-20-b"}


def test_search_vec_returns_topk_with_similarity(fake_brainiac, embedder_stub):
    fm_a = make_fm(note_id="2026-05-20-alpha")
    fm_b = make_fm(note_id="2026-05-20-beta")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-alpha.md", fm_a, "# Alpha\n\nalfa")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-beta.md", fm_b, "# Beta\n\nbeta")
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)

    results = search_vec(conn, "qualquer query", k=2)
    assert len(results) == 2
    for r in results:
        assert set(r.keys()) >= {"id", "path", "type", "title", "score"}
        assert -1.0 <= r["score"] <= 1.0
    # ordenação por score desc
    assert results[0]["score"] >= results[1]["score"]


def test_new_notes_have_archived_zero(fake_brainiac, embedder_stub):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    fm = make_fm(note_id="2026-05-20-new")
    index_note(conn, fm, "# New\n\nbody", "semanticMemory/2026-05-20-new.md")
    row = conn.execute("SELECT archived FROM notes WHERE id = ?", ("2026-05-20-new",)).fetchone()
    assert row[0] == 0


def test_archived_note_hidden_from_recall_by_default(fake_brainiac, embedder_stub):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    fm = make_fm(note_id="2026-05-20-arc")
    index_note(conn, fm, "# Arc\n\nbody archivado", "semanticMemory/2026-05-20-arc.md", archived=True)
    results = recall(conn, "archivado", k=5)
    assert all(r["id"] != "2026-05-20-arc" for r in results)


def test_archived_note_visible_with_include_archived(fake_brainiac, embedder_stub):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    fm = make_fm(note_id="2026-05-20-arc2")
    index_note(conn, fm, "# Arc2\n\narchivado visivel", "semanticMemory/2026-05-20-arc2.md", archived=True)
    results = recall(conn, "archivado visivel", k=5, include_archived=True)
    assert any(r["id"] == "2026-05-20-arc2" for r in results)


def test_reindex_all_indexes_archived_notes_from_archive_dir(fake_brainiac, embedder_stub):
    from brainiac.core.note import write_note
    archive_dir = fake_brainiac / "memoryTransfer" / "archive" / "2026"
    archive_dir.mkdir(parents=True)
    fm = make_fm(note_id="2026-05-20-old-arc")
    write_note(archive_dir / "2026-05-20-old-arc.md", fm, "# Old Arc\n\nconteudo")
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)
    row = conn.execute("SELECT archived FROM notes WHERE id = ?", ("2026-05-20-old-arc",)).fetchone()
    assert row is not None
    assert row[0] == 1


def test_recall_does_not_return_archived_neighbor_via_1hop(fake_brainiac, embedder_stub):
    """Archived note reached via 1-hop expansion must not appear in default recall."""
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")

    # Active seed note
    fm_seed = make_fm(note_id="2026-05-20-seed-active")
    index_note(conn, fm_seed, "# Seed\n\nbody seed content", "semanticMemory/2026-05-20-seed-active.md")

    # Archived neighbor that seed links to
    fm_arc = make_fm(note_id="2026-05-20-neighbor-arc")
    index_note(conn, fm_arc, "# Arc Neighbor\n\nbody seed content", "semanticMemory/2026-05-20-neighbor-arc.md", archived=True)

    # Add explicit link from seed → archived neighbor
    conn.execute(
        "INSERT OR IGNORE INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-20-seed-active", "2026-05-20-neighbor-arc"),
    )
    conn.commit()

    results = recall(conn, "seed content", k=10)
    result_ids = [r["id"] for r in results]
    assert "2026-05-20-seed-active" in result_ids  # seed appears
    assert "2026-05-20-neighbor-arc" not in result_ids  # archived neighbor excluded


def test_connect_creates_accesses_table(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accesses)").fetchall()]
    assert set(cols) == {"id", "note_id", "ts", "source", "weight"}


def test_connect_creates_accesses_index(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(accesses)").fetchall()]
    assert "idx_accesses_note_ts" in indexes


def test_connect_idempotent_on_existing_accesses_table(fake_brainiac):
    """Running connect() twice on the same DB must not raise."""
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    db_path = index_db_path(fake_brainiac)
    conn1 = connect(db_path)
    conn1.close()
    conn2 = connect(db_path)  # must not raise
    cols = [r[1] for r in conn2.execute("PRAGMA table_info(accesses)").fetchall()]
    assert "note_id" in cols


def test_accesses_source_check_constraint(fake_brainiac):
    import sqlite3
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO accesses (note_id, ts, source, weight) VALUES (?, ?, ?, ?)",
            ("2026-05-20-x", "2026-05-20T10:00:00+00:00", "bogus_source", 1.0),
        )
