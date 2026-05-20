import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from brainiac.core.index import connect
from brainiac.core.models import NoteFrontmatter


@pytest.fixture
def fake_brainiac(tmp_path: Path) -> Path:
    """Brainiac root with all memory dirs."""
    for d in ("shortMemory", "longMemory/episodic", "semanticMemory", "memoryTransfer"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def conn(fake_brainiac: Path) -> sqlite3.Connection:
    """Fresh SQLite connection with schema applied."""
    return connect(fake_brainiac / "memoryTransfer" / "index.sqlite")


def make_fm(
    note_id: str = "2026-05-20-test",
    note_type: str = "semantic",
    access_count: int = 0,
    strength: float = 1.0,
    tags: list[str] | None = None,
    links: list[str] | None = None,
) -> NoteFrontmatter:
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    return NoteFrontmatter(
        id=note_id,
        type=note_type,
        created=now,
        last_access=now,
        access_count=access_count,
        strength=strength,
        tags=tags or [],
        links=links or [],
    )


@pytest.fixture
def embedder_stub(monkeypatch):
    """Substitui embed_texts/embed_query por vetores determinísticos baseados em hash."""
    from brainiac.core import embeddings

    def fake_embed_texts(texts):
        out = np.zeros((len(texts), 384), dtype=np.float32)
        for i, t in enumerate(texts):
            h = hash(t) & 0xFFFFFFFF
            rng = np.random.default_rng(h)
            v = rng.standard_normal(384).astype(np.float32)
            v /= np.linalg.norm(v) + 1e-9
            out[i] = v
        return out

    def fake_embed_query(text):
        return fake_embed_texts([text])[0]

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(embeddings, "embed_query", fake_embed_query)
    monkeypatch.setattr(embeddings, "model_available", lambda: True)
