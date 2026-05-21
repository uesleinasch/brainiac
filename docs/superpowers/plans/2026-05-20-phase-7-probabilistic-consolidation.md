# Fase 7 — Consolidação Probabilística Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um 3º caminho de consolidação baseado em `P(consolidar) = 1 − e^(−α·R·E·n)` que coexiste com Phase 2 (booleano) e Phase 5 (ACT-R borderline). Captura saliência emocional explícita (E) e novidade derivada de embeddings (n), permitindo promoção de notas importantes mesmo com baixo `access_count`.

**Architecture:** Schema ganha 2 colunas em `notes` (`emotional_weight`, `novelty_score`). Novo módulo `core/novelty.py` (compute + cache). `consolidate.py` ganha 3º path via union com cálculo de P. `NoteFrontmatter` ganha campo opcional `emotional_weight`. Skill `brainiac-capture` ganha passo opcional. Config ganha 2 fields. Sem novas deps pip.

**Tech Stack:** Python stdlib `math` + sqlite-vec (cosine_distance já em uso) + pydantic + existing brainiac.

---

## Mapa de arquivos

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── novelty.py            # CREATE
│   │   ├── config.py             # MODIFY: +2 fields
│   │   ├── models.py             # MODIFY: emotional_weight em NoteFrontmatter
│   │   ├── index.py              # MODIFY: connect() migration + index_note persiste emotional_weight
│   │   └── consolidate.py        # MODIFY: 3º caminho probabilístico
│   └── mcp_server.py             # MODIFY: tool_add_note aceita emotional_weight
└── tests/
    ├── core/
    │   ├── test_novelty.py       # CREATE
    │   ├── test_models.py        # MODIFY: emotional_weight tests
    │   ├── test_config.py        # MODIFY: 2 fields
    │   ├── test_index_vec.py     # MODIFY: schema migration
    │   └── test_consolidate.py   # MODIFY: probabilistic path tests
    ├── test_mcp_server.py        # MODIFY: tool_add_note com emotional_weight
    └── test_smoke_e2e.py         # MODIFY: 3 DoD tests

.claude/skills/brainiac-capture/SKILL.md  # MODIFY: passo opcional
```

---

## Task 1: Schema migration + Config 2 fields novos + NoteFrontmatter

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/brainiac/core/config.py`
- Modify: `tools/brainiac/brainiac/core/models.py`
- Modify: `tools/brainiac/tests/core/test_config.py`
- Modify: `tools/brainiac/tests/core/test_models.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Testes failing**

Em `tools/brainiac/tests/core/test_config.py`:

```python
def test_config_has_consolidation_learning_rate_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.consolidation_learning_rate == 0.5


def test_config_has_consolidation_probability_threshold_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.consolidation_probability_threshold == 0.6
```

Em `tools/brainiac/tests/core/test_models.py`:

```python
def test_note_frontmatter_emotional_weight_default():
    from datetime import datetime, timezone
    from brainiac.core.models import NoteFrontmatter
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    fm = NoteFrontmatter(
        id="2026-05-20-ew", type="semantic", created=now, last_access=now,
        access_count=0, strength=1.0,
    )
    assert fm.emotional_weight == 0.5


def test_note_frontmatter_accepts_explicit_emotional_weight():
    from datetime import datetime, timezone
    from brainiac.core.models import NoteFrontmatter
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    fm = NoteFrontmatter(
        id="2026-05-20-ew2", type="semantic", created=now, last_access=now,
        access_count=0, strength=1.0, emotional_weight=0.9,
    )
    assert fm.emotional_weight == 0.9


def test_note_frontmatter_rejects_emotional_weight_out_of_range():
    import pytest
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from brainiac.core.models import NoteFrontmatter
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        NoteFrontmatter(
            id="2026-05-20-ew3", type="semantic", created=now, last_access=now,
            access_count=0, strength=1.0, emotional_weight=1.5,
        )
```

Em `tools/brainiac/tests/core/test_index_vec.py`:

```python
def test_connect_adds_emotional_weight_column(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    conn = connect(index_db_path(fake_brainiac))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()]
    assert "emotional_weight" in cols


def test_connect_adds_novelty_score_column(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    conn = connect(index_db_path(fake_brainiac))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()]
    assert "novelty_score" in cols
```

- [ ] **Step 2: Rodar — fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py tests/core/test_models.py tests/core/test_index_vec.py -v --no-cov -k "consolidation or emotional_weight or novelty_score"`
Expected: FAIL.

- [ ] **Step 3: Adicionar fields em Config**

Em `tools/brainiac/brainiac/core/config.py`, adicionar 2 fields:

```python
@dataclass(frozen=True)
class Config:
    # ... existing fields ...
    # Probabilistic consolidation (Phase 7)
    consolidation_learning_rate: float = 0.5
    consolidation_probability_threshold: float = 0.6
```

- [ ] **Step 4: Adicionar field em NoteFrontmatter**

Em `tools/brainiac/brainiac/core/models.py`, adicionar ao final da classe `NoteFrontmatter`:

```python
    emotional_weight: float = Field(default=0.5, ge=0.0, le=1.0)
```

- [ ] **Step 5: Migration em `connect()`**

Em `tools/brainiac/brainiac/core/index.py`, após o bloco que adiciona `archived`, acrescentar:

```python
    # Phase 7: emotional_weight + novelty_score
    try:
        conn.execute("ALTER TABLE notes ADD COLUMN emotional_weight REAL NOT NULL DEFAULT 0.5")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE notes ADD COLUMN novelty_score REAL")
        conn.commit()
    except sqlite3.OperationalError:
        pass
```

- [ ] **Step 6: Persistir `emotional_weight` em `index_note()`**

Em `index_note()`, atualizar o INSERT OR REPLACE para incluir a nova coluna. Localizar:

```python
    conn.execute(
        """
        INSERT OR REPLACE INTO notes
        (id, path, type, created, last_access, access_count, strength,
         tags, sm2_json, body_hash, archived)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (...)
    )
```

Substituir por:

```python
    conn.execute(
        """
        INSERT OR REPLACE INTO notes
        (id, path, type, created, last_access, access_count, strength,
         tags, sm2_json, body_hash, archived, emotional_weight, novelty_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            fm.id, rel_path, fm.type,
            fm.created.isoformat(), fm.last_access.isoformat(),
            fm.access_count, fm.strength,
            json.dumps(fm.tags),
            fm.sm2.model_dump_json() if fm.sm2 else None,
            bh,
            1 if archived else 0,
            fm.emotional_weight,
        ),
    )
```

(Nota: `novelty_score` é setado para NULL na re-index — invalidação automática quando body muda.)

- [ ] **Step 7: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py tests/core/test_models.py tests/core/test_index_vec.py -v --no-cov`
Expected: PASS.

- [ ] **Step 8: Suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS sem regressões.

- [ ] **Step 9: Commit**

```bash
git add tools/brainiac/brainiac/core/config.py tools/brainiac/brainiac/core/models.py tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_config.py tools/brainiac/tests/core/test_models.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-7): schema emotional_weight + novelty_score + Config 2 fields + NoteFrontmatter"
```

---

## Task 2: `core/novelty.py` — compute + cache

**Files:**
- Create: `tools/brainiac/brainiac/core/novelty.py`
- Create: `tools/brainiac/tests/core/test_novelty.py`

- [ ] **Step 1: Testes failing**

Criar `tools/brainiac/tests/core/test_novelty.py`:

```python
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
```

- [ ] **Step 2: Rodar — fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_novelty.py -v --no-cov`
Expected: FAIL.

- [ ] **Step 3: Implementar `core/novelty.py`**

Criar `tools/brainiac/brainiac/core/novelty.py`:

```python
from __future__ import annotations

import sqlite3

import sqlite_vec

_DEFAULT_NOVELTY = 0.5  # used when no embedding is available


def compute_novelty(conn: sqlite3.Connection, note_id: str) -> float:
    """1 - max(cosine_similarity) with top-3 nearest neighbors, excluding self.

    Returns 1.0 if corpus has no other notes; 0.5 if note has no embedding.
    Bounded to [0.0, 1.0].
    """
    # Get the note's embedding
    emb_row = conn.execute(
        "SELECT embedding FROM notes_vec WHERE id = ?", (note_id,)
    ).fetchone()
    if emb_row is None:
        return _DEFAULT_NOVELTY

    embedding = emb_row[0]

    # Find top-3 nearest neighbors (cosine distance), excluding self
    rows = conn.execute(
        """
        SELECT vec_distance_cosine(embedding, ?) as dist
        FROM notes_vec
        WHERE id != ?
        ORDER BY dist ASC
        LIMIT 3
        """,
        (embedding, note_id),
    ).fetchall()

    if not rows:
        return 1.0  # alone in corpus

    min_dist = min(r[0] for r in rows)  # closest neighbor
    max_sim = 1.0 - min_dist  # cosine_sim = 1 - cosine_dist
    novelty = 1.0 - max_sim
    return max(0.0, min(1.0, novelty))


def cache_novelty(conn: sqlite3.Connection, note_id: str, value: float) -> None:
    """UPDATE notes SET novelty_score = ? WHERE id = ?"""
    conn.execute(
        "UPDATE notes SET novelty_score = ? WHERE id = ?",
        (value, note_id),
    )
    conn.commit()


def get_or_compute_novelty(conn: sqlite3.Connection, note_id: str) -> float:
    """Read from cache; if NULL, compute and cache."""
    row = conn.execute(
        "SELECT novelty_score FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is not None and row[0] is not None:
        return float(row[0])

    n = compute_novelty(conn, note_id)
    if row is not None:  # note exists in DB
        cache_novelty(conn, note_id, n)
    return n
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_novelty.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/novelty.py tools/brainiac/tests/core/test_novelty.py
git commit -m "feat(phase-7): novelty.py — compute + cache cosine-distance novelty"
```

---

## Task 3: Probabilistic path em `consolidate.py`

**Files:**
- Modify: `tools/brainiac/brainiac/core/consolidate.py`
- Modify: `tools/brainiac/tests/core/test_consolidate.py`

- [ ] **Step 1: Testes failing**

Acrescentar ao final de `test_consolidate.py`:

```python
def test_consolidation_candidates_includes_high_probability_note(fake_brainiac):
    """R=5 + E=0.9 + n=0.9 → P≈0.87 ≥ 0.6 → candidato."""
    from datetime import datetime, timedelta, timezone
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    # access_count=5, emotional_weight=0.9, novelty=0.9 (cached)
    _seed(fake_brainiac, "2026-05-18-prob-hi", "working",
          access_count=5, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    conn.execute(
        "UPDATE notes SET emotional_weight = 0.9 WHERE id = ?",
        ("2026-05-18-prob-hi",),
    )
    cache_novelty(conn, "2026-05-18-prob-hi", 0.9)

    candidates = consolidation_candidates(conn, now=now)
    ids = [c["id"] for c in candidates]
    assert "2026-05-18-prob-hi" in ids


def test_consolidation_candidates_excludes_low_probability_note(fake_brainiac):
    """R=1 + E=0.5 + n=0.5 → P≈0.06 < 0.6 → não candidato pelo path probabilístico."""
    from datetime import datetime, timedelta, timezone
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    _seed(fake_brainiac, "2026-05-18-prob-lo", "working",
          access_count=1, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    cache_novelty(conn, "2026-05-18-prob-lo", 0.5)
    # emotional_weight defaults to 0.5

    candidates = consolidation_candidates(conn, now=now)
    ids = [c["id"] for c in candidates]
    assert "2026-05-18-prob-lo" not in ids


def test_consolidation_candidates_includes_probability_field(fake_brainiac):
    from datetime import datetime, timedelta, timezone
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    _seed(fake_brainiac, "2026-05-18-prob-field", "working",
          access_count=5, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    conn.execute(
        "UPDATE notes SET emotional_weight = 1.0 WHERE id = ?",
        ("2026-05-18-prob-field",),
    )
    cache_novelty(conn, "2026-05-18-prob-field", 1.0)

    candidates = consolidation_candidates(conn, now=now)
    cand = next((c for c in candidates if c["id"] == "2026-05-18-prob-field"), None)
    assert cand is not None
    assert "consolidation_probability" in cand
    assert 0.0 <= cand["consolidation_probability"] <= 1.0
```

- [ ] **Step 2: Rodar — fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_consolidate.py -v --no-cov -k "probability"`
Expected: FAIL.

- [ ] **Step 3: Modificar `consolidation_candidates`**

Em `tools/brainiac/brainiac/core/consolidate.py`, modificar `consolidation_candidates` para adicionar o 3º path. Após o block borderline (Phase 5), antes do `return out`, acrescentar:

```python
    # Phase 7: probabilistic path
    import math
    from brainiac.core.config import load_config
    from brainiac.core.novelty import get_or_compute_novelty
    from brainiac.core.paths import find_root

    config = load_config(find_root()) if find_root() else None
    # Defensive: use defaults if config can't be loaded
    if config is None:
        from brainiac.core.config import Config
        config = Config()

    prob_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               n.emotional_weight, COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.last_access >= ?
        GROUP BY n.id
        """,
        (cutoff,),
    ).fetchall()

    for r in prob_rows:
        nid = r[0]
        if nid in seen:
            continue
        R = r[2]  # access_count
        E = r[4]  # emotional_weight
        n_score = get_or_compute_novelty(conn, nid)
        alpha = config.consolidation_learning_rate
        p = 1.0 - math.exp(-alpha * R * E * n_score)
        if p >= config.consolidation_probability_threshold:
            out.append({
                "id": nid,
                "path": r[1],
                "access_count": R,
                "last_access": r[3],
                "fan_in": r[5],
                "suggested_type": "semantic",
                "consolidation_probability": p,
            })
            seen.add(nid)
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_consolidate.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/consolidate.py tools/brainiac/tests/core/test_consolidate.py
git commit -m "feat(phase-7): consolidate probabilistic path — P = 1 - exp(-α·R·E·n)"
```

---

## Task 4: MCP `tool_add_note` aceita `emotional_weight` + skill update

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`
- Modify: `.claude/skills/brainiac-capture/SKILL.md`

- [ ] **Step 1: Teste failing**

Acrescentar ao final de `test_mcp_server.py`:

```python
def test_tool_add_note_accepts_emotional_weight(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.note import parse_note
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-ew-mcp", note_type="semantic",
        title="x", body="# x\n\nbody",
        emotional_weight=0.85,
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-ew-mcp.md")
    assert fm.emotional_weight == 0.85


def test_tool_add_note_emotional_weight_defaults_to_0_5(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.note import parse_note
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-ew-def", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-ew-def.md")
    assert fm.emotional_weight == 0.5
```

- [ ] **Step 2: Rodar — fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov -k "emotional_weight"`
Expected: FAIL.

- [ ] **Step 3: Modificar `tool_add_note`**

Em `mcp_server.py`, atualizar signature + body:

```python
def tool_add_note(
    note_id: str,
    note_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    study: bool = False,
    emotional_weight: float = 0.5,
) -> dict:
    """Create a new note. emotional_weight ∈ [0,1] influences consolidation probability."""
    root = find_root()

    if note_type == "working":
        # ... existing capacity check ...

    fm = new_note(note_id=note_id, note_type=note_type, tags=tags or [])
    fm = fm.model_copy(update={"emotional_weight": emotional_weight})

    # ... rest unchanged ...
```

E atualizar `_list_tools()` entry de `add_note` para incluir `emotional_weight` no schema:

```python
        Tool(
            name="add_note",
            description=...,
            inputSchema={
                "type": "object",
                "properties": {
                    # ... existing ...
                    "emotional_weight": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.5},
                },
                "required": [...],
            },
        ),
```

- [ ] **Step 4: Atualizar skill `brainiac-capture`**

Em `.claude/skills/brainiac-capture/SKILL.md`, após o passo `study`, acrescentar:

```markdown
6. **Saliência emocional (opcional)**:
   - Para captures rotineiras, NÃO pergunte — apenas use default 0.5.
   - Se o usuário sinalizar importância especial ("isso é crítico", "muito importante"), pergunte:
     "Essa nota é especialmente importante para você? (baixo/médio/alto/crítico)"
   - Mapeie: baixo → 0.3, médio → 0.5 (default), alto → 0.8, crítico → 1.0
   - Passe `emotional_weight=<valor>` para `add_note` quando ≠ 0.5
```

- [ ] **Step 5: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/tests/test_mcp_server.py .claude/skills/brainiac-capture/SKILL.md
git commit -m "feat(phase-7): MCP add_note emotional_weight + skill capture passo opcional"
```

---

## Task 5: Smoke E2E DoD + cobertura

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: 3 testes DoD**

Acrescentar ao final:

```python
# --- DoD Phase 7 ---


def test_high_emotional_weight_amplifies_consolidation_probability(fake_brainiac, monkeypatch):
    """DoD: high E + high n + medium R → P alta o suficiente para promover."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import datetime, timedelta, timezone
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty
    from tests.core.test_consolidate import _seed

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    # Low E (default 0.5): R=3 + E=0.5 + n=0.5 → P=0.31, not promoted
    _seed(fake_brainiac, "2026-05-18-low-e", "working",
          access_count=3, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    cache_novelty(conn, "2026-05-18-low-e", 0.5)

    # High E: R=3 + E=0.9 + n=0.9 → P=0.71, promoted
    _seed(fake_brainiac, "2026-05-18-high-e", "working",
          access_count=3, last_access=recent)
    conn.execute(
        "UPDATE notes SET emotional_weight = 0.9 WHERE id = ?",
        ("2026-05-18-high-e",),
    )
    cache_novelty(conn, "2026-05-18-high-e", 0.9)

    candidates = consolidation_candidates(conn, now=now)
    ids = [c["id"] for c in candidates]
    assert "2026-05-18-high-e" in ids
    assert "2026-05-18-low-e" not in ids


def test_novel_note_higher_probability_than_redundant(fake_brainiac, monkeypatch):
    """DoD: 2 notas mesmo R e E; novel tem P maior."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import datetime, timedelta, timezone
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty
    from tests.core.test_consolidate import _seed

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    _seed(fake_brainiac, "2026-05-18-novel", "working", access_count=5, last_access=recent)
    _seed(fake_brainiac, "2026-05-18-redundant", "working", access_count=5, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    for nid in ["2026-05-18-novel", "2026-05-18-redundant"]:
        conn.execute(
            "UPDATE notes SET emotional_weight = 0.9 WHERE id = ?", (nid,),
        )
    cache_novelty(conn, "2026-05-18-novel", 0.9)
    cache_novelty(conn, "2026-05-18-redundant", 0.1)

    candidates = consolidation_candidates(conn, now=now)
    novel_cand = next((c for c in candidates if c["id"] == "2026-05-18-novel"), None)
    redundant_cand = next((c for c in candidates if c["id"] == "2026-05-18-redundant"), None)

    assert novel_cand is not None
    # Redundant has very low novelty → P ≈ 0.20, below 0.6 threshold
    assert redundant_cand is None


def test_consolidate_check_returns_probability_via_mcp(fake_brainiac, monkeypatch):
    """DoD: tool_consolidate_check propaga consolidation_probability quando vem do prob path."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import datetime, timedelta, timezone
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty
    from brainiac.mcp_server import tool_consolidate_check
    from tests.core.test_consolidate import _seed

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    _seed(fake_brainiac, "2026-05-18-mcp-prob", "working",
          access_count=5, last_access=recent)
    conn = connect(index_db_path(fake_brainiac))
    conn.execute(
        "UPDATE notes SET emotional_weight = 1.0 WHERE id = ?",
        ("2026-05-18-mcp-prob",),
    )
    cache_novelty(conn, "2026-05-18-mcp-prob", 1.0)

    candidates = tool_consolidate_check()
    cand = next((c for c in candidates if c["id"] == "2026-05-18-mcp-prob"), None)
    assert cand is not None
    assert "consolidation_probability" in cand
```

- [ ] **Step 2: Pass + cobertura**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS.

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.novelty --cov-report=term --ignore=tests/core/test_embeddings.py 2>&1 | tail -5`
Expected: `novelty.py` ≥ 95%.

- [ ] **Step 3: Commit**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-7): smoke E2E DoD — emotional + novelty amplify consolidation"
```

---

## Definition of Done — Fase 7

- [ ] Schema migration idempotente (emotional_weight + novelty_score)
- [ ] `compute_novelty` correto em corpus vazio / com vizinhos / sem embedding
- [ ] Novelty cached + invalidado em reindex
- [ ] 3º path probabilístico em `consolidation_candidates` funciona
- [ ] `tool_add_note(emotional_weight=...)` propaga até frontmatter
- [ ] Skill `brainiac-capture` documenta passo opcional
- [ ] Cobertura `novelty.py` ≥ 95%
- [ ] Suite verde sem regressões

Após Phase 7 verde, próxima: **Phase 8 — Atkinson-Shiffrin states**.
