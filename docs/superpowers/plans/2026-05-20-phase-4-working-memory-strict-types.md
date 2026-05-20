# Fase 4 — Working Memory + Tipos Estritos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar disciplina cognitiva forçada — `shortMemory/` recusa exceder limite configurável; classificador heurístico sugere `episodic/semantic/working` no capture; CLI `brainiac classify <path>` ajuda a normalizar notas legadas.

**Architecture:** Três novos módulos pequenos — `core/config.py` (Config dataclass + `load_config(root)` lendo `brainiac.toml` opcional), `core/working_memory.py` (count + capacity check + eviction candidates), `core/classifier.py` (regras léxicas em pt-BR + scoring por tipo). MCP layer estende `tool_add_note` (recusa estruturada com `suggestion`) e adiciona `tool_working_status`. CLI adiciona `brainiac classify <path>`. Skill `brainiac-capture` atualizada para consultar classifier antes de perguntar tipo. Sem novas dependências pip — `tomllib` é stdlib em Python 3.11+.

**Tech Stack:**
- Python stdlib: `tomllib`, `dataclasses`, `re`
- Existente: `sqlite3`, `pydantic>=2`, `click>=8`, `mcp>=1.0`
- Sem novas dependências pip

---

## Mapa de arquivos (Fase 4)

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── config.py             # CREATE: Config dataclass + load_config(root)
│   │   ├── working_memory.py     # CREATE: working_count, candidates, check_capacity, working_status
│   │   └── classifier.py         # CREATE: classify(body, tags) → (type|None, confidence)
│   ├── mcp_server.py             # MODIFY: tool_add_note enforce limit + tool_working_status
│   └── cli.py                    # MODIFY: comando classify
└── tests/
    ├── core/
    │   ├── test_config.py        # CREATE
    │   ├── test_working_memory.py# CREATE
    │   └── test_classifier.py    # CREATE (unit + 20-note benchmark)
    ├── test_mcp_server.py        # MODIFY: limit enforcement + working_status tests
    ├── test_cli.py               # MODIFY: classify command tests
    └── test_smoke_e2e.py         # MODIFY: DoD Phase 4

.claude/skills/brainiac-capture/SKILL.md  # MODIFY: usar classify antes de perguntar tipo
```

**Decisões arquiteturais:**
- **Config opcional, defaults inline**: `brainiac.toml` é opcional. Se ausente, usa defaults da dataclass (`working_memory_limit=9`, `classifier_threshold=0.3`). Sem warning — silêncio é fluxo padrão.
- **`working_memory.py` separado, não dentro de `index.py`**: lógica de quotas e candidatos é uma preocupação cognitiva distinta de indexação SQL. Mesmo padrão de `decay.py` / `sm2.py`.
- **`WorkingMemoryFullError` carrega `candidates` no payload**: erro estruturado vira `{"error", "count", "limit", "suggestion"}` no nível MCP. Cliente sempre pode agir sobre o erro.
- **Classifier zero-deps**: lexical pt-BR puro com `re`. Embeddings deferidos. Para o DoD ≥85% no sample curado, regras + tag hints bastam.
- **Threshold de ambiguidade = 0.3** + **margem mínima entre top-2 = 0.15**: abaixo disso, retorna `(None, 0.0)` para forçar o skill a perguntar ao usuário.
- **`brainiac classify` é stateless**: lê o `.md`, roda classifier, imprime sugestão e confidence. Não modifica o arquivo (usuário decide).

---

## Task 1: `core/config.py` — Config dataclass + `load_config`

**Files:**
- Create: `tools/brainiac/brainiac/core/config.py`
- Create: `tools/brainiac/tests/core/test_config.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_config.py`:

```python
from pathlib import Path

import pytest


def test_load_config_returns_defaults_when_no_toml(fake_brainiac):
    from brainiac.core.config import Config, load_config

    cfg = load_config(fake_brainiac)
    assert isinstance(cfg, Config)
    assert cfg.working_memory_limit == 9
    assert cfg.classifier_threshold == 0.3


def test_load_config_reads_from_brainiac_toml(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 5\nclassifier_threshold = 0.5\n',
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.working_memory_limit == 5
    assert cfg.classifier_threshold == 0.5


def test_load_config_partial_overrides_keeps_defaults(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 12\n',
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.working_memory_limit == 12
    assert cfg.classifier_threshold == 0.3  # default preserved


def test_load_config_rejects_unknown_keys(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = 9\nunknown_key = "x"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown_key"):
        load_config(fake_brainiac)


def test_load_config_rejects_invalid_types(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        'working_memory_limit = "nine"\n',
        encoding="utf-8",
    )
    with pytest.raises((TypeError, ValueError)):
        load_config(fake_brainiac)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py -v --no-cov`
Expected: FAIL (`ModuleNotFoundError: No module named 'brainiac.core.config'`).

- [ ] **Step 3: Implementar `core/config.py`**

Criar `tools/brainiac/brainiac/core/config.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    working_memory_limit: int = 9
    classifier_threshold: float = 0.3


def load_config(root: Path) -> Config:
    """Load brainiac.toml from root, falling back to defaults.

    Raises ValueError on unknown keys (typo protection).
    """
    cfg_path = root / "brainiac.toml"
    if not cfg_path.exists():
        return Config()

    with cfg_path.open("rb") as f:
        data = tomllib.load(f)

    allowed = {f.name for f in fields(Config)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown config keys in brainiac.toml: {sorted(unknown)}")

    return Config(**data)
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py -v --no-cov`
Expected: 5 PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 171 PASS (166 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/config.py tools/brainiac/tests/core/test_config.py
git commit -m "feat(phase-4): core/config.py — load brainiac.toml with safe defaults"
```

---

## Task 2: `core/working_memory.py` — count + candidates + capacity check

**Files:**
- Create: `tools/brainiac/brainiac/core/working_memory.py`
- Create: `tools/brainiac/tests/core/test_working_memory.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_working_memory.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brainiac.core.config import Config
from brainiac.core.index import connect, index_note
from brainiac.core.note import write_note
from brainiac.core.paths import index_db_path, note_path
from tests.conftest import make_fm


def _seed_working(root: Path, note_id: str, access_count: int = 0, strength: float = 1.0) -> None:
    fm = make_fm(note_id=note_id, note_type="working", access_count=access_count, strength=strength)
    p = note_path(root, note_id, "working")
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(root))
    index_note(conn, fm, f"# {note_id}\n\nbody", str(p.relative_to(root)))


# --- working_count ---

def test_working_count_zero_for_empty(fake_brainiac):
    from brainiac.core.working_memory import working_count

    conn = connect(index_db_path(fake_brainiac))
    assert working_count(conn) == 0


def test_working_count_only_counts_type_working(fake_brainiac):
    from brainiac.core.working_memory import working_count

    _seed_working(fake_brainiac, "2026-05-20-w1")
    fm = make_fm("2026-05-20-s1", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-s1", "semantic")
    write_note(p, fm, "# s1\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# s1\n\nbody", str(p.relative_to(fake_brainiac)))

    assert working_count(conn) == 1


def test_working_count_excludes_archived(fake_brainiac):
    from brainiac.core.working_memory import working_count

    fm = make_fm("2026-05-20-arc", "working")
    p = note_path(fake_brainiac, "2026-05-20-arc", "working")
    write_note(p, fm, "# arc\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# arc\n\nbody", str(p.relative_to(fake_brainiac)), archived=True)

    assert working_count(conn) == 0


# --- candidates_for_eviction ---

def test_candidates_orders_by_access_count_desc(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    _seed_working(fake_brainiac, "2026-05-20-cold", access_count=0)
    _seed_working(fake_brainiac, "2026-05-20-hot", access_count=10)
    _seed_working(fake_brainiac, "2026-05-20-warm", access_count=3)

    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=3)
    ids = [c["id"] for c in cands]
    assert ids == ["2026-05-20-hot", "2026-05-20-warm", "2026-05-20-cold"]


def test_candidates_respects_limit(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    for i in range(5):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=2)
    assert len(cands) == 2


def test_candidates_returns_required_fields(fake_brainiac):
    from brainiac.core.working_memory import candidates_for_eviction

    _seed_working(fake_brainiac, "2026-05-20-fields", access_count=5, strength=0.7)
    conn = connect(index_db_path(fake_brainiac))
    cands = candidates_for_eviction(conn, limit=5)
    assert len(cands) == 1
    c = cands[0]
    assert set(c.keys()) >= {"id", "path", "access_count", "strength"}


# --- check_working_capacity ---

def test_check_working_capacity_passes_when_below_limit(fake_brainiac):
    from brainiac.core.working_memory import check_working_capacity

    _seed_working(fake_brainiac, "2026-05-20-w1")
    conn = connect(index_db_path(fake_brainiac))
    # Does not raise
    check_working_capacity(conn, Config(working_memory_limit=9))


def test_check_working_capacity_raises_when_at_limit(fake_brainiac):
    from brainiac.core.working_memory import (
        WorkingMemoryFullError,
        check_working_capacity,
    )

    for i in range(3):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))

    with pytest.raises(WorkingMemoryFullError) as excinfo:
        check_working_capacity(conn, Config(working_memory_limit=3))
    err = excinfo.value
    assert err.count == 3
    assert err.limit == 3
    assert len(err.candidates) >= 1


# --- working_status ---

def test_working_status_reports_empty_state(fake_brainiac):
    from brainiac.core.working_memory import working_status

    conn = connect(index_db_path(fake_brainiac))
    status = working_status(conn, Config(working_memory_limit=9))
    assert status == {"count": 0, "limit": 9, "full": False, "candidates": []}


def test_working_status_reports_full_state_with_candidates(fake_brainiac):
    from brainiac.core.working_memory import working_status

    for i in range(3):
        _seed_working(fake_brainiac, f"2026-05-20-w{i}", access_count=i)
    conn = connect(index_db_path(fake_brainiac))
    status = working_status(conn, Config(working_memory_limit=3))
    assert status["count"] == 3
    assert status["limit"] == 3
    assert status["full"] is True
    assert len(status["candidates"]) == 3
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_working_memory.py -v --no-cov`
Expected: FAIL (`ModuleNotFoundError: No module named 'brainiac.core.working_memory'`).

- [ ] **Step 3: Implementar `core/working_memory.py`**

Criar `tools/brainiac/brainiac/core/working_memory.py`:

```python
from __future__ import annotations

import sqlite3

from brainiac.core.config import Config


class WorkingMemoryFullError(Exception):
    """Raised when adding a working note would exceed the configured limit."""

    def __init__(self, count: int, limit: int, candidates: list[dict]):
        self.count = count
        self.limit = limit
        self.candidates = candidates
        super().__init__(f"shortMemory at capacity ({count}/{limit})")


def working_count(conn: sqlite3.Connection) -> int:
    """Count of active (non-archived) working notes."""
    row = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE type='working' AND archived=0"
    ).fetchone()
    return int(row[0])


def candidates_for_eviction(
    conn: sqlite3.Connection,
    limit: int = 5,
) -> list[dict]:
    """Top-N working notes most likely worth promoting or discarding.

    Sorted by access_count DESC (most-touched first — strong promotion candidates),
    tiebroken by strength ASC (weakest first — discard candidates).
    """
    rows = conn.execute(
        """
        SELECT id, path, access_count, strength
        FROM notes
        WHERE type='working' AND archived=0
        ORDER BY access_count DESC, strength ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {"id": r[0], "path": r[1], "access_count": r[2], "strength": r[3]}
        for r in rows
    ]


def check_working_capacity(conn: sqlite3.Connection, config: Config) -> None:
    """Raise WorkingMemoryFullError if adding a new working note would exceed limit."""
    count = working_count(conn)
    if count >= config.working_memory_limit:
        candidates = candidates_for_eviction(conn, limit=5)
        raise WorkingMemoryFullError(count, config.working_memory_limit, candidates)


def working_status(conn: sqlite3.Connection, config: Config) -> dict:
    """Snapshot of working memory occupancy and eviction candidates."""
    count = working_count(conn)
    limit = config.working_memory_limit
    is_full = count >= limit
    return {
        "count": count,
        "limit": limit,
        "full": is_full,
        "candidates": candidates_for_eviction(conn, limit=5) if is_full else [],
    }
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_working_memory.py -v --no-cov`
Expected: 9 PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (171 + 9 = 180).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/working_memory.py tools/brainiac/tests/core/test_working_memory.py
git commit -m "feat(phase-4): core/working_memory.py — count/candidates/capacity/status"
```

---

## Task 3: MCP — enforce limit in `tool_add_note` + new `tool_working_status`

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`

- [ ] **Step 1: Acrescentar testes failing em `test_mcp_server.py`**

Acrescentar ao final de `tools/brainiac/tests/test_mcp_server.py`:

```python
def test_tool_add_note_rejects_working_when_full(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-w-a", note_type="working",
        title="A", body="# A\n\nx",
    )
    tool_add_note(
        note_id="2026-05-20-w-b", note_type="working",
        title="B", body="# B\n\ny",
    )
    result = tool_add_note(
        note_id="2026-05-20-w-c", note_type="working",
        title="C", body="# C\n\nz",
    )
    assert "error" in result
    assert result["count"] == 2
    assert result["limit"] == 2
    assert isinstance(result["suggestion"], list)
    assert len(result["suggestion"]) >= 1
    # file should NOT be created
    assert not (fake_brainiac / "shortMemory" / "2026-05-20-w-c.md").exists()


def test_tool_add_note_allows_semantic_at_working_limit(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 1\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(
        note_id="2026-05-20-w-fill", note_type="working",
        title="W", body="# W\n\nbody",
    )
    # semantic note should still go through
    result = tool_add_note(
        note_id="2026-05-20-s-ok", note_type="semantic",
        title="S", body="# S\n\nbody",
    )
    assert "error" not in result
    assert result["type"] == "semantic"


def test_tool_working_status_reports_empty_brainiac(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_working_status

    status = tool_working_status()
    assert status["count"] == 0
    assert status["limit"] == 9  # default
    assert status["full"] is False
    assert status["candidates"] == []


def test_tool_working_status_reports_full_with_candidates(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note, tool_working_status

    tool_add_note(note_id="2026-05-20-ws-a", note_type="working", title="A", body="# A")
    tool_add_note(note_id="2026-05-20-ws-b", note_type="working", title="B", body="# B")

    status = tool_working_status()
    assert status["count"] == 2
    assert status["limit"] == 2
    assert status["full"] is True
    assert len(status["candidates"]) == 2
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov -k "working or rejects_working or allows_semantic"`
Expected: FAIL (`cannot import name 'tool_working_status'`, plus working-limit test fails because no enforcement).

- [ ] **Step 3: Modificar `tool_add_note` em `mcp_server.py`**

Substituir `tool_add_note` em `tools/brainiac/brainiac/mcp_server.py`:

```python
def tool_add_note(
    note_id: str,
    note_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    study: bool = False,
) -> dict:
    """Create a new note. Body should start with '# title'.

    If note_type='working' and shortMemory is full per config, returns a
    structured error with eviction candidates instead of creating the note.
    If study=True, enrolls in SM-2.
    """
    root = find_root()

    if note_type == "working":
        from brainiac.core.config import load_config
        from brainiac.core.working_memory import (
            WorkingMemoryFullError,
            check_working_capacity,
        )
        conn = connect(index_db_path(root))
        try:
            check_working_capacity(conn, load_config(root))
        except WorkingMemoryFullError as exc:
            return {
                "error": str(exc),
                "count": exc.count,
                "limit": exc.limit,
                "suggestion": exc.candidates,
            }

    fm = new_note(note_id=note_id, note_type=note_type, tags=tags or [])

    if study:
        from brainiac.core.sm2 import start_sm2
        fm.sm2 = start_sm2()

    # ensure body starts with a title line
    body_with_title = body if body.lstrip().startswith("#") else f"# {title}\n\n{body}"

    path = note_path(root, note_id, note_type)
    write_note(path, fm, body_with_title)

    conn = connect(index_db_path(root))
    rel = path.relative_to(root)
    index_note(conn, fm, body_with_title, str(rel))

    return {"id": note_id, "path": str(rel), "type": note_type}
```

- [ ] **Step 4: Adicionar `tool_working_status` em `mcp_server.py`**

Antes de `# --- MCP server plumbing ---`, acrescentar:

```python
def tool_working_status() -> dict:
    """Snapshot of shortMemory occupancy + eviction candidates if full."""
    from brainiac.core.config import load_config
    from brainiac.core.working_memory import working_status
    root = find_root()
    conn = connect(index_db_path(root))
    return working_status(conn, load_config(root))
```

Atualizar o docstring no topo do arquivo:

```python
"""MCP server exposing brainiac tools via stdio.

Tools (11): add_note, recall, get_note, link, list_recent,
            consolidate_check, forget,
            review_queue, grade_review, start_review,
            working_status
"""
```

- [ ] **Step 5: Registrar `working_status` em `_list_tools()` e `_DISPATCH`**

Antes do `]` final em `_list_tools()`, acrescentar:

```python
        Tool(
            name="working_status",
            description=(
                "Snapshot do estado da shortMemory: ocupação atual, limite configurado, "
                "se está cheia, e candidatos a promover/descartar quando cheia."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
```

Atualizar `_DISPATCH` adicionando a chave:

```python
_DISPATCH = {
    "add_note": tool_add_note,
    "recall": tool_recall,
    "get_note": tool_get_note,
    "link": tool_link,
    "list_recent": tool_list_recent,
    "consolidate_check": tool_consolidate_check,
    "forget": tool_forget,
    "review_queue": tool_review_queue,
    "grade_review": tool_grade_review,
    "start_review": tool_start_review,
    "working_status": tool_working_status,
}
```

- [ ] **Step 6: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov`
Expected: PASS (todos 13 anteriores + 4 novos = 17).

- [ ] **Step 7: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (180 + 4 = 184).

- [ ] **Step 8: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/tests/test_mcp_server.py
git commit -m "feat(phase-4): MCP — enforce working limit em add_note + tool working_status"
```

---

## Task 4: `core/classifier.py` — heurística léxica pt-BR

**Files:**
- Create: `tools/brainiac/brainiac/core/classifier.py`
- Create: `tools/brainiac/tests/core/test_classifier.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_classifier.py`:

```python
import pytest


# --- happy-path tests, one per type ---

def test_classify_episodic_first_person_past():
    from brainiac.core.classifier import classify
    typ, conf = classify("Hoje fui ao escritório e decidimos pivotar o produto.")
    assert typ == "episodic"
    assert conf > 0


def test_classify_semantic_definition_form():
    from brainiac.core.classifier import classify
    typ, conf = classify("BM25 é uma função de ranking probabilística usada em FTS.")
    assert typ == "semantic"
    assert conf > 0


def test_classify_working_short_body():
    from brainiac.core.classifier import classify
    typ, conf = classify("ideia: redis como cache?", tags=["wip"])
    assert typ == "working"
    assert conf > 0


def test_classify_working_question_or_draft():
    from brainiac.core.classifier import classify
    typ, conf = classify("TODO: investigar latência. preciso pensar mais sobre isso depois.")
    assert typ == "working"


def test_classify_episodic_via_tag():
    from brainiac.core.classifier import classify
    typ, conf = classify("Reunião com cliente A.", tags=["reuniao"])
    assert typ == "episodic"


def test_classify_semantic_via_tag():
    from brainiac.core.classifier import classify
    typ, conf = classify("Termo descontextualizado.", tags=["conceito"])
    assert typ == "semantic"


# --- ambiguity ---

def test_classify_ambiguous_returns_none():
    from brainiac.core.classifier import classify
    typ, conf = classify("Frase neutra sem marcadores.")
    assert typ is None
    assert conf == 0.0


def test_classify_empty_body_returns_working():
    """Empty/very short body without any marker is treated as working draft."""
    from brainiac.core.classifier import classify
    typ, _ = classify("rascunho")
    assert typ == "working"


# --- threshold tunable ---

def test_classify_threshold_lower_makes_borderline_decisive():
    from brainiac.core.classifier import classify
    typ_strict, _ = classify("Hoje aprendi algo.", threshold=0.5)
    typ_loose, _ = classify("Hoje aprendi algo.", threshold=0.2)
    # "Hoje" hits 1 episodic marker (0.3 score) — strict (0.5) → None, loose (0.2) → episodic
    assert typ_strict is None
    assert typ_loose == "episodic"


# --- return type ---

def test_classify_returns_tuple_of_optional_str_and_float():
    from brainiac.core.classifier import classify
    result = classify("Texto qualquer.")
    assert isinstance(result, tuple)
    assert len(result) == 2
    typ, conf = result
    assert typ is None or isinstance(typ, str)
    assert isinstance(conf, float)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_classifier.py -v --no-cov`
Expected: FAIL (`ModuleNotFoundError: No module named 'brainiac.core.classifier'`).

- [ ] **Step 3: Implementar `core/classifier.py`**

Criar `tools/brainiac/brainiac/core/classifier.py`:

```python
from __future__ import annotations

import re

_EPISODIC_PATTERNS = [
    r"\bhoje\b", r"\bontem\b", r"\banteontem\b",
    r"\beu fiz\b", r"\beu vi\b", r"\beu li\b", r"\beu consegui\b",
    r"\bdecidimos\b", r"\bdecidi\b",
    r"\bfui ao\b", r"\bfui à\b", r"\bfui em\b",
    r"\bminha reuni[aã]o\b", r"\bnossa reuni[aã]o\b",
    r"\bme contou\b", r"\bme disse\b",
]

_SEMANTIC_PATTERNS = [
    r"\bé uma\b", r"\bé um\b",
    r"\bconsiste em\b", r"\bfunciona\b", r"\bopera\b",
    r"\brefere-se a\b", r"\bsignifica\b",
    r"\bdefine-se\b", r"\bcaracteriza-se\b",
    r"\btrata-se de\b",
]

_WORKING_TAG_HINTS = {"rascunho", "draft", "ideia", "wip", "todo"}
_EPISODIC_TAG_HINTS = {"pessoal", "diário", "diario", "reunião", "reuniao", "evento"}
_SEMANTIC_TAG_HINTS = {"conceito", "definição", "definicao", "fato", "fórmula", "formula"}

_MARKER_WEIGHT = 0.3
_TAG_WEIGHT = 0.4
_SHORT_BODY_WEIGHT = 0.4
_QUESTION_OR_DRAFT_WEIGHT = 0.4

_SHORT_BODY_CHARS = 80
_AMBIGUITY_MARGIN = 0.15
_DEFAULT_THRESHOLD = 0.3


def classify(
    body: str,
    tags: list[str] | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[str | None, float]:
    """Heuristic classifier for note type.

    Returns (suggested_type, confidence in [0, 1]).
    Returns (None, 0.0) if confidence is below threshold or top-2 tie is too close.
    """
    tags = tags or []
    body_lower = body.lower()
    score = {"episodic": 0.0, "semantic": 0.0, "working": 0.0}

    for pat in _EPISODIC_PATTERNS:
        if re.search(pat, body_lower):
            score["episodic"] += _MARKER_WEIGHT

    for pat in _SEMANTIC_PATTERNS:
        if re.search(pat, body_lower):
            score["semantic"] += _MARKER_WEIGHT

    if len(body.strip()) < _SHORT_BODY_CHARS:
        score["working"] += _SHORT_BODY_WEIGHT
    tail = body[-30:]
    if "?" in tail or "rascunho" in body_lower or "todo:" in body_lower:
        score["working"] += _QUESTION_OR_DRAFT_WEIGHT

    for t in tags:
        tl = t.lower()
        if tl in _EPISODIC_TAG_HINTS:
            score["episodic"] += _TAG_WEIGHT
        elif tl in _SEMANTIC_TAG_HINTS:
            score["semantic"] += _TAG_WEIGHT
        elif tl in _WORKING_TAG_HINTS:
            score["working"] += _TAG_WEIGHT

    best = max(score, key=score.get)
    best_score = score[best]
    sorted_scores = sorted(score.values(), reverse=True)
    margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else best_score

    if best_score < threshold:
        return None, 0.0
    if margin < _AMBIGUITY_MARGIN:
        return None, 0.0

    return best, min(best_score, 1.0)
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_classifier.py -v --no-cov`
Expected: 10 PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (184 + 10 = 194).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/classifier.py tools/brainiac/tests/core/test_classifier.py
git commit -m "feat(phase-4): classifier.py — heurística léxica pt-BR (episodic/semantic/working)"
```

---

## Task 5: CLI `brainiac classify <path>`

**Files:**
- Modify: `tools/brainiac/brainiac/cli.py`
- Modify: `tools/brainiac/tests/test_cli.py`

- [ ] **Step 1: Acrescentar testes failing em `test_cli.py`**

Acrescentar ao final de `tools/brainiac/tests/test_cli.py`:

```python
class TestClassifyCommand:
    def test_classify_episodic_note(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from tests.conftest import make_fm

        fm = make_fm("2026-05-20-classify-e", "working")
        p = fake_brainiac / "shortMemory" / "2026-05-20-classify-e.md"
        write_note(p, fm, "# log\n\nHoje fui à reunião e decidimos pivotar.")

        result = CliRunner().invoke(main, ["classify", str(p)])
        assert result.exit_code == 0
        assert "episodic" in result.output.lower()

    def test_classify_semantic_note(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from tests.conftest import make_fm

        fm = make_fm("2026-05-20-classify-s", "working")
        p = fake_brainiac / "shortMemory" / "2026-05-20-classify-s.md"
        write_note(p, fm, "# BM25\n\nBM25 é uma função de ranking probabilística.")

        result = CliRunner().invoke(main, ["classify", str(p)])
        assert result.exit_code == 0
        assert "semantic" in result.output.lower()

    def test_classify_ambiguous_note_reports_unknown(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from tests.conftest import make_fm

        fm = make_fm("2026-05-20-classify-amb", "working")
        p = fake_brainiac / "shortMemory" / "2026-05-20-classify-amb.md"
        write_note(p, fm, "# x\n\nFrase neutra sem marcadores claros.")

        result = CliRunner().invoke(main, ["classify", str(p)])
        assert result.exit_code == 0
        assert "ambiguous" in result.output.lower() or "unknown" in result.output.lower()

    def test_classify_nonexistent_file_errors(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))

        result = CliRunner().invoke(main, ["classify", str(fake_brainiac / "missing.md")])
        assert result.exit_code != 0
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov -k "Classify"`
Expected: FAIL (`No such command 'classify'`).

- [ ] **Step 3: Adicionar comando `classify` em `cli.py`**

Antes do comando `mcp` em `tools/brainiac/brainiac/cli.py`, acrescentar:

```python
@main.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def classify(path: Path) -> None:
    """Suggest a type (episodic/semantic/working) for an existing .md note."""
    from brainiac.core.classifier import classify as classify_body
    from brainiac.core.note import parse_note

    fm, body = parse_note(path)
    suggested, confidence = classify_body(body, tags=fm.tags)

    click.echo(f"file: {path}")
    click.echo(f"current type: {fm.type}")
    if suggested is None:
        click.echo("suggested: ambiguous (consider asking the user or refining the body)")
    else:
        click.echo(f"suggested: {suggested} (confidence: {confidence:.2f})")
```

Atualizar os imports no topo de `cli.py` — adicionar `from pathlib import Path` se ainda não estiver lá:

(Verificar primeiro com `head -10 tools/brainiac/brainiac/cli.py`. Se já tem `from pathlib import Path`, não duplicar. Se não tem, adicionar logo após o `import click`.)

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov`
Expected: PASS (13 anteriores + 4 novos = 17).

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (194 + 4 = 198).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_cli.py
git commit -m "feat(phase-4): CLI brainiac classify <path> — sugere tipo p/ nota legada"
```

---

## Task 6: Atualizar skill `brainiac-capture` para consultar classifier

**Files:**
- Modify: `.claude/skills/brainiac-capture/SKILL.md`

- [ ] **Step 1: Substituir o passo 1 ("Determinar tipo")**

Em `.claude/skills/brainiac-capture/SKILL.md`, localizar o passo 1 (`**Determinar tipo** da nota:`) e substituir:

```markdown
1. **Determinar tipo** da nota:
   - Antes de perguntar, rode o classificador rápido sobre o body + tags hipotéticas.
     Mentalmente (ou via `brainiac classify` se a nota já está em arquivo) avalie:
     - 1ª pessoa + verbos no passado ("hoje fui...", "decidimos...") → forte sinal `episodic`
     - Definição impessoal ("X é uma...", "X consiste em...") → forte sinal `semantic`
     - Body curto, com `?` no fim, palavras como "ideia", "rascunho", "todo" → forte sinal `working`
   - **Se o sinal for forte (≥ 0.5 de confiança)**: use o tipo sugerido sem perguntar.
   - **Se for ambíguo** (sem sinal claro ou dois tipos empatados): pergunte ao usuário.
   - Tipos possíveis:
     - `episodic` — narrativa pessoal com timestamp/contexto ("hoje eu fiz X", "decidimos Y na reunião")
     - `semantic` — conceito/fato descontextualizado ("Kubernetes scheduler funciona assim", "BM25 é uma função de ranking")
     - `working` — ideia ainda crua, a ser refinada/promovida depois (rascunho)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/brainiac-capture/SKILL.md
git commit -m "feat(phase-4): brainiac-capture skill — consultar classifier antes de perguntar tipo"
```

---

## Task 7: Benchmark de acurácia do classifier (DoD ≥ 85%)

**Files:**
- Modify: `tools/brainiac/tests/core/test_classifier.py`

- [ ] **Step 1: Acrescentar benchmark ao final de `test_classifier.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_classifier.py`:

```python
# --- 20-note accuracy benchmark (DoD §5 Fase 4) ---

_SAMPLES: list[tuple[str, list[str], str]] = [
    # episodic (7)
    ("Hoje fui à pizzaria com a equipe.", [], "episodic"),
    ("Ontem decidimos pivotar o produto para B2B.", [], "episodic"),
    ("Eu vi o talk do Karpathy sobre LLMs ontem.", [], "episodic"),
    ("Anteontem li o paper sobre Mamba na cama.", [], "episodic"),
    ("Minha reunião com o cliente foi produtiva.", ["reuniao"], "episodic"),
    ("Hoje consegui debugar aquele bug chato do K8s.", [], "episodic"),
    ("Decidi mudar de linguagem para o projeto novo.", [], "episodic"),

    # semantic (8)
    ("BM25 é uma função de ranking probabilística usada em FTS.", ["ranking"], "semantic"),
    ("Kubernetes é um orquestrador de containers em larga escala.", ["k8s"], "semantic"),
    ("Mamba consiste em um state-space model alternativo a transformers.", [], "semantic"),
    ("O algoritmo SuperMemo-2 funciona com ease, interval e reps por nota.", [], "semantic"),
    ("Hash criptográfico refere-se a função one-way determinística.", [], "semantic"),
    ("Eventual consistency significa que reads podem retornar dados stale.", [], "semantic"),
    ("Embedding caracteriza-se por mapear texto em vetor denso.", [], "semantic"),
    ("Pydantic é uma lib de validação de dados em Python moderno.", [], "semantic"),

    # working (5)
    ("ideia: usar redis como cache de embeddings?", ["wip"], "working"),
    ("rascunho do roadmap Q3", ["rascunho"], "working"),
    ("TODO: investigar latência da query X.", [], "working"),
    ("preciso pensar mais sobre isso.", [], "working"),
    ("anotar depois", [], "working"),
]


def test_classifier_accuracy_on_curated_20_note_sample():
    """DoD §5 Fase 4: classifier ≥ 85% accuracy on a curated sample of 20 notes."""
    from brainiac.core.classifier import classify

    correct = 0
    misclassified: list[tuple[str, str, str | None]] = []
    for body, tags, expected in _SAMPLES:
        suggested, _ = classify(body, tags=tags)
        if suggested == expected:
            correct += 1
        else:
            misclassified.append((body, expected, suggested))

    accuracy = correct / len(_SAMPLES)
    assert accuracy >= 0.85, (
        f"Accuracy {accuracy:.0%} below 85% target. "
        f"Misclassified ({len(misclassified)}/{len(_SAMPLES)}): "
        f"{misclassified}"
    )
```

- [ ] **Step 2: Rodar — verificar acurácia**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_classifier.py::test_classifier_accuracy_on_curated_20_note_sample -v --no-cov`
Expected: PASS (accuracy ≥ 85%).

**Se falhar:** inspecionar `misclassified` na mensagem de erro. Em geral o ajuste é:
- Adicionar palavra-chave em `_EPISODIC_PATTERNS` / `_SEMANTIC_PATTERNS` que cobriria a falha.
- **NÃO** abaixar o threshold abaixo de 0.2 — isso vira ruído.
- Re-rodar até passar; se truques esgotarem e ainda <85%, parar e reportar BLOCKED.

- [ ] **Step 3: Commit**

```bash
git add tools/brainiac/tests/core/test_classifier.py
git commit -m "test(phase-4): classifier accuracy benchmark — 20-note curated sample ≥85%"
```

---

## Task 8: Smoke E2E — DoD da Fase 4

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: Acrescentar testes DoD ao final de `test_smoke_e2e.py`**

Acrescentar:

```python
# --- DoD Phase 4 ---


def test_short_memory_never_exceeds_limit(fake_brainiac, monkeypatch):
    """DoD: shortMemory/ nunca excede limite; tentativa retorna erro útil."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(note_id="2026-05-20-w-1", note_type="working", title="1", body="# 1")
    tool_add_note(note_id="2026-05-20-w-2", note_type="working", title="2", body="# 2")
    result = tool_add_note(note_id="2026-05-20-w-3", note_type="working", title="3", body="# 3")

    assert "error" in result
    assert result["count"] == 2
    assert result["limit"] == 2
    assert isinstance(result["suggestion"], list)

    # Filesystem must reflect refusal — only 2 .md files
    short_dir = fake_brainiac / "shortMemory"
    actual = sorted(p.name for p in short_dir.glob("2026-05-20-w-*.md"))
    assert actual == ["2026-05-20-w-1.md", "2026-05-20-w-2.md"]


def test_capture_classifier_unambiguous_returns_type(fake_brainiac, monkeypatch):
    """DoD: capture (via classifier) reconhece tipo sem perguntar quando confiante."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.classifier import classify

    # episodic — confident
    typ, conf = classify("Hoje decidimos pivotar para B2B.", tags=["reuniao"])
    assert typ == "episodic"
    assert conf > 0.3

    # semantic — confident
    typ, conf = classify("BM25 é uma função de ranking probabilística.", tags=["conceito"])
    assert typ == "semantic"
    assert conf > 0.3


def test_capture_classifier_ambiguous_returns_none(fake_brainiac, monkeypatch):
    """DoD: capture pergunta tipo apenas quando ambíguo (classifier retorna None)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.classifier import classify

    typ, _ = classify("Frase neutra sem marcadores fortes.")
    assert typ is None  # skill deve perguntar ao usuário


def test_brainiac_classify_cli_on_legacy_note(fake_brainiac, monkeypatch):
    """DoD: brainiac classify <path> sugere tipo para nota pré-existente/legada."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from click.testing import CliRunner
    from brainiac.cli import main
    from brainiac.core.note import write_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-legacy", "working")  # mistyped as working
    p = fake_brainiac / "shortMemory" / "2026-05-20-legacy.md"
    write_note(p, fm, "# K8s\n\nKubernetes é um orquestrador de containers.")

    result = CliRunner().invoke(main, ["classify", str(p)])
    assert result.exit_code == 0
    assert "semantic" in result.output.lower()
```

- [ ] **Step 2: Rodar testes DoD**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_smoke_e2e.py -v --no-cov -k "short_memory or classifier_unambiguous or classifier_ambiguous or brainiac_classify"`
Expected: 4 PASS.

- [ ] **Step 3: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (199 + 4 = 203).

- [ ] **Step 4: Verificar cobertura dos novos módulos**

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.config --cov=brainiac.core.working_memory --cov=brainiac.core.classifier --cov-report=term-missing --ignore=tests/core/test_embeddings.py 2>&1 | tail -10`
Expected: cobertura ≥ 80% em `config.py`, `working_memory.py`, `classifier.py`.

- [ ] **Step 5: Commit final da Fase 4**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-4): smoke E2E — DoD working limit + classifier (capture + CLI)"
```

---

## Definition of Done — Fase 4

Checklist final da spec (§5 Fase 4):

- [ ] `shortMemory/` nunca excede limite; tentativa retorna erro útil com `suggestion` (test_smoke_e2e: `test_short_memory_never_exceeds_limit`)
- [ ] Capture pergunta tipo apenas quando ambíguo (test_smoke_e2e: `test_capture_classifier_unambiguous_returns_type` + `test_capture_classifier_ambiguous_returns_none`)
- [ ] `brainiac classify` acerta ≥ 85% em sample manual de 20 notas (test_classifier: `test_classifier_accuracy_on_curated_20_note_sample`)
- [ ] `working_status` reporta ocupação + candidatos (test_mcp_server: `test_tool_working_status_reports_full_with_candidates`)
- [ ] Cobertura ≥ 80% em `config.py`, `working_memory.py`, `classifier.py`

Fase 4 conclui o roadmap de 5 fases definido em §5 do spec. Sistema cognitivo completo.
