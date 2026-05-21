import numpy as np
import pytest

from brainiac.core.index import connect, recall, reindex_all
from brainiac.core.note import write_note
from tests.conftest import make_fm


def _seed(root, ids):
    for note_id in ids:
        fm = make_fm(note_id=note_id)
        write_note(
            root / "semanticMemory" / f"{note_id}.md",
            fm,
            f"# {note_id}\n\nbody",
        )


def test_recall_returns_top_k_with_badge_semantic(fake_brainiac, embedder_stub):
    _seed(fake_brainiac, [f"2026-05-20-n{i}" for i in range(3)])
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)

    results = recall(conn, "qualquer", k=2)
    assert 1 <= len(results) <= 2
    for r in results:
        assert r["origin"] in {"semantic", "explicit", "implicit", "both"}
        assert "score" in r and "id" in r


def test_recall_expands_via_explicit_link_and_marks_badge(fake_brainiac, monkeypatch):
    from brainiac.core import embeddings

    def fake_embed_texts(texts):
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for i, t in enumerate(texts):
            v = np.zeros(384, dtype=np.float32)
            # each text gets its own axis → orthogonal → cosine ≈ 0
            axis = abs(hash(t)) % 384
            v[axis] = 1.0
            out[i] = v
        return out

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embeddings, "embed_query", lambda t: fake_embed_texts([t])[0])
    monkeypatch.setattr(embeddings, "model_available", lambda: True)

    _seed(fake_brainiac, ["2026-05-20-seed", "2026-05-20-friend", "2026-05-20-other"])
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    reindex_all(conn, fake_brainiac)
    conn.execute(
        "INSERT INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-20-seed", "2026-05-20-friend"),
    )
    conn.commit()

    # query vector will match "2026-05-20-seed" axis
    results = recall(conn, "2026-05-20-seed", k=5)
    by_id = {r["id"]: r for r in results}
    assert "2026-05-20-friend" in by_id
    assert by_id["2026-05-20-friend"]["origin"] in {"explicit", "both", "implicit"}


def test_recall_falls_back_to_fts_when_model_unavailable(fake_brainiac, monkeypatch):
    from brainiac.core import embeddings
    from brainiac.core import index as index_mod

    def boom(*args, **kwargs):
        raise RuntimeError("model not available")

    monkeypatch.setattr(embeddings, "embed_query", boom)
    monkeypatch.setattr(embeddings, "embed_texts", boom)
    monkeypatch.setattr(embeddings, "model_available", lambda: False)

    fm = make_fm(note_id="2026-05-20-fts")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-fts.md", fm, "# FTS\n\nbm25 ranking")
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    index_mod.index_note(conn, fm, "# FTS\n\nbm25 ranking", "semanticMemory/2026-05-20-fts.md")

    results = recall(conn, "bm25", k=5)
    assert any(r["id"] == "2026-05-20-fts" for r in results)
    assert all(r["origin"] == "fts" for r in results)
