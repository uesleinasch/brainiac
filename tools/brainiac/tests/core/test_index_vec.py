import re
import sqlite3

import sqlite_vec

from brainiac.core.index import connect


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
