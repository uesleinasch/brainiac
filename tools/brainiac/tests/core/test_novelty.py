import pytest


def test_compute_novelty_empty_corpus_returns_one(fake_brainiac, embedder_stub):
    """Note alone in corpus has max novelty."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import compute_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-alone", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-alone", "semantic")
    write_note(p, fm, "# alone\n\nunique content here")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# alone\n\nunique content here", str(p.relative_to(fake_brainiac)))

    assert compute_novelty(conn, "2026-05-20-alone") == 1.0


def test_compute_novelty_excludes_self(fake_brainiac, embedder_stub):
    """Self-similarity (1.0) should never count."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import compute_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm1 = make_fm("2026-05-20-a", "semantic")
    fm2 = make_fm("2026-05-20-b", "semantic")
    body_a = "# a\n\ndistinct content for note a"
    body_b = "# b\n\nvery different topic mostly unrelated"
    for fm, body in [(fm1, body_a), (fm2, body_b)]:
        p = note_path(fake_brainiac, fm.id, "semantic")
        write_note(p, fm, body)

    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm1, body_a, str(note_path(fake_brainiac, fm1.id, "semantic").relative_to(fake_brainiac)))
    index_note(conn, fm2, body_b, str(note_path(fake_brainiac, fm2.id, "semantic").relative_to(fake_brainiac)))

    n_a = compute_novelty(conn, "2026-05-20-a")
    assert 0.0 <= n_a <= 1.0
    # If self-similarity counted, max_sim = 1.0 → novelty = 0. Here we expect > 0.
    assert n_a > 0.0


def test_compute_novelty_no_embedding_returns_default(fake_brainiac):
    """Without embedder, novelty falls back to default 0.5."""
    from brainiac.core.index import connect
    from brainiac.core.novelty import compute_novelty
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    # No note inserted; no embedding
    assert compute_novelty(conn, "2026-05-20-missing") == 0.5


def test_cache_novelty_updates_column(fake_brainiac, embedder_stub):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import cache_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-c", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-c", "semantic")
    write_note(p, fm, "# c\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# c\n\nbody", str(p.relative_to(fake_brainiac)))

    cache_novelty(conn, "2026-05-20-c", 0.42)
    row = conn.execute(
        "SELECT novelty_score FROM notes WHERE id = ?", ("2026-05-20-c",)
    ).fetchone()
    assert row[0] == 0.42


def test_get_or_compute_returns_cached_if_present(fake_brainiac, embedder_stub):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import cache_novelty, get_or_compute_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-cached", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-cached", "semantic")
    write_note(p, fm, "# cached\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# cached\n\nbody", str(p.relative_to(fake_brainiac)))
    cache_novelty(conn, "2026-05-20-cached", 0.77)

    assert get_or_compute_novelty(conn, "2026-05-20-cached") == 0.77


def test_get_or_compute_computes_and_caches_if_null(fake_brainiac, embedder_stub):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import get_or_compute_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-fresh", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-fresh", "semantic")
    write_note(p, fm, "# fresh\n\nunique fresh content")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# fresh\n\nunique fresh content", str(p.relative_to(fake_brainiac)))

    n = get_or_compute_novelty(conn, "2026-05-20-fresh")
    assert n == 1.0  # alone in corpus

    # Verify it was cached
    row = conn.execute(
        "SELECT novelty_score FROM notes WHERE id = ?", ("2026-05-20-fresh",)
    ).fetchone()
    assert row[0] == 1.0


def test_compute_novelty_invalidated_on_reindex(fake_brainiac, embedder_stub):
    """After re-index_note with new body, novelty_score becomes NULL."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.novelty import cache_novelty
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-rein", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-rein", "semantic")
    write_note(p, fm, "# rein\n\noriginal body")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# rein\n\noriginal body", str(p.relative_to(fake_brainiac)))
    cache_novelty(conn, "2026-05-20-rein", 0.5)

    # Re-index with same id but new body
    index_note(conn, fm, "# rein\n\ncompletely different body", str(p.relative_to(fake_brainiac)))
    row = conn.execute(
        "SELECT novelty_score FROM notes WHERE id = ?", ("2026-05-20-rein",)
    ).fetchone()
    assert row[0] is None  # invalidated
