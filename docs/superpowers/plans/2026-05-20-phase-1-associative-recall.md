# Fase 1 — Recall Associativo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever `recall()` para busca semântica (embeddings 384-dim) + expansão 1-hop no grafo (links explícitos + implícitos por cosine ≥ 0.75), mantendo FTS5 como fallback.

**Architecture:** Modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` carregado lazy em `core/embeddings.py`. Vetores normalizados (L2) persistidos em `notes_vec` via `sqlite-vec`. `core/graph.py` calcula vizinhos (explícitos da tabela `links`; implícitos em runtime via cosine sobre `notes_vec`). `recall()` combina top-k semântico + expansão 1-hop com decay de peso 0.5 e devolve badge de origem por nota.

**Tech Stack:**
- `sentence-transformers>=2.7` (modelo multilingual, 384 dim, ~120MB)
- `sqlite-vec>=0.1` (virtual table `vec0`, distância cosine)
- `numpy>=1.26` (vetores e normalização)
- Pydantic 2, frontmatter, click, mcp — já em uso desde Fase 0

---

## Mapa de arquivos (Fase 1)

```
tools/brainiac/
├── pyproject.toml                          # MODIFY: deps
├── brainiac/
│   ├── core/
│   │   ├── embeddings.py                   # CREATE: model loader + embed_*()
│   │   ├── graph.py                        # CREATE: neighbors_of()
│   │   └── index.py                        # MODIFY: notes_vec schema, search_vec, recall
│   └── mcp_server.py                       # MODIFY: tool_recall devolve badges
└── tests/
    ├── conftest.py                         # MODIFY: fixture stub_embeddings + real model
    └── core/
        ├── test_embeddings.py              # CREATE
        ├── test_graph.py                   # CREATE
        ├── test_index_vec.py               # CREATE
        └── test_recall.py                  # CREATE

.claude/skills/brainiac-recall/SKILL.md     # MODIFY: documentar badges
docs/superpowers/plans/                     # (este arquivo)
tests/test_smoke_e2e.py                     # MODIFY: smoke DKG + perf budget
```

**Decisões arquiteturais (curtas):**

- **Normalização L2 + cosine distance**: embeddings normalizados pelo `sentence-transformers` (param `normalize_embeddings=True`). Em consultas usamos `vec_distance_cosine(...)` do sqlite-vec; `similarity = 1.0 - distance`.
- **`notes_vec` separado das outras tabelas**: virtual table `vec0` exige carga da extensão antes do `CREATE`. `connect()` carrega a extensão antes do `executescript(_SCHEMA)`.
- **Implicit links calculados em runtime**: o grafo persistente armazena só `kind='explicit'`. `neighbors_of()` faz uma consulta extra ao `notes_vec` para gerar vizinhos implícitos por seed.
- **Threshold de implicit = 0.75** (constante `IMPLICIT_THRESHOLD` em `core/graph.py`).
- **Decay de 1-hop = 0.5** (constante `NEIGHBOR_DECAY` em `core/graph.py`). Score do vizinho = `seed_score × NEIGHBOR_DECAY × link_weight`.
- **Badges**: cada item do resultado tem `origin ∈ {"semantic","explicit","implicit","both"}`. "both" quando aparece via mais de uma rota (semantic + algum link).
- **FTS5 fallback**: se `embed_texts()` levantar exceção (modelo ausente ou falha de carga), `recall()` captura, loga e cai para `search_fts()`. Resultado mantém schema (sem badges; `origin='fts'`).
- **Sem mocks de embeddings em integração**: testes de `embeddings.py`, `recall` e DoD usam o modelo real. Testes unitários de `graph.py` e `search_vec()` recebem vetores deterministicos via fixture.

---

## Task 1: Dependências + verificação de install

**Files:**
- Modify: `tools/brainiac/pyproject.toml`

- [ ] **Step 1: Atualizar pyproject.toml**

Editar o bloco `dependencies`:

```toml
dependencies = [
    "mcp>=1.0",
    "pydantic>=2",
    "python-frontmatter>=1.1",
    "click>=8",
    "sentence-transformers>=2.7",
    "sqlite-vec>=0.1.6",
    "numpy>=1.26",
]
```

- [ ] **Step 2: Reinstalar em modo editable**

Run:
```bash
cd tools/brainiac && .venv/bin/pip install -e ".[dev]"
```

Expected: install bem-sucedido. Primeira execução baixará torch + transformers (~500MB) — pode demorar alguns minutos.

- [ ] **Step 3: Smoke import**

Run:
```bash
cd tools/brainiac && .venv/bin/python -c "import sentence_transformers, sqlite_vec, numpy; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add tools/brainiac/pyproject.toml
git commit -m "feat(phase-1): add sentence-transformers, sqlite-vec, numpy deps"
```

---

## Task 2: `core/embeddings.py` — lazy loader + embed funcs

**Files:**
- Create: `tools/brainiac/brainiac/core/embeddings.py`
- Test: `tools/brainiac/tests/core/test_embeddings.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_embeddings.py`:

```python
import numpy as np
import pytest

from brainiac.core import embeddings


@pytest.mark.slow
def test_embed_query_returns_normalized_384dim():
    vec = embeddings.embed_query("teste em portugues")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32
    # normalized
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-4


@pytest.mark.slow
def test_embed_texts_batches_and_normalizes():
    vecs = embeddings.embed_texts(["hello", "olá", "criptografia"])
    assert vecs.shape == (3, 384)
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


@pytest.mark.slow
def test_semantic_similarity_pt_br():
    a = embeddings.embed_query("criação distribuída de chaves criptográficas")
    b = embeddings.embed_query("DKG protocol — distributed key generation")
    sim = float(np.dot(a, b))
    assert sim > 0.45  # >> overlap lexical (zero)


def test_model_available_returns_bool():
    assert isinstance(embeddings.model_available(), bool)
```

Adicionar marker `slow` em `tools/brainiac/pyproject.toml` na seção `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=brainiac --cov-report=term-missing"
markers = ["slow: tests que carregam o modelo de embeddings (>3s)"]
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_embeddings.py -v`
Expected: FAIL (`ImportError: cannot import name 'embeddings'`).

- [ ] **Step 3: Implementar `core/embeddings.py`**

Criar `tools/brainiac/brainiac/core/embeddings.py`:

```python
"""Sentence-transformers wrapper: lazy load, cache em memória, normalização L2."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Sequence

import numpy as np

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_DIM = 384

_logger = logging.getLogger(__name__)
_model = None
_load_failed = False
_lock = Lock()


def _get_model():
    """Lazy load do modelo. Em falha, marca _load_failed e propaga exceção."""
    global _model, _load_failed
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_MODEL_NAME)
            return _model
        except Exception as exc:
            _load_failed = True
            _logger.warning("embeddings: model load failed: %s", exc)
            raise


def model_available() -> bool:
    """True se o modelo já foi carregado com sucesso; False se nunca carregou ou falhou."""
    return _model is not None and not _load_failed


def embed_texts(texts: Sequence[str]) -> np.ndarray:
    """Embed batch. Retorna float32 (N, 384) normalizados."""
    model = _get_model()
    vecs = model.encode(
        list(texts),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vecs.astype(np.float32, copy=False)


def embed_query(text: str) -> np.ndarray:
    """Embed um único texto. Retorna float32 (384,) normalizado."""
    return embed_texts([text])[0]


def reset_for_tests() -> None:
    """Limpa o cache de modelo. Apenas para uso em testes."""
    global _model, _load_failed
    with _lock:
        _model = None
        _load_failed = False
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_embeddings.py -v`
Expected: 4 PASS. O primeiro teste leva ~3s (carga do modelo); subsequentes <100ms.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/embeddings.py tools/brainiac/tests/core/test_embeddings.py tools/brainiac/pyproject.toml
git commit -m "feat(phase-1): embeddings module — lazy load multilingual MiniLM"
```

---

## Task 3: Schema update — `notes_vec` + `connect()` carrega sqlite-vec

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Test: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Escrever teste failing**

Criar `tools/brainiac/tests/core/test_index_vec.py`:

```python
import sqlite3

import pytest

from brainiac.core.index import connect


def test_connect_loads_sqlite_vec_and_creates_notes_vec(fake_brainiac):
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    # vec_version() existe se sqlite-vec carregou
    row = conn.execute("SELECT vec_version()").fetchone()
    assert row[0].startswith("v0.")


def test_notes_vec_accepts_384_float_vector(fake_brainiac):
    import sqlite_vec
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    payload = sqlite_vec.serialize_float32([0.1] * 384)
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        ("2026-05-20-x", payload),
    )
    n = conn.execute("SELECT COUNT(*) FROM notes_vec").fetchone()[0]
    assert n == 1
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: FAIL (`no such function: vec_version` ou similar).

- [ ] **Step 3: Atualizar `core/index.py`**

No topo do arquivo, importar `sqlite_vec`:

```python
import sqlite_vec
```

Adicionar ao `_SCHEMA` (logo após a virtual table `notes_fts`):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0(
    id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
```

Substituir a função `connect()` por:

```python
def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection, load sqlite-vec, ensure schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Garantir que tests existentes continuam verdes**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index.py -v`
Expected: todos os testes Fase 0 do `index.py` PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-1): sqlite-vec extension + notes_vec virtual table"
```

---

## Task 4: `index_note()` — gera e persiste embedding (com skip por body_hash)

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Adicionar fixture `embedder_stub` em conftest**

Editar `tools/brainiac/tests/conftest.py`, adicionar no final:

```python
import numpy as np
import pytest


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
```

- [ ] **Step 2: Adicionar testes failing em test_index_vec.py**

Acrescentar ao arquivo `test_index_vec.py`:

```python
from brainiac.core.index import connect, index_note
from tests.conftest import make_fm


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
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: os 2 novos testes FAIL (embedding não populado).

- [ ] **Step 4: Atualizar `index_note()` em `core/index.py`**

Adicionar import no topo:

```python
from brainiac.core import embeddings
```

Adicionar helper antes de `index_note()`:

```python
def _existing_body_hash(conn: sqlite3.Connection, note_id: str) -> str | None:
    row = conn.execute("SELECT body_hash FROM notes WHERE id = ?", (note_id,)).fetchone()
    return row[0] if row else None


def _store_embedding(conn: sqlite3.Connection, note_id: str, title: str, body: str) -> None:
    import sqlite_vec
    text = f"{title}\n\n{body}" if title else body
    try:
        vec = embeddings.embed_query(text)
    except Exception:
        return  # fail-soft: índice vetorial fica desatualizado, FTS5 ainda funciona
    payload = sqlite_vec.serialize_float32(vec.tolist())
    conn.execute("DELETE FROM notes_vec WHERE id = ?", (note_id,))
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        (note_id, payload),
    )
```

Modificar `index_note()` — logo após `bh = _body_hash(body)`, antes do `INSERT OR REPLACE INTO notes`:

```python
    prev_hash = _existing_body_hash(conn, fm.id)
    needs_embed = prev_hash != bh
```

E logo antes do `conn.commit()` final, adicionar:

```python
    if needs_embed:
        _store_embedding(conn, fm.id, title, body)
```

- [ ] **Step 5: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Re-rodar suite Fase 0 para confirmar não-regressão**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index.py -v`
Expected: PASS (alguns testes podem agora invocar embeddings; o `embedder_stub` fixture só age quando aplicado, então testes Fase 0 podem ter falha de modelo. Se aparecer falha, adicionar `autouse=False` não é o caso aqui — preferimos tornar `_store_embedding` fail-soft, o que já fizemos via `except Exception: return`).

Re-rodar e validar.

- [ ] **Step 7: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/conftest.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-1): index_note persists embedding; skips when body unchanged"
```

---

## Task 5: `reindex_all()` — limpa e repopula `notes_vec`

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Adicionar teste failing**

Acrescentar ao `test_index_vec.py`:

```python
from brainiac.core.index import reindex_all
from brainiac.core.note import write_note
from tests.conftest import make_fm


def test_reindex_all_repopulates_notes_vec(fake_brainiac, embedder_stub):
    fm1 = make_fm(note_id="2026-05-20-a")
    fm2 = make_fm(note_id="2026-05-20-b")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md", fm1, "# A\n\ntexto a")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md", fm2, "# B\n\ntexto b")

    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    # popular com lixo pra garantir que reindex limpa
    import sqlite_vec
    conn.execute(
        "INSERT INTO notes_vec(id, embedding) VALUES (?, ?)",
        ("stale-id", sqlite_vec.serialize_float32([0.0] * 384)),
    )
    n = reindex_all(conn, fake_brainiac)
    assert n == 2

    ids = {r[0] for r in conn.execute("SELECT id FROM notes_vec").fetchall()}
    assert ids == {"2026-05-20-a", "2026-05-20-b"}
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py::test_reindex_all_repopulates_notes_vec -v`
Expected: FAIL (`stale-id` ainda presente).

- [ ] **Step 3: Atualizar `reindex_all()`**

Em `core/index.py`, modificar `reindex_all` — após `DELETE FROM links WHERE kind = 'explicit'` adicionar:

```python
    conn.execute("DELETE FROM notes_vec")
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: 5 PASS no arquivo.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-1): reindex_all clears notes_vec before repopulation"
```

---

## Task 6: `search_vec()` — top-k por cosine distance

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Adicionar teste failing**

Acrescentar ao `test_index_vec.py`:

```python
from brainiac.core.index import search_vec


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
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py::test_search_vec_returns_topk_with_similarity -v`
Expected: FAIL (`cannot import name 'search_vec'`).

- [ ] **Step 3: Implementar `search_vec`**

Em `core/index.py`, adicionar (logo após `search_fts`):

```python
def search_vec(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
) -> list[dict]:
    """Top-k semantic search via cosine distance over notes_vec."""
    import sqlite_vec
    qvec = embeddings.embed_query(query)
    payload = sqlite_vec.serialize_float32(qvec.tolist())
    rows = conn.execute(
        """
        SELECT n.id, n.path, n.type,
               coalesce((SELECT value FROM json_each(?)), '') as _unused,
               vec_distance_cosine(v.embedding, ?) as dist,
               (SELECT title FROM notes_fts f WHERE f.id = n.id) as title
        FROM notes_vec v JOIN notes n ON n.id = v.id
        ORDER BY dist ASC
        LIMIT ?
        """,
        ("[]", payload, k),
    ).fetchall()
    return [
        {
            "id": r[0], "path": r[1], "type": r[2],
            "title": r[5] or "",
            "score": float(1.0 - r[4]),
        }
        for r in rows
    ]
```

> Nota: a coluna `_unused` é um vestígio defensivo; remova-a se preferir — o SQL abaixo é equivalente e mais limpo:

```python
def search_vec(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
) -> list[dict]:
    """Top-k semantic search via cosine distance over notes_vec."""
    import sqlite_vec
    qvec = embeddings.embed_query(query)
    payload = sqlite_vec.serialize_float32(qvec.tolist())
    rows = conn.execute(
        """
        SELECT n.id, n.path, n.type,
               vec_distance_cosine(v.embedding, ?) as dist,
               (SELECT title FROM notes_fts f WHERE f.id = n.id) as title
        FROM notes_vec v JOIN notes n ON n.id = v.id
        ORDER BY dist ASC
        LIMIT ?
        """,
        (payload, k),
    ).fetchall()
    return [
        {
            "id": r[0], "path": r[1], "type": r[2],
            "title": r[4] or "",
            "score": float(1.0 - r[3]),
        }
        for r in rows
    ]
```

Use a forma limpa.

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-1): search_vec — top-k cosine via sqlite-vec"
```

---

## Task 7: `core/graph.py` — `neighbors_of()` (explícitos + implícitos)

**Files:**
- Create: `tools/brainiac/brainiac/core/graph.py`
- Test: `tools/brainiac/tests/core/test_graph.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_graph.py`:

```python
import sqlite_vec
import numpy as np

from brainiac.core.graph import IMPLICIT_THRESHOLD, NEIGHBOR_DECAY, neighbors_of
from brainiac.core.index import connect, index_note, reindex_all
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
        # vetores próximos: e1 e e2 = e1 + ruído pequeno (cosine ~ 0.99)
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
            v[0] += 0.01 * i  # pequenas diferenças
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
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_graph.py -v`
Expected: FAIL (`No module named 'brainiac.core.graph'`).

- [ ] **Step 3: Implementar `core/graph.py`**

Criar `tools/brainiac/brainiac/core/graph.py`:

```python
"""Grafo de notas: links explícitos (persistidos) + implícitos (cosine em runtime)."""

from __future__ import annotations

import sqlite3

import sqlite_vec

IMPLICIT_THRESHOLD: float = 0.75
NEIGHBOR_DECAY: float = 0.5


def _explicit_neighbors(conn: sqlite3.Connection, note_id: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT dst, weight FROM links WHERE src = ? AND kind = 'explicit'",
        (note_id,),
    ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def _implicit_neighbors(
    conn: sqlite3.Connection,
    note_id: str,
    threshold: float = IMPLICIT_THRESHOLD,
    limit: int = 20,
) -> dict[str, float]:
    row = conn.execute(
        "SELECT embedding FROM notes_vec WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        return {}
    payload = row[0]
    rows = conn.execute(
        """
        SELECT id, vec_distance_cosine(embedding, ?) as dist
        FROM notes_vec
        WHERE id != ?
        ORDER BY dist ASC
        LIMIT ?
        """,
        (payload, note_id, limit),
    ).fetchall()
    out: dict[str, float] = {}
    for rid, dist in rows:
        sim = 1.0 - float(dist)
        if sim >= threshold:
            out[rid] = sim
    return out


def neighbors_of(
    conn: sqlite3.Connection,
    note_id: str,
    threshold: float = IMPLICIT_THRESHOLD,
) -> dict[str, dict]:
    """Retorna mapa id → {kind, weight}. Explícitos prevalecem sobre implícitos."""
    expl = _explicit_neighbors(conn, note_id)
    impl = _implicit_neighbors(conn, note_id, threshold=threshold)
    out: dict[str, dict] = {}
    for dst, w in impl.items():
        out[dst] = {"kind": "implicit", "weight": w}
    for dst, w in expl.items():
        out[dst] = {"kind": "explicit", "weight": w}
    return out
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_graph.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/graph.py tools/brainiac/tests/core/test_graph.py
git commit -m "feat(phase-1): graph.neighbors_of — explicit + implicit (cosine ≥ 0.75)"
```

---

## Task 8: `recall()` — semantic + 1-hop + badges

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Create: `tools/brainiac/tests/core/test_recall.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_recall.py`:

```python
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
            # cada texto pega um eixo distinto → ortogonais → cosine ≈ 0
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

    # query coincide com vetor de "2026-05-20-seed"
    results = recall(conn, "2026-05-20-seed", k=5)
    by_id = {r["id"]: r for r in results}
    assert "2026-05-20-friend" in by_id
    assert by_id["2026-05-20-friend"]["origin"] in {"explicit", "both"}


def test_recall_falls_back_to_fts_when_model_unavailable(fake_brainiac, monkeypatch):
    from brainiac.core import embeddings, index as index_mod

    def boom(*args, **kwargs):
        raise RuntimeError("model not available")

    monkeypatch.setattr(embeddings, "embed_query", boom)
    monkeypatch.setattr(embeddings, "embed_texts", boom)
    monkeypatch.setattr(embeddings, "model_available", lambda: False)

    # popula via index_note com fail-soft (sem vec)
    fm = make_fm(note_id="2026-05-20-fts")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-fts.md", fm, "# FTS\n\nbm25 ranking")
    conn = connect(fake_brainiac / "memoryTransfer" / "index.sqlite")
    index_mod.index_note(conn, fm, "# FTS\n\nbm25 ranking", "semanticMemory/2026-05-20-fts.md")

    results = recall(conn, "bm25", k=5)
    assert any(r["id"] == "2026-05-20-fts" for r in results)
    assert all(r["origin"] == "fts" for r in results)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_recall.py -v`
Expected: FAIL (`cannot import name 'recall'`).

- [ ] **Step 3: Implementar `recall()` em `core/index.py`**

Adicionar import no topo (se ainda não houver):

```python
from brainiac.core.graph import NEIGHBOR_DECAY, neighbors_of
```

Adicionar função no final do arquivo:

```python
def recall(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
) -> list[dict]:
    """Recall associativo: semantic top-k + 1-hop expansion + badges.

    Em caso de falha do modelo de embeddings, faz fallback para FTS5 (sem badges,
    com origin='fts').
    """
    if not embeddings.model_available():
        # tentativa best-effort de carga; se também falhar, vai pro fallback
        try:
            embeddings.embed_query("warmup")
        except Exception:
            return _fallback_fts(conn, query, k)

    try:
        seeds = search_vec(conn, query, k=k)
    except Exception:
        return _fallback_fts(conn, query, k)

    # mapa id → resultado consolidado
    scored: dict[str, dict] = {}
    for s in seeds:
        scored[s["id"]] = {
            "id": s["id"],
            "path": s["path"],
            "type": s["type"],
            "title": s["title"],
            "score": float(s["score"]),
            "origin": "semantic",
        }

    # expansão 1-hop
    for s in seeds:
        seed_score = float(s["score"])
        for dst, meta in neighbors_of(conn, s["id"]).items():
            neighbor_score = seed_score * NEIGHBOR_DECAY * float(meta["weight"])
            if dst in scored:
                # já vinha do semantic — vira "both"
                if scored[dst]["origin"] == "semantic":
                    scored[dst]["origin"] = "both"
                scored[dst]["score"] = max(scored[dst]["score"], neighbor_score)
            else:
                row = conn.execute(
                    "SELECT path, type FROM notes WHERE id = ?", (dst,)
                ).fetchone()
                if row is None:
                    continue
                title_row = conn.execute(
                    "SELECT title FROM notes_fts WHERE id = ?", (dst,)
                ).fetchone()
                scored[dst] = {
                    "id": dst,
                    "path": row[0],
                    "type": row[1],
                    "title": title_row[0] if title_row else "",
                    "score": neighbor_score,
                    "origin": meta["kind"],
                }

    results = sorted(scored.values(), key=lambda r: r["score"], reverse=True)
    return results[:k]


def _fallback_fts(conn: sqlite3.Connection, query: str, k: int) -> list[dict]:
    out = []
    for r in search_fts(conn, query, k=k):
        out.append({
            "id": r["id"], "path": r["path"], "type": r["type"],
            "title": r["title"], "snippet": r.get("snippet", ""),
            "score": 0.0, "origin": "fts",
        })
    return out
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_recall.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Rodar suite completa para garantir não-regressão**

Run: `cd tools/brainiac && .venv/bin/pytest -v`
Expected: tudo verde (ou apenas testes marcados `slow` se filtrados).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_recall.py
git commit -m "feat(phase-1): recall — semantic + 1-hop expansion + origin badges"
```

---

## Task 9: MCP `tool_recall` devolve badges; descrição atualizada

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`

- [ ] **Step 1: Ler o teste existente para entender o padrão**

Run: `cat tools/brainiac/tests/test_mcp_server.py`

(Apenas para contexto — o agente que implementar deve usar Read.)

- [ ] **Step 2: Adicionar teste failing**

Acrescentar ao final de `tools/brainiac/tests/test_mcp_server.py`:

```python
def test_tool_recall_returns_origin_badge(fake_brainiac, embedder_stub, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))

    from brainiac.mcp_server import tool_add_note, tool_recall

    tool_add_note(
        note_id="2026-05-20-recall-mcp",
        note_type="semantic",
        title="DKG protocol",
        body="distributed key generation",
        tags=["crypto"],
    )
    results = tool_recall(query="DKG", k=3)
    assert len(results) >= 1
    assert all("origin" in r for r in results)
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v`
Expected: FAIL no novo teste (`'origin' not in r`).

- [ ] **Step 4: Atualizar `tool_recall` em `mcp_server.py`**

Substituir `tool_recall`:

```python
def tool_recall(query: str, k: int = 5) -> list[dict]:
    """Recall associativo (semantic + 1-hop) com fallback para FTS5."""
    from brainiac.core.index import recall
    root = find_root()
    conn = connect(index_db_path(root))
    return recall(conn, query, k=k)
```

Remover o import agora-não-usado de `search_fts` (mas manter se outros lugares do arquivo o usam — checar antes de remover).

Atualizar a descrição do Tool `recall` em `_list_tools()`:

```python
Tool(
    name="recall",
    description=(
        "Recall associativo: top-k semântico (embeddings 384-dim) + expansão 1-hop "
        "no grafo. Cada item retorna origin ∈ {semantic, explicit, implicit, both, fts}. "
        "FTS5 fica como fallback se o modelo de embeddings falhar."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
),
```

- [ ] **Step 5: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/tests/test_mcp_server.py
git commit -m "feat(phase-1): MCP recall tool — devolve origin badges"
```

---

## Task 10: Skill `brainiac-recall` — documentar badges

**Files:**
- Modify: `.claude/skills/brainiac-recall/SKILL.md`

- [ ] **Step 1: Reescrever `.claude/skills/brainiac-recall/SKILL.md`**

Substituir o conteúdo por:

```markdown
---
name: brainiac-recall
description: Busca no brainiac por uma query e sintetiza uma resposta contextual com as notas relevantes. Use quando o usuário pergunta sobre algo que ele provavelmente já registrou, ou pede explicitamente "veja no brainiac", "lembre o que sabemos sobre X".
---

# Brainiac Recall

Orquestra busca semântica + expansão no grafo + leitura das notas mais relevantes via MCP tools `recall` + `get_note`.

## Quando usar

- Usuário pergunta sobre tópico que ele provavelmente já anotou
- Usuário pede: "veja no brainiac", "o que sabemos sobre X", "lembra aquilo de..."
- Antes de explicar conceito que pode ter sido registrado anteriormente — vale checar

## Passos

1. **Chamar `recall(query, k=5)`** com a query em pt-BR. Receba lista de notas com `id`, `title`, `path`, `score`, `origin`.

2. **Interpretar `origin`**:
   - `semantic` — a nota veio diretamente do top-k por similaridade semântica
   - `explicit` — chegou pela expansão via link declarado pelo usuário
   - `implicit` — chegou pela expansão via similaridade ≥ 0.75 com alguma seed
   - `both` — apareceu por mais de uma rota (sinal forte de relevância)
   - `fts` — modelo de embeddings indisponível; fallback BM25 (sem badge associativo)

3. **Priorizar** notas com `origin ∈ {semantic, both}`; tratar `explicit`/`implicit` como contexto adjacente útil.

4. **Ler integralmente** via `get_note(note_id)` apenas as notas que parecem realmente relevantes ao snippet/título. `get_note` incrementa `access_count`.

5. **Sintetizar resposta**:
   - Cite cada nota usada por `id` (ex: "conforme anotado em `2026-05-20-bm25-ranking`...")
   - Mencione a origem quando relevante ("essa nota apareceu por similaridade implícita com X")
   - Se houver gaps, diga claramente — não invente

6. **Sugerir nota nova** se a resposta levou a um insight que vale persistir (handoff implícito para `brainiac-capture`).

## Quando não usar

- Pergunta sobre algo fora do escopo das notas do usuário ("qual a capital da França")
- Conversa puramente operacional (rodar comando, debugar erro local)

## Exemplo

Usuário: "lembra como funciona aquele algoritmo de ranking que vimos?"

Você:
1. `recall("algoritmo de ranking", k=5)` → `[{id: "2026-05-20-bm25-ranking", origin: "semantic", score: 0.62}, {id: "2026-05-20-tf-idf", origin: "implicit", score: 0.21}]`
2. `get_note("2026-05-20-bm25-ranking")` — leitura integral
3. Resposta: "Você anotou BM25 em `2026-05-20-bm25-ranking` (match semântico direto). A nota `2026-05-20-tf-idf` apareceu por similaridade implícita — pode ser contexto útil. BM25 é função de ranking probabilística que considera TF, comprimento do doc e IDF; é o default scoring do FTS5 do SQLite."
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/brainiac-recall/SKILL.md
git commit -m "feat(phase-1): skill brainiac-recall — documenta badges de origem"
```

---

## Task 11: Smoke E2E — DKG + perf budget

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: Ler smoke atual para entender padrão**

Run: `cat tools/brainiac/tests/test_smoke_e2e.py` (Read tool).

- [ ] **Step 2: Adicionar testes DoD**

Acrescentar ao final do arquivo:

```python
import time

import pytest


@pytest.mark.slow
def test_recall_finds_dkg_without_lexical_overlap(fake_brainiac, monkeypatch):
    """DoD: 'criação distribuída de chaves' recupera 'DKG protocol'."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_recall

    tool_add_note(
        note_id="2026-05-20-dkg",
        note_type="semantic",
        title="DKG protocol",
        body="distributed key generation; multi-party computation; threshold cryptography",
        tags=["crypto"],
    )
    # ruido
    tool_add_note(
        note_id="2026-05-20-mostarda",
        note_type="semantic",
        title="Receita de mostarda",
        body="sementes de mostarda, vinagre, sal",
        tags=["culinaria"],
    )
    results = tool_recall(query="criação distribuída de chaves criptográficas", k=3)
    assert any(r["id"] == "2026-05-20-dkg" for r in results)
    dkg = next(r for r in results if r["id"] == "2026-05-20-dkg")
    assert dkg["origin"] in {"semantic", "both"}


@pytest.mark.slow
def test_recall_latency_under_500ms_for_modest_corpus(fake_brainiac, monkeypatch):
    """DoD: recall < 500ms — usando corpus de 50 notas (proxy do budget de 1000)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_recall

    for i in range(50):
        tool_add_note(
            note_id=f"2026-05-20-perf-{i:02d}",
            note_type="semantic",
            title=f"Nota {i}",
            body=f"conteudo sintetico {i} sobre topico variado",
        )
    # warmup (carga do modelo já aconteceu nos add_note)
    tool_recall(query="warmup", k=5)

    t0 = time.perf_counter()
    tool_recall(query="topico variado", k=5)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500, f"recall took {elapsed_ms:.1f}ms"
```

- [ ] **Step 3: Rodar — esperar pass (com modelo real)**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_smoke_e2e.py -v -m slow`
Expected: 2 PASS. Primeira execução leva ~10s (carga do modelo + 50 embeddings).

- [ ] **Step 4: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest -v`
Expected: tudo verde.

- [ ] **Step 5: Conferir coverage Fase 1**

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.embeddings --cov=brainiac.core.graph --cov=brainiac.core.index --cov-report=term-missing`
Expected: cobertura ≥ 80% em `embeddings.py`, `graph.py` e `index.py`.

- [ ] **Step 6: Commit final da Fase 1**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-1): smoke E2E — DKG sem overlap lexical + perf budget"
```

---

## Definition of Done — Fase 1

Checklist final da spec (§5 Fase 1):

- [ ] Busca por "criação distribuída de chaves" recupera nota titulada "DKG protocol" sem overlap lexical (smoke test em Task 11)
- [ ] Resultado mostra badges de origem (`origin` no payload de `recall`)
- [ ] Geração de embedding < 200ms por nota em CPU (modelo MiniLM-L12: ~30ms/nota em CPU moderna)
- [ ] `recall` retorna em < 500ms para corpus de até 1000 notas (smoke test usa 50 como proxy; se passar com folga, está OK)
- [ ] Cobertura ≥ 80% em `embeddings.py`, `graph.py` e `index.py`

Após Fase 1 verde, gerar o plano da **Fase 2 — Consolidação + Decay** invocando novamente `superpowers:writing-plans`.
