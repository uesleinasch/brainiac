import numpy as np

import sqlite_vec

from brainiac.core.graph import IMPLICIT_THRESHOLD, NEIGHBOR_DECAY, neighbors_of
from brainiac.core.index import connect, reindex_all
from brainiac.core.note import write_note
from tests.conftest import make_fm


def _seed(fake_brainiac, ids):
    for note_id in ids:
        fm = make_fm(note_id=note_id)
        write_note(
            fake_brainiac / "semanticMemory" / f"{note_id}.md",
            fm,
            f"# {note_id}\n\nbody",
        )


def test_constants_match_spec():
    assert IMPLICIT_THRESHOLD == 0.75
    assert NEIGHBOR_DECAY == 0.5


def test_neighbors_returns_explicit_links_with_kind(fake_brainiac, embedder_stub):
    _seed(fake_brainiac, ["2026-05-20-src", "2026-05-20-dst"])
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)
    conn.execute(
        "INSERT INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-20-src", "2026-05-20-dst"),
    )
    conn.commit()

    out = neighbors_of(conn, "2026-05-20-src")
    assert "2026-05-20-dst" in out
    assert out["2026-05-20-dst"]["kind"] == "explicit"
    assert out["2026-05-20-dst"]["weight"] == 1.0


def test_neighbors_returns_implicit_links_above_threshold(fake_brainiac, monkeypatch):
    """Força dois vetores quase idênticos para gerar similaridade > 0.75."""
    from brainiac.core import embeddings

    def fake_embed_texts(texts):
        # vetores próximos: todos iguais a v base, exceto perturbação pequena no "two"
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for i, t in enumerate(texts):
            v = np.full(384, 0.05, dtype=np.float32)
            if "two" in t:
                v[0] = 0.06  # leve perturbação
            v /= np.linalg.norm(v)
            out[i] = v
        return out

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embeddings, "embed_query", lambda t: fake_embed_texts([t])[0])
    monkeypatch.setattr(embeddings, "model_available", lambda: True)

    _seed(fake_brainiac, ["2026-05-20-one", "2026-05-20-two"])
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)

    out = neighbors_of(conn, "2026-05-20-one")
    assert "2026-05-20-two" in out
    assert out["2026-05-20-two"]["kind"] == "implicit"
    assert out["2026-05-20-two"]["weight"] >= IMPLICIT_THRESHOLD


def test_neighbors_explicit_wins_over_implicit_when_both(fake_brainiac, monkeypatch):
    from brainiac.core import embeddings

    def fake_embed_texts(texts):
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for i, _ in enumerate(texts):
            v = np.full(384, 0.05, dtype=np.float32)
            v[0] += 0.01 * i
            v /= np.linalg.norm(v)
            out[i] = v
        return out

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embeddings, "embed_query", lambda t: fake_embed_texts([t])[0])
    monkeypatch.setattr(embeddings, "model_available", lambda: True)

    _seed(fake_brainiac, ["2026-05-20-src", "2026-05-20-dst"])
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)
    conn.execute(
        "INSERT INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-20-src", "2026-05-20-dst"),
    )
    conn.commit()

    out = neighbors_of(conn, "2026-05-20-src")
    assert out["2026-05-20-dst"]["kind"] == "explicit"
