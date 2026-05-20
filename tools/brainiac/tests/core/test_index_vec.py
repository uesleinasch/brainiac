import re
import sqlite3

import sqlite_vec

from brainiac.core.index import connect, index_note, reindex_all
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

    n = reindex_all(conn, fake_brainiac)
    assert n == 2

    ids = {r[0] for r in conn.execute("SELECT id FROM notes_vec").fetchall()}
    assert ids == {"2026-05-20-a", "2026-05-20-b"}
