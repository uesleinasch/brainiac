# Fase 3 — SM-2 Spaced Repetition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar revisão espaçada (SuperMemo-2 canônico) — notas marcadas para estudo entram em ciclo de revisão ativa com intervalos crescentes; usuário gradua recall (0-5) e o sistema atualiza ease/interval/next_review.

**Architecture:** Novo módulo `core/sm2.py` — funções puras (`grade`, `start_sm2`) + I/O (`review_queue`, `grade_review`, `start_review`). O campo `sm2_json` da tabela `notes` já existe (introduzido na Fase 0 como nullable). O modelo `SM2` ganha um campo `reps` (contador de revisões bem-sucedidas) — necessário para distinguir 1ª/2ª/3ª+ revisão no branch do algoritmo. Três novos MCP tools (`review_queue`, `grade_review`, `start_review`) + extensão de `add_note(study=True)` + um comando CLI (`brainiac review`) + skill `brainiac-review` fecham o ciclo. Revisões disparam também bump em `access_count`/`last_access` (DoD §5 Fase 3).

**Tech Stack:**
- Python stdlib: `math`, `datetime`
- Existente: `sqlite3`, `pydantic>=2`, `click>=8`, `mcp>=1.0`
- Sem novas dependências pip

---

## Mapa de arquivos (Fase 3)

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── models.py             # MODIFY: SM2.reps field
│   │   └── sm2.py                # CREATE: grade/start_sm2/review_queue/grade_review/start_review
│   ├── mcp_server.py             # MODIFY: tool_review_queue, tool_grade_review, tool_start_review, study param em add_note
│   └── cli.py                    # MODIFY: comando review
└── tests/
    ├── core/
    │   ├── test_models.py        # MODIFY: validar reps default + range
    │   └── test_sm2.py           # CREATE
    ├── test_mcp_server.py        # MODIFY: 4 testes (review_queue, grade_review, start_review, add_note study)
    ├── test_cli.py               # MODIFY: 2 testes (review queue vazia + grade interativo)
    └── test_smoke_e2e.py         # MODIFY: 4 testes DoD Fase 3

.claude/skills/
├── brainiac-review/SKILL.md      # CREATE
└── brainiac-capture/SKILL.md     # MODIFY: passo "perguntar se study"
```

**Decisões arquiteturais:**
- **`reps` em `SM2`, não derivado**: derivar 1ª/2ª revisão de `(interval, ease)` é frágil; um contador explícito é determinístico e auditável.
- **`sm2.py` único (puro + I/O)**: mesmo padrão de `decay.py` (Fase 2); evita pulverização.
- **`grade_review` também bumpa `access_count`/`last_access`**: DoD explícita ("Acessos durante review também atualizam"). Implementado dentro de `grade_review`, sem chamar `get_note` (evita reindex duplicado).
- **`start_sm2()` retorna `next_review = today`**: nota inscrita aparece já na próxima fila — não precisa esperar para começar.
- **`add_note(study=True)` em `tool_add_note`, não em `new_note`**: evita import circular (`sm2.py → note.py → sm2.py`); a flag vive na borda MCP.
- **Ordering do queue**: `next_review ASC, ease ASC` — atrasadas primeiro; entre empatadas, cartas mais difíceis (ease menor) primeiro.

---

## Task 1: Extender modelo SM2 com `reps`

**Files:**
- Modify: `tools/brainiac/brainiac/core/models.py`
- Modify: `tools/brainiac/tests/core/test_models.py`

- [ ] **Step 1: Escrever testes failing em `test_models.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_models.py`:

```python
class TestSM2Reps:
    def test_reps_defaults_to_zero(self):
        sm2 = SM2(next_review=date(2026, 5, 21))
        assert sm2.reps == 0

    def test_reps_accepts_positive_int(self):
        sm2 = SM2(reps=3, next_review=date(2026, 5, 21))
        assert sm2.reps == 3

    def test_reps_rejects_negative(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SM2(reps=-1, next_review=date(2026, 5, 21))
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_models.py::TestSM2Reps -v --no-cov`
Expected: FAIL (`AttributeError: 'SM2' object has no attribute 'reps'` ou `ValidationError: extra fields not permitted`).

- [ ] **Step 3: Adicionar campo `reps` em `SM2`**

Substituir a classe `SM2` em `tools/brainiac/brainiac/core/models.py`:

```python
class SM2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ease: float = Field(default=2.5, ge=1.3)
    interval: int = Field(default=1, ge=1)
    reps: int = Field(default=0, ge=0)
    next_review: date
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_models.py -v --no-cov`
Expected: todos PASS (incluindo testes antigos `TestSM2.test_defaults` e `TestNoteFrontmatter.test_sm2_optional`).

- [ ] **Step 5: Rodar suite completa — não-regressão**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 125 PASS (mesmo número da Fase 2).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/models.py tools/brainiac/tests/core/test_models.py
git commit -m "feat(phase-3): SM2 model — add reps counter (default 0)"
```

---

## Task 2: `core/sm2.py` — função pura `grade()` + `start_sm2()`

**Files:**
- Create: `tools/brainiac/brainiac/core/sm2.py`
- Create: `tools/brainiac/tests/core/test_sm2.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_sm2.py`:

```python
from datetime import date, timedelta

import pytest

from brainiac.core.models import SM2


# --- start_sm2 ---

def test_start_sm2_defaults():
    from brainiac.core.sm2 import start_sm2
    today = date(2026, 5, 20)
    sm2 = start_sm2(today=today)
    assert sm2.ease == 2.5
    assert sm2.interval == 1
    assert sm2.reps == 0
    assert sm2.next_review == today


# --- grade pure function ---

def test_grade_rejects_out_of_range():
    from brainiac.core.sm2 import grade
    sm2 = SM2(next_review=date(2026, 5, 20))
    with pytest.raises(ValueError):
        grade(sm2, q=-1)
    with pytest.raises(ValueError):
        grade(sm2, q=6)


def test_grade_5_first_review_sets_interval_1_reps_1():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 20)
    sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=5, today=today)
    assert out.reps == 1
    assert out.interval == 1
    assert out.ease == pytest.approx(2.6, abs=1e-6)
    assert out.next_review == today + timedelta(days=1)


def test_grade_5_second_review_sets_interval_6_reps_2():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 21)
    sm2 = SM2(ease=2.6, interval=1, reps=1, next_review=today)
    out = grade(sm2, q=5, today=today)
    assert out.reps == 2
    assert out.interval == 6
    assert out.next_review == today + timedelta(days=6)


def test_grade_5_third_review_uses_new_ease_multiplier():
    from brainiac.core.sm2 import grade
    today = date(2026, 5, 27)
    sm2 = SM2(ease=2.6, interval=6, reps=2, next_review=today)
    out = grade(sm2, q=5, today=today)
    assert out.reps == 3
    # new_ease ≈ 2.7; interval = round(6 * 2.7) = 16
    assert out.interval == round(6 * out.ease)
    assert out.next_review == today + timedelta(days=out.interval)


def test_grade_0_resets_reps_and_interval():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.4, interval=16, reps=3, next_review=today)
    out = grade(sm2, q=0, today=today)
    assert out.reps == 0
    assert out.interval == 1
    # ease dropped: 2.4 + 0.1 - 5 * (0.08 + 5 * 0.02) = 2.4 + 0.1 - 0.9 = 1.6
    assert out.ease == pytest.approx(1.6, abs=1e-6)
    assert out.next_review == today + timedelta(days=1)


def test_grade_2_treated_as_failure():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.5, interval=6, reps=2, next_review=today)
    out = grade(sm2, q=2, today=today)
    assert out.reps == 0
    assert out.interval == 1
    assert out.ease < 2.5  # ease still drops on failure


def test_grade_3_passes_minimally():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=3, today=today)
    assert out.reps == 1  # success, reps++
    # ease: 2.5 + 0.1 - 2*(0.08+2*0.02) = 2.5 + 0.1 - 0.24 = 2.36
    assert out.ease == pytest.approx(2.36, abs=1e-6)


def test_ease_floor_at_1_3():
    from brainiac.core.sm2 import grade
    today = date(2026, 6, 1)
    sm2 = SM2(ease=1.3, interval=1, reps=0, next_review=today)
    out = grade(sm2, q=0, today=today)
    assert out.ease == pytest.approx(1.3, abs=1e-6)  # floor holds
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sm2.py -v --no-cov`
Expected: FAIL (`ModuleNotFoundError: No module named 'brainiac.core.sm2'`).

- [ ] **Step 3: Criar `core/sm2.py` com funções puras**

Criar `tools/brainiac/brainiac/core/sm2.py`:

```python
from __future__ import annotations

from datetime import date, timedelta

from brainiac.core.models import SM2

EASE_FLOOR: float = 1.3
INITIAL_EASE: float = 2.5
INITIAL_INTERVAL: int = 1


def start_sm2(today: date | None = None) -> SM2:
    """Build the initial SM2 state for a note entering review.

    next_review = today so the note appears in the next review_queue immediately.
    """
    today = today or date.today()
    return SM2(
        ease=INITIAL_EASE,
        interval=INITIAL_INTERVAL,
        reps=0,
        next_review=today,
    )


def grade(sm2: SM2, q: int, today: date | None = None) -> SM2:
    """Apply a grade (0-5) to an SM2 state. Returns the new state.

    Canonical SuperMemo-2:
      ease' = max(1.3, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
      q < 3      → reps' = 0, interval' = 1
      reps == 0  → reps' = 1, interval' = 1
      reps == 1  → reps' = 2, interval' = 6
      reps >= 2  → reps' = reps + 1, interval' = round(interval * ease')
      next_review = today + interval' days
    """
    if not 0 <= q <= 5:
        raise ValueError(f"grade must be 0-5, got {q}")
    today = today or date.today()

    new_ease = max(
        EASE_FLOOR,
        sm2.ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02),
    )

    if q < 3:
        new_reps = 0
        new_interval = 1
    elif sm2.reps == 0:
        new_reps = 1
        new_interval = 1
    elif sm2.reps == 1:
        new_reps = 2
        new_interval = 6
    else:
        new_reps = sm2.reps + 1
        new_interval = max(1, round(sm2.interval * new_ease))

    return SM2(
        ease=new_ease,
        interval=new_interval,
        reps=new_reps,
        next_review=today + timedelta(days=new_interval),
    )
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sm2.py -v --no-cov`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/sm2.py tools/brainiac/tests/core/test_sm2.py
git commit -m "feat(phase-3): sm2.py — pure grade() + start_sm2() (SuperMemo-2 canonical)"
```

---

## Task 3: `core/sm2.py` — `review_queue` + `grade_review` + `start_review` (I/O)

**Files:**
- Modify: `tools/brainiac/brainiac/core/sm2.py`
- Modify: `tools/brainiac/tests/core/test_sm2.py`

- [ ] **Step 1: Acrescentar testes failing em `test_sm2.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_sm2.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path


def _seed(
    root: Path,
    note_id: str,
    note_type: str = "semantic",
    sm2: SM2 | None = None,
    access_count: int = 0,
) -> None:
    """Create a .md note + index, optionally with sm2 enrolled."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm(note_id=note_id, note_type=note_type, access_count=access_count)
    if sm2 is not None:
        fm.sm2 = sm2
    p = note_path(root, note_id, note_type)
    write_note(p, fm, f"# {note_id}\n\nbody")
    conn = connect(index_db_path(root))
    index_note(conn, fm, f"# {note_id}\n\nbody", str(p.relative_to(root)))


# --- start_review ---

def test_start_review_enrolls_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.note import parse_note
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import start_review

    today = date(2026, 5, 20)
    _seed(fake_brainiac, "2026-05-20-study-me")
    conn = connect(index_db_path(fake_brainiac))
    sm2 = start_review(conn, fake_brainiac, "2026-05-20-study-me", today=today)

    assert sm2.next_review == today
    assert sm2.reps == 0
    p = fake_brainiac / "semanticMemory" / "2026-05-20-study-me.md"
    fm, _ = parse_note(p)
    assert fm.sm2 is not None
    assert fm.sm2.next_review == today


def test_start_review_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import start_review

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        start_review(conn, fake_brainiac, "2026-05-20-ghost")


# --- review_queue ---

def test_review_queue_empty_when_no_enrolled_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    _seed(fake_brainiac, "2026-05-20-not-enrolled")
    conn = connect(index_db_path(fake_brainiac))
    assert review_queue(conn, today=date(2026, 5, 20)) == []


def test_review_queue_returns_overdue_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    yesterday = date(2026, 5, 19)
    _seed(
        fake_brainiac,
        "2026-05-19-due",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=yesterday),
    )
    conn = connect(index_db_path(fake_brainiac))
    queue = review_queue(conn, today=today)
    assert len(queue) == 1
    assert queue[0]["id"] == "2026-05-19-due"
    assert queue[0]["days_overdue"] == 1


def test_review_queue_excludes_future_notes(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    future = date(2026, 5, 25)
    _seed(
        fake_brainiac,
        "2026-05-25-future",
        sm2=SM2(ease=2.5, interval=5, reps=2, next_review=future),
    )
    conn = connect(index_db_path(fake_brainiac))
    assert review_queue(conn, today=today) == []


def test_review_queue_ordered_by_urgency_then_ease(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import review_queue

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-15-old",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 15)),
    )
    _seed(
        fake_brainiac,
        "2026-05-19-hard",
        sm2=SM2(ease=1.5, interval=1, reps=0, next_review=date(2026, 5, 19)),
    )
    _seed(
        fake_brainiac,
        "2026-05-19-easy",
        sm2=SM2(ease=2.8, interval=1, reps=0, next_review=date(2026, 5, 19)),
    )
    conn = connect(index_db_path(fake_brainiac))
    queue = review_queue(conn, today=today)
    ids = [c["id"] for c in queue]
    # most overdue first, then within tie: lower ease first
    assert ids == ["2026-05-15-old", "2026-05-19-hard", "2026-05-19-easy"]


def test_review_queue_excludes_archived_notes(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.sm2 import review_queue
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    fm = make_fm("2026-05-19-arc", "semantic")
    fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
    p = note_path(fake_brainiac, "2026-05-19-arc", "semantic")
    write_note(p, fm, "# arc\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# arc\n\nbody", str(p.relative_to(fake_brainiac)), archived=True)
    assert review_queue(conn, today=today) == []


# --- grade_review ---

def test_grade_review_updates_sm2_in_frontmatter_and_db(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.note import parse_note
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-grade",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    new_sm2 = grade_review(conn, fake_brainiac, "2026-05-20-grade", q=5, today=today)

    assert new_sm2.reps == 1
    p = fake_brainiac / "semanticMemory" / "2026-05-20-grade.md"
    fm, _ = parse_note(p)
    assert fm.sm2.reps == 1
    assert fm.sm2.next_review == today + timedelta(days=1)


def test_grade_review_bumps_access_count_and_last_access(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-acc",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
        access_count=2,
    )
    conn = connect(index_db_path(fake_brainiac))
    grade_review(conn, fake_brainiac, "2026-05-20-acc", q=4, today=today)

    row = conn.execute(
        "SELECT access_count FROM notes WHERE id = ?", ("2026-05-20-acc",)
    ).fetchone()
    assert row[0] == 3


def test_grade_review_logs_reviewed_event(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-evt",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    grade_review(conn, fake_brainiac, "2026-05-20-evt", q=5, today=today)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    assert any(
        e["note_id"] == "2026-05-20-evt" and e["action"] == "reviewed"
        for e in entries
    )


def test_grade_review_raises_for_note_without_sm2(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(fake_brainiac, "2026-05-20-noenroll")  # no sm2
    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(ValueError):
        grade_review(conn, fake_brainiac, "2026-05-20-noenroll", q=5, today=today)


def test_grade_review_raises_for_unknown_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        grade_review(conn, fake_brainiac, "2026-05-20-ghost", q=5)


def test_grade_review_rejects_invalid_grade(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-bad",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(ValueError):
        grade_review(conn, fake_brainiac, "2026-05-20-bad", q=7, today=today)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sm2.py -v --no-cov -k "start_review or review_queue or grade_review"`
Expected: FAIL (`ImportError: cannot import name 'start_review' from 'brainiac.core.sm2'`).

- [ ] **Step 3: Acrescentar funções I/O em `core/sm2.py`**

Acrescentar ao final de `tools/brainiac/brainiac/core/sm2.py`:

```python

# --- I/O ---

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def start_review(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    today: date | None = None,
) -> SM2:
    """Enroll an existing note in spaced repetition. Sets initial SM2 state.

    Raises KeyError if note not found or archived.
    """
    from brainiac.core.events import log_event
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note

    today = today or date.today()
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active note not found: {note_id}")

    rel = row[0]
    full = root / rel
    fm, body = parse_note(full)
    fm.sm2 = start_sm2(today=today)
    write_note(full, fm, body)
    index_note(conn, fm, body, rel)

    log_event(
        root,
        note_id,
        "study_enrolled",
        f"next_review={fm.sm2.next_review.isoformat()}",
    )
    return fm.sm2


def review_queue(
    conn: sqlite3.Connection,
    today: date | None = None,
) -> list[dict]:
    """Return active enrolled notes due for review (next_review <= today).

    Ordered: most overdue first; ties broken by lower ease (harder cards first).
    """
    today = today or date.today()
    rows = conn.execute(
        """
        SELECT id, path, type, sm2_json
        FROM notes
        WHERE archived = 0 AND sm2_json IS NOT NULL
        ORDER BY json_extract(sm2_json, '$.next_review') ASC,
                 json_extract(sm2_json, '$.ease') ASC
        """,
    ).fetchall()

    out: list[dict] = []
    for note_id, rel_path, note_type, sm2_json in rows:
        sm2 = SM2.model_validate_json(sm2_json)
        if sm2.next_review > today:
            continue
        out.append({
            "id": note_id,
            "path": rel_path,
            "type": note_type,
            "ease": sm2.ease,
            "interval": sm2.interval,
            "reps": sm2.reps,
            "next_review": sm2.next_review.isoformat(),
            "days_overdue": (today - sm2.next_review).days,
        })
    return out


def grade_review(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    q: int,
    today: date | None = None,
) -> SM2:
    """Apply a grade to a note in review. Also bumps access_count / last_access.

    Raises KeyError if note not found or archived;
    ValueError if note has no sm2 state or q is out of range.
    """
    from brainiac.core.events import log_event
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note

    today = today or date.today()
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ? AND archived = 0",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Active note not found: {note_id}")

    rel = row[0]
    full = root / rel
    fm, body = parse_note(full)
    if fm.sm2 is None:
        raise ValueError(f"Note {note_id} is not enrolled in spaced repetition")

    new_sm2 = grade(fm.sm2, q, today=today)  # may raise ValueError on bad q

    fm.access_count += 1
    fm.last_access = datetime.now(timezone.utc)
    fm.sm2 = new_sm2

    write_note(full, fm, body)
    index_note(conn, fm, body, rel)

    log_event(
        root,
        note_id,
        "reviewed",
        f"q={q} ease={new_sm2.ease:.2f} interval={new_sm2.interval}d "
        f"next={new_sm2.next_review.isoformat()}",
    )
    return new_sm2
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sm2.py -v --no-cov`
Expected: todos PASS (9 pure + 12 I/O = 21 testes).

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/sm2.py tools/brainiac/tests/core/test_sm2.py
git commit -m "feat(phase-3): sm2.py — start_review + review_queue + grade_review (I/O)"
```

---

## Task 4: MCP tools `review_queue`, `grade_review`, `start_review` + `add_note(study=True)`

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`

- [ ] **Step 1: Acrescentar testes failing em `test_mcp_server.py`**

Acrescentar ao final de `tools/brainiac/tests/test_mcp_server.py`:

```python
from datetime import date


def test_tool_add_note_with_study_enrolls_sm2(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note
    from brainiac.core.note import parse_note

    tool_add_note(
        note_id="2026-05-20-study",
        note_type="semantic",
        title="Studyable",
        body="# Studyable\n\nfact",
        study=True,
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-study.md")
    assert fm.sm2 is not None
    assert fm.sm2.reps == 0
    assert fm.sm2.interval == 1


def test_tool_start_review_enrolls_existing_note(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_start_review

    tool_add_note(
        note_id="2026-05-20-existing",
        note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    result = tool_start_review("2026-05-20-existing")
    assert result["id"] == "2026-05-20-existing"
    assert result["next_review"]  # ISO string
    assert result["reps"] == 0


def test_tool_review_queue_returns_due_notes(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_review_queue, tool_start_review

    tool_add_note(
        note_id="2026-05-20-q1",
        note_type="semantic",
        title="x", body="# x\n\nbody",
        study=True,
    )
    queue = tool_review_queue()
    assert any(item["id"] == "2026-05-20-q1" for item in queue)


def test_tool_grade_review_updates_state(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_grade_review

    tool_add_note(
        note_id="2026-05-20-g",
        note_type="semantic",
        title="x", body="# x\n\nbody",
        study=True,
    )
    result = tool_grade_review("2026-05-20-g", grade=5)
    assert result["id"] == "2026-05-20-g"
    assert result["reps"] == 1
    assert result["interval"] == 1
    assert "next_review" in result
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov -k "study or review"`
Expected: FAIL (`cannot import name 'tool_review_queue'`, plus `study` unknown kwarg).

- [ ] **Step 3: Adicionar tools em `mcp_server.py`**

Em `tools/brainiac/brainiac/mcp_server.py`:

(a) Atualizar docstring no topo do arquivo:

```python
"""MCP server exposing brainiac tools via stdio.

Tools (10): add_note, recall, get_note, link, list_recent,
            consolidate_check, forget,
            review_queue, grade_review, start_review
"""
```

(b) Substituir `tool_add_note` (apenas as primeiras linhas) — adicionar parâmetro `study`:

```python
def tool_add_note(
    note_id: str,
    note_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    study: bool = False,
) -> dict:
    """Create a new note. Body should start with '# title'. If study=True, enrolls in SM-2."""
    root = find_root()
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

(c) Antes do bloco `# --- MCP server plumbing ---`, acrescentar:

```python
def tool_review_queue() -> list[dict]:
    """Return notes whose next_review <= today, ordered by urgency then ease."""
    from brainiac.core.sm2 import review_queue
    root = find_root()
    conn = connect(index_db_path(root))
    return review_queue(conn)


def tool_grade_review(note_id: str, grade: int) -> dict:
    """Apply a grade (0-5) to a review. Returns new SM2 state."""
    from brainiac.core.sm2 import grade_review
    root = find_root()
    conn = connect(index_db_path(root))
    sm2 = grade_review(conn, root, note_id, q=grade)
    return {
        "id": note_id,
        "ease": sm2.ease,
        "interval": sm2.interval,
        "reps": sm2.reps,
        "next_review": sm2.next_review.isoformat(),
    }


def tool_start_review(note_id: str) -> dict:
    """Enroll an existing note in spaced repetition."""
    from brainiac.core.sm2 import start_review
    root = find_root()
    conn = connect(index_db_path(root))
    sm2 = start_review(conn, root, note_id)
    return {
        "id": note_id,
        "ease": sm2.ease,
        "interval": sm2.interval,
        "reps": sm2.reps,
        "next_review": sm2.next_review.isoformat(),
    }
```

- [ ] **Step 4: Atualizar `_list_tools()` e `_DISPATCH`**

(a) Em `_list_tools()`, atualizar a entrada de `add_note` (adicionar `study` no schema):

Localizar:
```python
        Tool(
            name="add_note",
            description="Create a new brainiac note with frontmatter and index it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Format: YYYY-MM-DD-slug"},
                    "note_type": {"type": "string", "enum": ["episodic", "semantic", "working"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["note_id", "note_type", "title", "body"],
            },
        ),
```

Substituir por:
```python
        Tool(
            name="add_note",
            description="Create a new brainiac note with frontmatter and index it. study=true enrolls in SM-2 spaced repetition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Format: YYYY-MM-DD-slug"},
                    "note_type": {"type": "string", "enum": ["episodic", "semantic", "working"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "study": {"type": "boolean", "default": False},
                },
                "required": ["note_id", "note_type", "title", "body"],
            },
        ),
```

(b) Antes do `]` final em `_list_tools()`, acrescentar:

```python
        Tool(
            name="review_queue",
            description=(
                "Lista notas inscritas em SM-2 vencidas hoje. "
                "Ordenadas por urgência (mais atrasada primeiro), tiebreak por ease menor."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="grade_review",
            description=(
                "Aplica grade 0-5 a uma revisão SM-2. "
                "0-2 = falha (reseta interval=1); 3-5 = sucesso (avança). "
                "Também incrementa access_count/last_access."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string"},
                    "grade": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "required": ["note_id", "grade"],
            },
        ),
        Tool(
            name="start_review",
            description="Inscreve uma nota existente em revisão espaçada (cria bloco sm2).",
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
```

(c) Atualizar `_DISPATCH`:

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
}
```

- [ ] **Step 5: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov`
Expected: PASS (todos os 9 anteriores + 4 novos = 13).

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/tests/test_mcp_server.py
git commit -m "feat(phase-3): MCP tools review_queue + grade_review + start_review (+study param em add_note)"
```

---

## Task 5: CLI `brainiac review`

**Files:**
- Modify: `tools/brainiac/brainiac/cli.py`
- Modify: `tools/brainiac/tests/test_cli.py`

- [ ] **Step 1: Acrescentar testes failing em `test_cli.py`**

Acrescentar ao final de `tools/brainiac/tests/test_cli.py`:

```python
class TestReviewCommand:
    def test_review_empty_queue(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = CliRunner().invoke(main, ["review"])
        assert result.exit_code == 0
        assert "queue is empty" in result.output.lower() or "no reviews" in result.output.lower()

    def test_review_grades_single_note_via_input(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import write_note
        from brainiac.core.paths import index_db_path, note_path
        from brainiac.core.models import SM2
        from tests.conftest import make_fm

        today = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        fm = make_fm("2026-05-19-due-review", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-due-review", "semantic")
        write_note(p, fm, "# due\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# due\n\nbody", str(p.relative_to(fake_brainiac)))

        # grade=5 then quit (q)
        result = CliRunner().invoke(main, ["review"], input="5\n")
        assert result.exit_code == 0
        assert "2026-05-19-due-review" in result.output
        assert "Reviewed" in result.output or "reviewed" in result.output

    def test_review_skip_via_s(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import parse_note, write_note
        from brainiac.core.paths import index_db_path, note_path
        from brainiac.core.models import SM2
        from tests.conftest import make_fm

        fm = make_fm("2026-05-19-skip", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-skip", "semantic")
        write_note(p, fm, "# skip\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# skip\n\nbody", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["review"], input="s\n")
        assert result.exit_code == 0
        # state unchanged after skip
        fm_after, _ = parse_note(p)
        assert fm_after.sm2.reps == 0
        assert fm_after.sm2.next_review == date(2026, 5, 19)
```

Adicionar no topo de `tests/test_cli.py`, junto aos outros imports do bloco `from datetime`:

```python
from datetime import date
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov -k "Review"`
Expected: FAIL (`No such command 'review'`).

- [ ] **Step 3: Adicionar `review` em `cli.py`**

Antes do comando `mcp` em `tools/brainiac/brainiac/cli.py`, acrescentar:

```python
@main.command()
@click.option("--limit", type=int, default=20, help="Max notes to review in one session.")
def review(limit: int) -> None:
    """Interactive SM-2 review session. Grade 0-5, 's' to skip, 'q' to quit."""
    from brainiac.core.sm2 import grade_review, review_queue

    root = find_root()
    conn = connect(index_db_path(root))
    queue = review_queue(conn)

    if not queue:
        click.echo("Review queue is empty. Nothing due today.")
        return

    click.echo(f"{len(queue)} note(s) due. Showing up to {limit}.")
    reviewed = 0
    skipped = 0
    for item in queue[:limit]:
        click.echo("")
        click.echo(f"📝 {item['id']} ({item['type']})")
        click.echo(
            f"   reps={item['reps']} ease={item['ease']:.2f} "
            f"interval={item['interval']}d overdue={item['days_overdue']}d"
        )
        choice = click.prompt(
            "   Grade [0-5], s to skip, q to quit",
            default="s",
        )
        if choice == "q":
            break
        if choice == "s":
            skipped += 1
            continue
        try:
            g = int(choice)
        except ValueError:
            click.echo("   invalid input, skipping")
            skipped += 1
            continue
        if not 0 <= g <= 5:
            click.echo("   grade out of range, skipping")
            skipped += 1
            continue
        new_sm2 = grade_review(conn, root, item["id"], q=g)
        click.echo(
            f"   Reviewed → ease={new_sm2.ease:.2f} "
            f"interval={new_sm2.interval}d next={new_sm2.next_review.isoformat()}"
        )
        reviewed += 1

    click.echo("")
    click.echo(f"Session complete. Reviewed: {reviewed}, skipped: {skipped}")
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov`
Expected: PASS (todos os 7 anteriores + 3 novos = 10).

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_cli.py
git commit -m "feat(phase-3): CLI brainiac review — sessão interativa SM-2"
```

---

## Task 6: Skill `brainiac-review`

**Files:**
- Create: `.claude/skills/brainiac-review/SKILL.md`

- [ ] **Step 1: Criar a skill**

Criar `.claude/skills/brainiac-review/SKILL.md`:

```markdown
---
name: brainiac-review
description: Conduz uma sessão de revisão espaçada (SM-2) no brainiac. Use quando o usuário diz "vamos revisar", "tem nota para revisar?", "revisão diária", ou pede explicitamente o ciclo SM-2. Mostra notas vencidas, apresenta a frente (título/contexto), aguarda recall mental, então coleta grade 0-5 e atualiza estado.
---

# Brainiac Review

Sessão interativa de revisão espaçada baseada no algoritmo SuperMemo-2.

## Quando usar

- Usuário pede "revisão", "vamos revisar", "tem o que revisar?"
- Início de dia / fim de tarde — momentos previsíveis de estudo
- Após `brainiac stats` mostrar notas pendentes

## Fluxo

### 1. Buscar fila

Chame `review_queue()` via MCP. Retorna lista ordenada (mais atrasadas primeiro, ties por ease menor).

Se vazia: "Sem notas vencidas hoje. ✓" — encerra.

### 2. Para cada nota

Apresente em duas fases — **frente** primeiro, depois **verso**:

**Frente** (sem revelar o corpo):
```
📝 {id} ({type})
   Overdue: {days_overdue}d · Reps: {reps} · Ease: {ease:.2f}
   Tente recordar o conteúdo desta nota mentalmente.
   Pronto? (enter para ver)
```

Aguarde enter.

**Verso** (corpo completo):
- Chame `get_note(id)` via MCP — retorna body
- Mostre o corpo
- Pergunte: "Quão bem você recordou? [0=esqueci totalmente, 5=lembrei perfeito]"

### 3. Aplicar grade

Chame `grade_review(id, grade)` via MCP. O sistema responde com novo estado:
```
✓ ease={ease:.2f} interval={interval}d próxima={next_review}
```

### 4. Após a fila

Resumo final:
```
Sessão completa.
- Revisadas: X
- Puladas: Y
- Próxima fila: amanhã ({YYYY-MM-DD})
```

## Convenções de grade

| Grade | Significado |
|-------|-------------|
| 0 | Esqueci completamente |
| 1 | Reconheci a resposta ao ver, mas não lembrava |
| 2 | Lembrei parcialmente, com dificuldade |
| 3 | Lembrei com algum esforço (mínimo aprovado) |
| 4 | Lembrei bem, hesitação leve |
| 5 | Lembrei perfeitamente, imediato |

Grades 0-2 reagendam para amanhã (interval=1, reps=0). Grades 3-5 avançam o ciclo.

## Inscrever nota em estudo

Para começar a estudar uma nota existente:
- Chame `start_review(note_id)` via MCP
- A nota entra na fila imediatamente (next_review = hoje)

Para criar uma nova nota já em estudo:
- `add_note(..., study=True)` via MCP

## Não usar quando

- Usuário quer buscar algo → `/brainiac-recall`
- Usuário quer salvar nota → `/brainiac-capture`
- Usuário quer manutenção (decay/promote) → `/brainiac-housekeep`

## Exemplo

```
Usuário: "vamos revisar"

Você → review_queue()
  2 notas vencidas: 2026-05-15-bm25 (5d), 2026-05-19-dkg (1d)

"📝 2026-05-15-bm25 (semantic)
 Overdue: 5d · Reps: 1 · Ease: 2.30
 Tente recordar mentalmente. Pronto?"

→ usuário: "ok"

[mostra corpo via get_note]

"Quão bem você recordou? [0-5]"

→ usuário: "4"
→ grade_review("2026-05-15-bm25", 4)
  ease=2.30 → 2.30 (slight change), interval=2d, next=2026-05-22

"✓ ease=2.30 interval=2d próxima=2026-05-22

📝 2026-05-19-dkg (semantic)
 Overdue: 1d · Reps: 0 · Ease: 2.50
 ..."

[continua até esgotar fila ou usuário dizer parar]

"Sessão completa. Revisadas: 2, puladas: 0."
```

## Observações

- Reviews também bumpam `access_count` e `last_access` — alimentam consolidação automaticamente
- Grade 0-2 não destrói: reset apenas zera `reps` e `interval`; ease ainda diminui gradualmente
- `ease` mínimo é 1.3 — nota nunca fica "presa" abaixo desse floor
- Eventos registrados em `memoryTransfer/logs/events.jsonl` com action=`reviewed`
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/brainiac-review/SKILL.md
git commit -m "feat(phase-3): skill brainiac-review — sessão interativa SM-2"
```

---

## Task 7: Atualizar skill `brainiac-capture` com opção `study`

**Files:**
- Modify: `.claude/skills/brainiac-capture/SKILL.md`

- [ ] **Step 1: Acrescentar passo `study` no fluxo**

Em `.claude/skills/brainiac-capture/SKILL.md`, localizar o passo 5 (`Chamar `add_note``) e substituir os passos 4-5 por:

```markdown
4. **Tags**: 1-3 tags em kebab-case que ajudariam buscar isso depois.

5. **Decidir se entra em estudo (SM-2)**:
   - Pergunta ao usuário **apenas se a nota for `semantic`** e parecer um conceito memorizável (definição, fato, fórmula): "Quer revisar esta com SM-2? (s/n)"
   - Se sim: passar `study=True` para `add_note`
   - Para `episodic` e `working`, padrão é `study=False` — episódicos não são revisados (já tem timestamp narrativo); working ainda crus.

6. **Chamar `add_note`** via MCP com `note_id`, `note_type`, `title`, `body`, `tags`, e `study` quando aplicável.

7. **Confirmar ao usuário**: arquivo salvo em `<pasta>/<id>.md`. Se `study=True`, mencionar: "também adicionada à fila de revisão (próxima: hoje)".
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/brainiac-capture/SKILL.md
git commit -m "feat(phase-3): brainiac-capture skill — passo opcional study para SM-2"
```

---

## Task 8: Smoke E2E — DoD da Fase 3

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: Acrescentar testes DoD ao final de `test_smoke_e2e.py`**

Acrescentar:

```python
from datetime import date


def test_capture_with_study_creates_sm2_block(fake_brainiac, monkeypatch):
    """DoD: posso marcar nota como 'estudar' via capture (study=True)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note
    from brainiac.core.note import parse_note

    tool_add_note(
        note_id="2026-05-20-study-dod",
        note_type="semantic",
        title="Studyable",
        body="# Studyable\n\nfato relevante",
        study=True,
    )
    fm, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-study-dod.md")
    assert fm.sm2 is not None
    assert fm.sm2.reps == 0
    assert fm.sm2.interval == 1


def test_review_queue_ordered_by_urgency(fake_brainiac, monkeypatch):
    """DoD: /brainiac-review apresenta fila ordenada por urgência."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.models import SM2
    from brainiac.core.sm2 import review_queue
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    # 2 notas vencidas (uma há 5d, outra há 1d) e 1 futura
    for note_id, next_review in [
        ("2026-05-15-very-old", date(2026, 5, 15)),
        ("2026-05-19-recent", date(2026, 5, 19)),
        ("2026-05-25-future", date(2026, 5, 25)),
    ]:
        fm = make_fm(note_id, "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=next_review)
        p = note_path(fake_brainiac, note_id, "semantic")
        write_note(p, fm, f"# {note_id}\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, f"# {note_id}\n\nbody", str(p.relative_to(fake_brainiac)))

    queue = review_queue(conn, today=today)
    ids = [item["id"] for item in queue]
    assert ids == ["2026-05-15-very-old", "2026-05-19-recent"]
    assert "2026-05-25-future" not in ids


def test_grade_low_reschedules_to_tomorrow(fake_brainiac, monkeypatch):
    """DoD: grade 0-2 reagenda para amanhã."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.models import SM2
    from brainiac.core.sm2 import grade_review
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    fm = make_fm("2026-05-20-fail-dod", "semantic")
    fm.sm2 = SM2(ease=2.5, interval=16, reps=3, next_review=today)
    p = note_path(fake_brainiac, "2026-05-20-fail-dod", "semantic")
    write_note(p, fm, "# fail\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# fail\n\nbody", str(p.relative_to(fake_brainiac)))

    new_sm2 = grade_review(conn, fake_brainiac, "2026-05-20-fail-dod", q=1, today=today)
    assert new_sm2.interval == 1
    assert new_sm2.reps == 0
    assert (new_sm2.next_review - today).days == 1


def test_grade_5_expands_interval_correctly(fake_brainiac, monkeypatch):
    """DoD: grade 5 expande corretamente o intervalo (reps=1 → 2 com interval=6)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.models import SM2
    from brainiac.core.sm2 import grade_review
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    fm = make_fm("2026-05-20-pass-dod", "semantic")
    fm.sm2 = SM2(ease=2.5, interval=1, reps=1, next_review=today)
    p = note_path(fake_brainiac, "2026-05-20-pass-dod", "semantic")
    write_note(p, fm, "# pass\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# pass\n\nbody", str(p.relative_to(fake_brainiac)))

    new_sm2 = grade_review(conn, fake_brainiac, "2026-05-20-pass-dod", q=5, today=today)
    # reps=1 → 2; interval = 6 (segunda revisão canônica)
    assert new_sm2.reps == 2
    assert new_sm2.interval == 6
    assert (new_sm2.next_review - today).days == 6


def test_review_bumps_access_count_for_consolidation(fake_brainiac, monkeypatch):
    """DoD: acessos durante review também atualizam access_count/strength."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.models import SM2
    from brainiac.core.sm2 import grade_review
    from tests.conftest import make_fm

    today = date(2026, 5, 20)
    fm = make_fm("2026-05-20-acc-dod", "semantic", access_count=2)
    fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=today)
    p = note_path(fake_brainiac, "2026-05-20-acc-dod", "semantic")
    write_note(p, fm, "# acc\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# acc\n\nbody", str(p.relative_to(fake_brainiac)))

    grade_review(conn, fake_brainiac, "2026-05-20-acc-dod", q=4, today=today)

    row = conn.execute(
        "SELECT access_count FROM notes WHERE id = ?", ("2026-05-20-acc-dod",)
    ).fetchone()
    assert row[0] == 3  # bumped
```

- [ ] **Step 2: Rodar testes DoD**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_smoke_e2e.py -v --no-cov -k "study or review_queue_ordered or grade_low or grade_5_expands or review_bumps"`
Expected: 5 PASS.

- [ ] **Step 3: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (todos).

- [ ] **Step 4: Verificar cobertura do módulo `sm2.py`**

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.sm2 --cov-report=term-missing --ignore=tests/core/test_embeddings.py 2>&1 | tail -10`
Expected: cobertura ≥ 80% em `brainiac/core/sm2.py`.

- [ ] **Step 5: Commit final da Fase 3**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-3): smoke E2E — DoD SM-2 (queue urgency / grade low / grade 5 expand / access bump)"
```

---

## Definition of Done — Fase 3

Checklist final da spec (§5 Fase 3):

- [ ] Posso marcar nota como "estudar" via capture (`add_note(study=True)`) ou MCP (`start_review`) (test_smoke_e2e: `test_capture_with_study_creates_sm2_block`)
- [ ] `/brainiac-review` apresenta fila ordenada por urgência (test_smoke_e2e: `test_review_queue_ordered_by_urgency`)
- [ ] Grade 0-2 reagenda para amanhã (test_smoke_e2e: `test_grade_low_reschedules_to_tomorrow`)
- [ ] Grade 5 expande corretamente o intervalo (test_smoke_e2e: `test_grade_5_expands_interval_correctly`)
- [ ] Acessos durante review atualizam `access_count` (test_smoke_e2e: `test_review_bumps_access_count_for_consolidation`)
- [ ] Cobertura ≥ 80% em `sm2.py`

Após Fase 3 verde, gerar o plano da **Fase 4 — Working memory + tipos estritos** invocando `superpowers:writing-plans`.
