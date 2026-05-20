# Fase 5 — ACT-R Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um terceiro eixo cognitivo `activation A(t) = ln(Σ wᵢ·tᵢ⁻ᵈ)` em paralelo a `retention` (Ebbinghaus) e `sm2` (SuperMemo-2). Cada nota passa a ter histórico completo de acessos rastreado em uma tabela `accesses(note_id, ts, source, weight)`, alimentando recall ranking, gate de consolidação, e introspecção via `brainiac inspect <id>`.

**Architecture:** Novo módulo `core/activation.py` (pure `actr_activation()` + I/O `record_access`/`activation`/`activation_batch`/`access_history`). Tabela `accesses` append-only. 4 sources com pesos: `get`=1.0, `review`=1.0, `recall_hit`=0.3, `link_in`=0.5. Computação pure on-demand (sem cache). Config (`brainiac.toml`) ganha 3 campos opcionais. Integrações pontuais: `get_note`, `recall` (re-rank + hit log), `grade_review`, `add_link`, `consolidation_candidates` (borderline via activation), `run_decay` (log enriquecido). MCP ganha `inspect_note`; CLI ganha `brainiac inspect <id>`.

**Tech Stack:**
- Python stdlib: `math`, `statistics`, `datetime`, `sqlite3`
- Existente: `pydantic>=2`, `click>=8`, `mcp>=1.0`
- Sem novas dependências pip

---

## Mapa de arquivos (Fase 5)

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── activation.py         # CREATE: actr_activation + record_access + activation + activation_batch + access_history
│   │   ├── config.py             # MODIFY: +3 fields ACT-R
│   │   ├── index.py              # MODIFY: connect() migration + get_note/recall/add_link record access; recall re-rank
│   │   ├── decay.py              # MODIFY: archive log enriquecido com activation
│   │   ├── consolidate.py        # MODIFY: borderline via activation
│   │   └── sm2.py                # MODIFY: grade_review record access
│   ├── mcp_server.py             # MODIFY: tool_inspect_note + registrar
│   └── cli.py                    # MODIFY: comando inspect + stats expandido
└── tests/
    ├── core/
    │   ├── test_activation.py    # CREATE: pure + I/O tests
    │   ├── test_config.py        # MODIFY: validar 3 fields novos
    │   ├── test_index.py         # MODIFY: access logging + recall re-rank
    │   ├── test_consolidate.py   # MODIFY: borderline
    │   └── test_sm2.py           # MODIFY: grade_review access
    ├── test_mcp_server.py        # MODIFY: tool_inspect_note tests
    ├── test_cli.py               # MODIFY: inspect + stats tests
    └── test_smoke_e2e.py         # MODIFY: 4 DoD tests

.claude/skills/brainiac-recall/SKILL.md  # MODIFY: badge ativação alta
```

**Decisões arquiteturais:**
- **Pure on-demand**: sem cache de `activation` na tabela `notes`. Custo aceitável (~5ms / 100 events em SQLite). Permite consultas históricas livres.
- **Append-only `accesses`**: sem UPDATE/DELETE. Pruning fica para Phase 6+ se a tabela crescer.
- **Re-rank no `recall()` antes de gravar `recall_hit`**: evita circularidade. Query atual usa estado anterior; o novo hit afeta queries futuras.
- **Archive gate continua sendo `retention`**: ACT-R não é gate. Apenas informa o log de archive.
- **Borderline em `consolidate`**: union de duas queries (critério Phase 2 + nota com `access_count=2` mas `activation ≥ 1.5`).

---

## Task 1: Schema migration + Config fields

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/brainiac/core/config.py`
- Modify: `tools/brainiac/tests/core/test_config.py`

- [ ] **Step 1: Acrescentar testes failing em `test_config.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_config.py`:

```python
def test_config_has_actr_decay_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_decay == 0.5


def test_config_has_actr_recall_hit_weight_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_recall_hit_weight == 0.3


def test_config_has_actr_link_in_weight_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.actr_link_in_weight == 0.5


def test_config_reads_actr_fields_from_toml(fake_brainiac):
    from brainiac.core.config import load_config

    (fake_brainiac / "brainiac.toml").write_text(
        "actr_decay = 0.3\nactr_recall_hit_weight = 0.4\nactr_link_in_weight = 0.6\n",
        encoding="utf-8",
    )
    cfg = load_config(fake_brainiac)
    assert cfg.actr_decay == 0.3
    assert cfg.actr_recall_hit_weight == 0.4
    assert cfg.actr_link_in_weight == 0.6
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py -v --no-cov -k "actr"`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'actr_decay'`).

- [ ] **Step 3: Acrescentar 3 fields em `Config`**

Em `tools/brainiac/brainiac/core/config.py`, substituir a classe `Config`:

```python
@dataclass(frozen=True)
class Config:
    working_memory_limit: int = 9
    classifier_threshold: float = 0.3
    # ACT-R activation (Phase 5)
    actr_decay: float = 0.5
    actr_recall_hit_weight: float = 0.3
    actr_link_in_weight: float = 0.5
```

- [ ] **Step 4: Acrescentar teste failing para migration em `tests/core/test_index_vec.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_index_vec.py`:

```python
def test_connect_creates_accesses_table(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accesses)").fetchall()]
    assert set(cols) == {"id", "note_id", "ts", "source", "weight"}


def test_connect_creates_accesses_index(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(accesses)").fetchall()]
    assert "idx_accesses_note_ts" in indexes


def test_connect_idempotent_on_existing_accesses_table(fake_brainiac):
    """Running connect() twice on the same DB must not raise."""
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    db_path = index_db_path(fake_brainiac)
    conn1 = connect(db_path)
    conn1.close()
    conn2 = connect(db_path)  # must not raise
    cols = [r[1] for r in conn2.execute("PRAGMA table_info(accesses)").fetchall()]
    assert "note_id" in cols


def test_accesses_source_check_constraint(fake_brainiac):
    import sqlite3
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO accesses (note_id, ts, source, weight) VALUES (?, ?, ?, ?)",
            ("2026-05-20-x", "2026-05-20T10:00:00+00:00", "bogus_source", 1.0),
        )
```

- [ ] **Step 5: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v --no-cov -k "accesses"`
Expected: FAIL (table doesn't exist).

- [ ] **Step 6: Adicionar migration em `connect()`**

Em `tools/brainiac/brainiac/core/index.py`, localizar a função `connect()` e acrescentar o seguinte logo após o bloco que adiciona a coluna `archived` (mesmo padrão idempotente):

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
    # idempotent migration for existing DBs created before Phase 2
    try:
        conn.execute("ALTER TABLE notes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Phase 5: accesses table for ACT-R activation
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('get', 'review', 'recall_hit', 'link_in')),
            weight REAL NOT NULL DEFAULT 1.0,
            FOREIGN KEY (note_id) REFERENCES notes(id)
        );
        CREATE INDEX IF NOT EXISTS idx_accesses_note_ts ON accesses(note_id, ts);
    """)
    conn.commit()
    return conn
```

- [ ] **Step 7: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py tests/core/test_index_vec.py -v --no-cov`
Expected: todos PASS.

- [ ] **Step 8: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 204 + 7 novos = 211 PASS, sem regressões.

- [ ] **Step 9: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/brainiac/core/config.py tools/brainiac/tests/core/test_config.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-5): schema accesses table + Config ACT-R fields"
```

---

## Task 2: `core/activation.py` — pure `actr_activation()`

**Files:**
- Create: `tools/brainiac/brainiac/core/activation.py`
- Create: `tools/brainiac/tests/core/test_activation.py`

- [ ] **Step 1: Escrever testes failing**

Criar `tools/brainiac/tests/core/test_activation.py`:

```python
import math
from datetime import datetime, timedelta, timezone

import pytest


# --- Pure function actr_activation ---

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_actr_activation_empty_events_returns_negative_infinity():
    from brainiac.core.activation import actr_activation
    assert actr_activation([], NOW) == float("-inf")


def test_actr_activation_single_event_one_hour_ago_returns_zero():
    from brainiac.core.activation import actr_activation
    # 1h ago, weight 1.0, d=0.5: ln(1.0 * 1^-0.5) = ln(1) = 0
    events = [(NOW - timedelta(hours=1), 1.0)]
    assert actr_activation(events, NOW) == pytest.approx(0.0, abs=1e-6)


def test_actr_activation_more_recent_event_higher_activation():
    from brainiac.core.activation import actr_activation
    a_recent = actr_activation([(NOW - timedelta(minutes=10), 1.0)], NOW)
    a_old = actr_activation([(NOW - timedelta(hours=10), 1.0)], NOW)
    assert a_recent > a_old


def test_actr_activation_weight_scales_contribution():
    from brainiac.core.activation import actr_activation
    e = NOW - timedelta(hours=1)
    a_full = actr_activation([(e, 1.0)], NOW)
    a_half = actr_activation([(e, 0.5)], NOW)
    # ln(1*1^-0.5) = 0, ln(0.5*1^-0.5) = ln(0.5) ≈ -0.693
    assert a_full == pytest.approx(0.0, abs=1e-6)
    assert a_half == pytest.approx(math.log(0.5), abs=1e-6)


def test_actr_activation_decay_constant_changes_persistence():
    from brainiac.core.activation import actr_activation
    e = NOW - timedelta(hours=24)
    a_d03 = actr_activation([(e, 1.0)], NOW, d=0.3)
    a_d07 = actr_activation([(e, 1.0)], NOW, d=0.7)
    # higher d → faster decay → lower activation for the same old event
    assert a_d03 > a_d07


def test_actr_activation_event_at_now_uses_epsilon_no_div_error():
    from brainiac.core.activation import actr_activation
    # ts == now should not raise; treated as Δt = epsilon
    a = actr_activation([(NOW, 1.0)], NOW)
    assert a > 0  # epsilon^-0.5 is very large; ln of it is positive


def test_actr_activation_very_old_events_dont_underflow():
    from brainiac.core.activation import actr_activation
    # 1 year ago — should produce a small positive number, not crash
    a = actr_activation([(NOW - timedelta(days=365), 1.0)], NOW)
    assert math.isfinite(a)
    assert a < 0  # very small contribution → negative log


def test_actr_activation_many_events_sum_correctly():
    from brainiac.core.activation import actr_activation
    events = [(NOW - timedelta(hours=i + 1), 1.0) for i in range(50)]
    a = actr_activation(events, NOW)
    # expected = ln(sum_{i=1..50} i^-0.5)
    expected = math.log(sum(i ** -0.5 for i in range(1, 51)))
    assert a == pytest.approx(expected, abs=1e-6)


def test_actr_activation_negative_delta_t_clamped_to_epsilon():
    from brainiac.core.activation import actr_activation
    # event in the "future" (clock skew) — treated as epsilon, not crash
    a = actr_activation([(NOW + timedelta(seconds=10), 1.0)], NOW)
    assert math.isfinite(a)


def test_actr_activation_recent_frequency_beats_single_recent():
    from brainiac.core.activation import actr_activation
    a_many = actr_activation(
        [(NOW - timedelta(hours=h), 1.0) for h in [1, 2, 3, 4, 5]],
        NOW,
    )
    a_single = actr_activation([(NOW - timedelta(hours=1), 1.0)], NOW)
    assert a_many > a_single
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_activation.py -v --no-cov`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar `core/activation.py` (pure function only)**

Criar `tools/brainiac/brainiac/core/activation.py`:

```python
from __future__ import annotations

import math
from datetime import datetime

_EPSILON_HOURS = 1e-3  # avoid division by zero / very small Δt


def actr_activation(
    events: list[tuple[datetime, float]],
    now: datetime,
    d: float = 0.5,
) -> float:
    """ACT-R declarative memory activation.

    A(t) = ln( Σ wᵢ · (Δtᵢ)⁻ᵈ )

    where Δtᵢ = max(epsilon, (now - tᵢ)) in hours. Events at or beyond now
    are clamped to epsilon to avoid div-by-zero / negative time.

    Returns float('-inf') when events is empty (no trace yet).
    """
    if not events:
        return float("-inf")

    total = 0.0
    for ts, weight in events:
        delta_hours = (now - ts).total_seconds() / 3600.0
        if delta_hours < _EPSILON_HOURS:
            delta_hours = _EPSILON_HOURS
        total += weight * (delta_hours ** -d)
    return math.log(total)
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_activation.py -v --no-cov`
Expected: 10 PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 211 + 10 = 221 PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/activation.py tools/brainiac/tests/core/test_activation.py
git commit -m "feat(phase-5): activation.py — pure actr_activation() (ACT-R declarative memory)"
```

---

## Task 3: `core/activation.py` — I/O layer

**Files:**
- Modify: `tools/brainiac/brainiac/core/activation.py`
- Modify: `tools/brainiac/tests/core/test_activation.py`

- [ ] **Step 1: Acrescentar testes failing**

Acrescentar ao final de `tools/brainiac/tests/core/test_activation.py`:

```python
# --- I/O: record_access ---

def test_record_access_inserts_row_with_default_weight(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-a", "get", now=NOW)
    row = conn.execute(
        "SELECT note_id, source, weight FROM accesses WHERE note_id = ?",
        ("2026-05-20-a",),
    ).fetchone()
    assert row[0] == "2026-05-20-a"
    assert row[1] == "get"
    assert row[2] == 1.0


def test_record_access_respects_explicit_weight(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-b", "recall_hit", now=NOW, weight=0.75)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-b",)
    ).fetchone()
    assert row[0] == 0.75


def test_record_access_uses_config_weight_for_recall_hit(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    config = Config(actr_recall_hit_weight=0.42)
    record_access(conn, "2026-05-20-c", "recall_hit", now=NOW, config=config)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-c",)
    ).fetchone()
    assert row[0] == 0.42


def test_record_access_uses_config_weight_for_link_in(fake_brainiac):
    from brainiac.core.activation import record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    config = Config(actr_link_in_weight=0.65)
    record_access(conn, "2026-05-20-d", "link_in", now=NOW, config=config)
    row = conn.execute(
        "SELECT weight FROM accesses WHERE note_id = ?", ("2026-05-20-d",)
    ).fetchone()
    assert row[0] == 0.65


def test_record_access_rejects_invalid_source(fake_brainiac):
    import sqlite3
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(sqlite3.IntegrityError):
        record_access(conn, "2026-05-20-e", "bogus", now=NOW)


# --- I/O: activation ---

def test_activation_zero_events_returns_neg_infinity(fake_brainiac):
    from brainiac.core.activation import activation
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    assert activation(conn, "2026-05-20-never", now=NOW) == float("-inf")


def test_activation_reads_full_history(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in [1, 2, 3]:
        record_access(conn, "2026-05-20-hist", "get", now=NOW - timedelta(hours=h))
    a = activation(conn, "2026-05-20-hist", now=NOW)
    expected = math.log(1.0 ** -0.5 + 2.0 ** -0.5 + 3.0 ** -0.5)
    assert a == pytest.approx(expected, abs=1e-6)


def test_activation_uses_config_decay(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.config import Config
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-d2", "get", now=NOW - timedelta(hours=10))
    a_d03 = activation(conn, "2026-05-20-d2", now=NOW, config=Config(actr_decay=0.3))
    a_d07 = activation(conn, "2026-05-20-d2", now=NOW, config=Config(actr_decay=0.7))
    assert a_d03 > a_d07


def test_activation_now_injectable_for_determinism(fake_brainiac):
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-det", "get", now=NOW - timedelta(hours=1))
    a1 = activation(conn, "2026-05-20-det", now=NOW)
    a2 = activation(conn, "2026-05-20-det", now=NOW)
    assert a1 == a2  # deterministic when now is fixed


# --- I/O: activation_batch ---

def test_activation_batch_single_query_results_match_individual_calls(fake_brainiac):
    from brainiac.core.activation import activation, activation_batch, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for note_id, hours in [("2026-05-20-a", [1, 5]), ("2026-05-20-b", [2]), ("2026-05-20-c", [10, 20, 30])]:
        for h in hours:
            record_access(conn, note_id, "get", now=NOW - timedelta(hours=h))

    batch = activation_batch(conn, ["2026-05-20-a", "2026-05-20-b", "2026-05-20-c"], now=NOW)
    for nid in ["2026-05-20-a", "2026-05-20-b", "2026-05-20-c"]:
        assert batch[nid] == pytest.approx(activation(conn, nid, now=NOW), abs=1e-9)


def test_activation_batch_handles_notes_without_events(fake_brainiac):
    from brainiac.core.activation import activation_batch
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    batch = activation_batch(conn, ["2026-05-20-no-events"], now=NOW)
    assert batch["2026-05-20-no-events"] == float("-inf")


def test_activation_batch_empty_input_returns_empty_dict(fake_brainiac):
    from brainiac.core.activation import activation_batch
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    assert activation_batch(conn, [], now=NOW) == {}


# --- I/O: access_history ---

def test_access_history_ordered_by_ts_desc(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in [5, 1, 3]:
        record_access(conn, "2026-05-20-h", "get", now=NOW - timedelta(hours=h))
    hist = access_history(conn, "2026-05-20-h")
    ts_values = [h["ts"] for h in hist]
    assert ts_values == sorted(ts_values, reverse=True)  # DESC


def test_access_history_respects_limit(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    for h in range(20):
        record_access(conn, "2026-05-20-many", "get", now=NOW - timedelta(hours=h))
    hist = access_history(conn, "2026-05-20-many", limit=5)
    assert len(hist) == 5


def test_access_history_returns_required_fields(fake_brainiac):
    from brainiac.core.activation import access_history, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-f", "review", now=NOW)
    hist = access_history(conn, "2026-05-20-f")
    assert len(hist) == 1
    assert set(hist[0].keys()) >= {"ts", "source", "weight"}
    assert hist[0]["source"] == "review"
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_activation.py -v --no-cov`
Expected: 10 PASS (pure) + 14 FAIL (I/O — `cannot import 'record_access'`).

- [ ] **Step 3: Acrescentar I/O em `core/activation.py`**

Acrescentar ao final de `tools/brainiac/brainiac/core/activation.py`:

```python

# --- I/O ---

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from brainiac.core.config import Config


_SOURCE_LITERAL_DEFAULTS = {
    "get": 1.0,
    "review": 1.0,
}


def _resolve_weight(source: str, config: Config, explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    if source in _SOURCE_LITERAL_DEFAULTS:
        return _SOURCE_LITERAL_DEFAULTS[source]
    if source == "recall_hit":
        return config.actr_recall_hit_weight
    if source == "link_in":
        return config.actr_link_in_weight
    raise ValueError(f"Unknown access source: {source}")


def record_access(
    conn: sqlite3.Connection,
    note_id: str,
    source: str,
    *,
    now: datetime | None = None,
    weight: float | None = None,
    config: Config | None = None,
) -> None:
    """Insert one row into accesses. weight defaults derived from source via Config."""
    now = now or datetime.now(timezone.utc)
    config = config or Config()
    resolved = _resolve_weight(source, config, weight)
    conn.execute(
        "INSERT INTO accesses (note_id, ts, source, weight) VALUES (?, ?, ?, ?)",
        (note_id, now.isoformat(), source, resolved),
    )
    conn.commit()


def activation(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> float:
    """Current A(t) for a note, reading full accesses history."""
    now = now or datetime.now(timezone.utc)
    config = config or Config()
    rows = conn.execute(
        "SELECT ts, weight FROM accesses WHERE note_id = ?",
        (note_id,),
    ).fetchall()
    events = [(datetime.fromisoformat(r[0]), r[1]) for r in rows]
    return actr_activation(events, now, d=config.actr_decay)


def activation_batch(
    conn: sqlite3.Connection,
    note_ids: list[str],
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> dict[str, float]:
    """Compute A(t) for many notes in one query. Notes with no events → -inf."""
    if not note_ids:
        return {}
    now = now or datetime.now(timezone.utc)
    config = config or Config()

    placeholders = ",".join("?" * len(note_ids))
    rows = conn.execute(
        f"SELECT note_id, ts, weight FROM accesses WHERE note_id IN ({placeholders}) ORDER BY note_id, ts",
        note_ids,
    ).fetchall()

    grouped: dict[str, list[tuple[datetime, float]]] = {nid: [] for nid in note_ids}
    for nid, ts, w in rows:
        grouped[nid].append((datetime.fromisoformat(ts), w))

    return {nid: actr_activation(events, now, d=config.actr_decay) for nid, events in grouped.items()}


def access_history(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Last N events for a note, ordered by ts DESC. [{ts, source, weight}]."""
    rows = conn.execute(
        "SELECT ts, source, weight FROM accesses WHERE note_id = ? ORDER BY ts DESC LIMIT ?",
        (note_id, limit),
    ).fetchall()
    return [{"ts": r[0], "source": r[1], "weight": r[2]} for r in rows]
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_activation.py -v --no-cov`
Expected: 24 PASS (10 pure + 14 I/O).

- [ ] **Step 5: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 221 + 14 = 235 PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/activation.py tools/brainiac/tests/core/test_activation.py
git commit -m "feat(phase-5): activation.py I/O — record_access + activation + activation_batch + access_history"
```

---

## Task 4: Integrar `record_access` em `get_note`, `grade_review`, `add_link`

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/brainiac/core/sm2.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`
- Modify: `tools/brainiac/tests/core/test_sm2.py`

- [ ] **Step 1: Acrescentar testes failing em `test_index_vec.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_index_vec.py`:

```python
def test_get_note_records_access_source_get(fake_brainiac, embedder_stub):
    from brainiac.core.index import connect, index_note, get_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-gn", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-gn", "semantic")
    write_note(p, fm, "# x\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# x\n\nbody", str(p.relative_to(fake_brainiac)))

    get_note(conn, fake_brainiac, "2026-05-20-gn")
    row = conn.execute(
        "SELECT source FROM accesses WHERE note_id = ?", ("2026-05-20-gn",)
    ).fetchone()
    assert row[0] == "get"


def test_add_link_records_access_source_link_in_on_destination(fake_brainiac, embedder_stub):
    from brainiac.core.index import add_link, connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    for nid in ["2026-05-20-src", "2026-05-20-dst"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, f"# {nid}\n\nbody")
        index_note(conn, fm, f"# {nid}\n\nbody", str(p.relative_to(fake_brainiac)))

    add_link(conn, fake_brainiac, "2026-05-20-src", "2026-05-20-dst")
    row = conn.execute(
        "SELECT source FROM accesses WHERE note_id = ?", ("2026-05-20-dst",)
    ).fetchone()
    assert row[0] == "link_in"
```

- [ ] **Step 2: Acrescentar teste failing em `test_sm2.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_sm2.py`:

```python
def test_grade_review_records_access_source_review(fake_brainiac):
    from datetime import date
    from brainiac.core.index import connect
    from brainiac.core.models import SM2
    from brainiac.core.paths import index_db_path
    from brainiac.core.sm2 import grade_review

    today = date(2026, 5, 20)
    _seed(
        fake_brainiac,
        "2026-05-20-rev-acc",
        sm2=SM2(ease=2.5, interval=1, reps=0, next_review=today),
    )
    conn = connect(index_db_path(fake_brainiac))
    grade_review(conn, fake_brainiac, "2026-05-20-rev-acc", q=4, today=today)
    row = conn.execute(
        "SELECT source FROM accesses WHERE note_id = ?", ("2026-05-20-rev-acc",)
    ).fetchone()
    assert row[0] == "review"
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py tests/core/test_sm2.py -v --no-cov -k "records_access"`
Expected: FAIL (no rows in accesses table).

- [ ] **Step 4: Acrescentar `record_access` em `get_note` (index.py)**

Em `tools/brainiac/brainiac/core/index.py`, localizar a função `get_note()`. Logo após `index_note(conn, fm, body, rel_path)` e antes do `return`, acrescentar:

```python
    from brainiac.core.activation import record_access
    record_access(conn, fm.id, "get")
```

- [ ] **Step 5: Acrescentar `record_access` em `add_link` (index.py)**

Em `tools/brainiac/brainiac/core/index.py`, localizar a função `add_link()`. Após o INSERT do link e o commit, acrescentar:

```python
    from brainiac.core.activation import record_access
    record_access(conn, dst, "link_in")
```

(Se `add_link` não tinha commit explícito, `record_access` já comita internamente — sem duplicidade.)

- [ ] **Step 6: Acrescentar `record_access` em `grade_review` (sm2.py)**

Em `tools/brainiac/brainiac/core/sm2.py`, localizar a função `grade_review()`. Após `index_note(conn, fm, body, rel)` + `conn.commit()` e antes de `log_event(...)`, acrescentar:

```python
    from brainiac.core.activation import record_access
    record_access(conn, note_id, "review")
```

- [ ] **Step 7: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py tests/core/test_sm2.py -v --no-cov`
Expected: PASS (incluindo 3 novos).

- [ ] **Step 8: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 235 + 3 = 238 PASS.

- [ ] **Step 9: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/brainiac/core/sm2.py tools/brainiac/tests/core/test_index_vec.py tools/brainiac/tests/core/test_sm2.py
git commit -m "feat(phase-5): integrate record_access into get_note + grade_review + add_link"
```

---

## Task 5: Integrar `activation` no `recall()` — re-ranking + hit logging

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`

- [ ] **Step 1: Acrescentar testes failing em `test_index_vec.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_index_vec.py`:

```python
def test_recall_records_recall_hit_for_each_top_k_hit(fake_brainiac, embedder_stub):
    from brainiac.core.index import connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    for nid in ["2026-05-20-r1", "2026-05-20-r2"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, f"# {nid}\n\nshared keyword body")
        index_note(conn, fm, f"# {nid}\n\nshared keyword body", str(p.relative_to(fake_brainiac)))

    hits = recall(conn, "shared keyword", k=5)
    hit_ids = {h["id"] for h in hits}

    rows = conn.execute(
        "SELECT note_id, source FROM accesses WHERE source = 'recall_hit'"
    ).fetchall()
    recorded_ids = {r[0] for r in rows}
    assert hit_ids.issubset(recorded_ids)


def test_recall_ranking_boosts_more_activated_notes(fake_brainiac, embedder_stub):
    """Two notes equally semantically similar; the one with more recent accesses ranks first."""
    from datetime import datetime, timedelta, timezone
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    conn = connect(index_db_path(fake_brainiac))
    body = "# x\n\nDKG protocol distributed key generation"
    for nid in ["2026-05-20-cold", "2026-05-20-hot"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, body)
        index_note(conn, fm, body, str(p.relative_to(fake_brainiac)))

    # Seed "hot" with 5 recent accesses; "cold" gets nothing
    for h in [1, 2, 3, 4, 5]:
        record_access(conn, "2026-05-20-hot", "get", now=now - timedelta(hours=h))

    hits = recall(conn, "DKG protocol", k=5)
    ids = [h["id"] for h in hits]
    # "hot" comes first thanks to activation boost
    assert ids.index("2026-05-20-hot") < ids.index("2026-05-20-cold")
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v --no-cov -k "recall_hit or ranking_boosts"`
Expected: FAIL (re-ranking not applied; no recall_hit records).

- [ ] **Step 3: Modificar `recall()` em `index.py` — adicionar re-rank + hit logging**

Em `tools/brainiac/brainiac/core/index.py`, localizar a função `recall()`. Antes do `return results[:k]` final, substituir o trecho final por:

```python
    # Phase 5: combine semantic score with ACT-R activation (z-score normalized per query)
    import statistics
    from brainiac.core.activation import activation_batch, record_access

    candidate_ids = list(scored.keys())
    acts = activation_batch(conn, candidate_ids)
    finite_vals = [v for v in acts.values() if v != float("-inf")]
    mean = statistics.fmean(finite_vals) if finite_vals else 0.0
    stdev = statistics.stdev(finite_vals) if len(finite_vals) > 1 else 1.0

    ALPHA, BETA = 0.7, 0.3
    for nid, item in scored.items():
        a = acts.get(nid, float("-inf"))
        a_norm = 0.0 if a == float("-inf") else (a - mean) / (stdev or 1.0)
        item["score"] = ALPHA * item["score"] + BETA * a_norm

    results = sorted(scored.values(), key=lambda r: r["score"], reverse=True)
    top_k = results[:k]

    # Record recall_hit AFTER reorder (the current query already saw the previous state)
    for hit in top_k:
        record_access(conn, hit["id"], "recall_hit")

    return top_k
```

(Substitui a linha `results = sorted(scored.values(), key=lambda r: r["score"], reverse=True)` e `return results[:k]` originais. Resto da função fica idêntico.)

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_index_vec.py -v --no-cov`
Expected: PASS (incluindo os 2 novos).

- [ ] **Step 5: Rodar suite completa — atenção a possíveis regressões**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 238 + 2 = 240 PASS. Se algum teste de recall pré-existente quebrar por causa do re-rank, investigar — pode ser que notas sem accesses ficaram com `a_norm = 0` que é neutro mas, em algum teste, mudou ordem por causa de stdev/mean.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-5): recall — combine semantic + activation (z-score) + log recall_hit"
```

---

## Task 6: Borderline em `consolidate` + log enriquecido em `decay`

**Files:**
- Modify: `tools/brainiac/brainiac/core/consolidate.py`
- Modify: `tools/brainiac/brainiac/core/decay.py`
- Modify: `tools/brainiac/tests/core/test_consolidate.py`
- Modify: `tools/brainiac/tests/core/test_decay.py`

- [ ] **Step 1: Acrescentar teste failing em `test_consolidate.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_consolidate.py`:

```python
def test_consolidation_candidates_includes_borderline_high_activation(fake_brainiac):
    """Borderline (access_count=2, fan_in≥1) é promovido se activation alta."""
    from datetime import datetime, timedelta, timezone
    from brainiac.core.activation import record_access
    from brainiac.core.consolidate import consolidation_candidates
    from brainiac.core.index import connect

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    # Borderline: access_count=2 only, but with link_in + frequent accesses
    _seed(
        fake_brainiac,
        "2026-05-18-border",
        "working",
        access_count=2,
        last_access=recent,
        links_from=["2026-05-15-linker"],
    )
    conn = connect(index_db_path(fake_brainiac))
    # Boost activation way above 1.5 threshold
    for h in [1, 2, 3, 4, 5, 6, 7]:
        record_access(conn, "2026-05-18-border", "get", now=now - timedelta(hours=h))

    candidates = consolidation_candidates(conn, now=now)
    ids = [c["id"] for c in candidates]
    assert "2026-05-18-border" in ids
```

- [ ] **Step 2: Acrescentar teste failing em `test_decay.py`**

Acrescentar ao final de `tools/brainiac/tests/core/test_decay.py`:

```python
def test_archive_log_includes_activation(fake_brainiac):
    """When run_decay archives, a follow-up archive_detail event captures activation + retention."""
    from datetime import datetime, timezone
    from brainiac.core.activation import record_access
    from brainiac.core.decay import run_decay
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    old_access = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)

    _seed_note(fake_brainiac, "2026-03-21-arc-log", "semantic",
               last_access=old_access, access_count=0)
    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-03-21-arc-log", "get", now=old_access)

    run_decay(conn, fake_brainiac, now=now)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    archive_details = [
        e for e in entries
        if e["note_id"] == "2026-03-21-arc-log" and e["action"] == "archive_detail"
    ]
    assert len(archive_details) == 1
    assert "activation" in archive_details[0]["detail"]
    assert "retention" in archive_details[0]["detail"]
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_consolidate.py tests/core/test_decay.py -v --no-cov -k "borderline or archive_log_includes_activation"`
Expected: FAIL.

- [ ] **Step 4: Modificar `consolidation_candidates` em `consolidate.py`**

Em `tools/brainiac/brainiac/core/consolidate.py`, substituir o corpo de `consolidation_candidates`:

```python
def consolidation_candidates(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    window_days: int = 7,
    *,
    activation_threshold: float = 1.5,
) -> list[dict]:
    """Return working notes ready for promotion.

    Primary criteria (Phase 2): type='working', archived=0, access_count >= 3,
    last_access within window_days, fan_in >= 1.

    Borderline (Phase 5): access_count = 2 + fan_in >= 1 + activation >= threshold.
    """
    from brainiac.core.activation import activation_batch

    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=window_days)).isoformat()

    primary_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.access_count >= 3
          AND n.last_access >= ?
        GROUP BY n.id
        HAVING fan_in >= 1
        ORDER BY n.access_count DESC
        """,
        (cutoff,),
    ).fetchall()

    out = [
        {
            "id": r[0], "path": r[1], "access_count": r[2],
            "last_access": r[3], "fan_in": r[4],
            "suggested_type": "semantic",
        }
        for r in primary_rows
    ]
    seen = {c["id"] for c in out}

    # Borderline path
    borderline_rows = conn.execute(
        """
        SELECT n.id, n.path, n.access_count, n.last_access,
               COUNT(l.src) as fan_in
        FROM notes n
        LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
        WHERE n.type = 'working'
          AND n.archived = 0
          AND n.access_count = 2
          AND n.last_access >= ?
        GROUP BY n.id
        HAVING fan_in >= 1
        """,
        (cutoff,),
    ).fetchall()

    if borderline_rows:
        borderline_ids = [r[0] for r in borderline_rows if r[0] not in seen]
        if borderline_ids:
            acts = activation_batch(conn, borderline_ids, now=now)
            for r in borderline_rows:
                if r[0] in seen:
                    continue
                if acts.get(r[0], float("-inf")) >= activation_threshold:
                    out.append({
                        "id": r[0], "path": r[1], "access_count": r[2],
                        "last_access": r[3], "fan_in": r[4],
                        "suggested_type": "semantic",
                    })

    return out
```

- [ ] **Step 5: Modificar `run_decay` em `decay.py` — enriquecer log de archive**

Em `tools/brainiac/brainiac/core/decay.py`, localizar o trecho que chama `archive_note` dentro de `run_decay`. Substituir para enriquecer o detail do log com activation:

Localizar:
```python
    if not dry_run:
        conn.commit()
        for note_id in to_archive:
            try:
                archive_note(conn, root, note_id, now=now)
                stats["archived"] += 1
            except (KeyError, FileNotFoundError):
                pass
```

Substituir por:
```python
    if not dry_run:
        conn.commit()
        from brainiac.core.activation import activation as compute_activation
        from brainiac.core.events import log_event
        for note_id, retention_val in [(nid, ret_map[nid]) for nid in to_archive if nid in ret_map]:
            try:
                archive_note(conn, root, note_id, now=now)
                act = compute_activation(conn, note_id, now=now)
                log_event(
                    root, note_id, "archive_detail",
                    f"retention={retention_val:.3f} activation={act:.3f}",
                )
                stats["archived"] += 1
            except (KeyError, FileNotFoundError):
                pass
```

E também adicionar acima do loop principal a coleta de `ret_map` (no loop de update de strength):

Localizar:
```python
    for note_id, last_access_str, access_count in rows:
        last_access = datetime.fromisoformat(last_access_str)
        new_s = updated_strength(last_access, access_count, now=now)

        if not dry_run:
            conn.execute(
                "UPDATE notes SET strength = ? WHERE id = ?",
                (new_s, note_id),
            )
            stats["updated"] += 1

        if new_s < ARCHIVE_THRESHOLD:
            to_archive.append(note_id)
```

Substituir por:
```python
    ret_map: dict[str, float] = {}
    for note_id, last_access_str, access_count in rows:
        last_access = datetime.fromisoformat(last_access_str)
        new_s = updated_strength(last_access, access_count, now=now)
        ret_map[note_id] = new_s

        if not dry_run:
            conn.execute(
                "UPDATE notes SET strength = ? WHERE id = ?",
                (new_s, note_id),
            )
            stats["updated"] += 1

        if new_s < ARCHIVE_THRESHOLD:
            to_archive.append(note_id)
```

- [ ] **Step 6: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_consolidate.py tests/core/test_decay.py -v --no-cov`
Expected: PASS (incluindo os 2 novos).

- [ ] **Step 7: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 240 + 2 = 242 PASS.

- [ ] **Step 8: Commit**

```bash
git add tools/brainiac/brainiac/core/consolidate.py tools/brainiac/brainiac/core/decay.py tools/brainiac/tests/core/test_consolidate.py tools/brainiac/tests/core/test_decay.py
git commit -m "feat(phase-5): consolidate borderline via activation + decay log enriquecido"
```

---

## Task 7: MCP tool `inspect_note` + CLI `brainiac inspect` + `stats` expandido + skill update

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/brainiac/cli.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`
- Modify: `tools/brainiac/tests/test_cli.py`
- Modify: `.claude/skills/brainiac-recall/SKILL.md`

- [ ] **Step 1: Acrescentar testes failing em `test_mcp_server.py`**

Acrescentar ao final de `tools/brainiac/tests/test_mcp_server.py`:

```python
def test_tool_inspect_note_returns_all_three_axes(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_inspect_note

    tool_add_note(
        note_id="2026-05-20-insp", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    result = tool_inspect_note("2026-05-20-insp")
    assert result["id"] == "2026-05-20-insp"
    assert "activation" in result
    assert "strength" in result
    assert "sm2" in result
    assert "recent_accesses" in result


def test_tool_inspect_note_includes_recent_accesses(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_get_note, tool_inspect_note

    tool_add_note(
        note_id="2026-05-20-h2", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    tool_get_note("2026-05-20-h2")  # records 'get'
    result = tool_inspect_note("2026-05-20-h2")
    assert len(result["recent_accesses"]) >= 1
    sources = {a["source"] for a in result["recent_accesses"]}
    assert "get" in sources


def test_tool_inspect_note_raises_for_unknown_note(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_inspect_note

    with pytest.raises(KeyError):
        tool_inspect_note("2026-05-20-ghost-insp")
```

- [ ] **Step 2: Acrescentar testes failing em `test_cli.py`**

Acrescentar ao final de `tools/brainiac/tests/test_cli.py`:

```python
class TestInspectCommand:
    def test_inspect_command_outputs_three_axes(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import write_note
        from brainiac.core.paths import index_db_path, note_path
        from tests.conftest import make_fm

        fm = make_fm("2026-05-20-cli-insp", "semantic")
        p = note_path(fake_brainiac, "2026-05-20-cli-insp", "semantic")
        write_note(p, fm, "# x\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# x\n\nbody", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["inspect", "2026-05-20-cli-insp"])
        assert result.exit_code == 0
        assert "retention" in result.output.lower()
        assert "activation" in result.output.lower()
        assert "sm2" in result.output.lower()

    def test_inspect_command_raises_for_unknown_note(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = CliRunner().invoke(main, ["inspect", "2026-05-20-cli-ghost"])
        assert result.exit_code != 0


def test_stats_command_shows_event_count_and_top_activations(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-stat-act", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-stat-act", "semantic")
    write_note(p, fm, "# x\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# x\n\nbody", str(p.relative_to(fake_brainiac)))
    for _ in range(3):
        record_access(conn, "2026-05-20-stat-act", "get")

    result = CliRunner().invoke(main, ["stats"])
    assert result.exit_code == 0
    assert "events" in result.output.lower()
    assert "activation" in result.output.lower()
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py tests/test_cli.py -v --no-cov -k "inspect or stats_command_shows_event"`
Expected: FAIL (`cannot import name 'tool_inspect_note'`, `No such command 'inspect'`).

- [ ] **Step 4: Adicionar `tool_inspect_note` em `mcp_server.py`**

Em `tools/brainiac/brainiac/mcp_server.py`, atualizar docstring no topo:

```python
"""MCP server exposing brainiac tools via stdio.

Tools (12): add_note, recall, get_note, link, list_recent,
            consolidate_check, forget,
            review_queue, grade_review, start_review,
            working_status,
            inspect_note
"""
```

Antes de `# --- MCP server plumbing ---`, acrescentar:

```python
def tool_inspect_note(note_id: str) -> dict:
    """Snapshot dos 3 eixos cognitivos (retention/activation/sm2) + audit trail."""
    import json
    from brainiac.core.activation import access_history, activation
    root = find_root()
    conn = connect(index_db_path(root))
    row = conn.execute(
        "SELECT type, access_count, strength, last_access, sm2_json, archived "
        "FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Note not found: {note_id}")
    return {
        "id": note_id,
        "type": row[0],
        "access_count": row[1],
        "strength": row[2],
        "last_access": row[3],
        "sm2": json.loads(row[4]) if row[4] else None,
        "archived": bool(row[5]),
        "activation": activation(conn, note_id),
        "recent_accesses": access_history(conn, note_id, limit=10),
    }
```

Em `_list_tools()`, antes do `]` final, acrescentar:

```python
        Tool(
            name="inspect_note",
            description=(
                "Snapshot dos 3 eixos cognitivos de uma nota: retention (Ebbinghaus), "
                "activation (ACT-R), sm2 (SuperMemo-2), além dos últimos 10 acessos "
                "registrados com source e weight."
            ),
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
```

Em `_DISPATCH`, acrescentar:
```python
    "inspect_note": tool_inspect_note,
```

- [ ] **Step 5: Adicionar comando `inspect` em `cli.py`**

Em `tools/brainiac/brainiac/cli.py`, antes do comando `mcp`, acrescentar:

```python
@main.command()
@click.argument("note_id")
def inspect(note_id: str) -> None:
    """Show the 3 cognitive axes + access history for a note."""
    from brainiac.core.activation import access_history, activation
    from brainiac.core.decay import updated_strength
    from datetime import datetime

    root = find_root()
    conn = connect(index_db_path(root))
    row = conn.execute(
        "SELECT type, access_count, strength, last_access, sm2_json, archived "
        "FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        raise click.ClickException(f"Note not found: {note_id}")

    note_type, access_count, strength, last_access, sm2_json, archived = row
    act = activation(conn, note_id)

    click.echo(f"id: {note_id}")
    click.echo(f"type: {note_type}")
    click.echo(f"archived: {bool(archived)}")
    click.echo("")
    click.echo("Eixos cognitivos:")
    click.echo(f"  retention:  {strength:.3f} (Ebbinghaus)")
    if act == float("-inf"):
        click.echo("  activation: no trace yet (no accesses)")
    else:
        click.echo(f"  activation: {act:.3f} (ACT-R)")
    if sm2_json:
        import json
        sm2 = json.loads(sm2_json)
        click.echo(
            f"  sm2:        ease={sm2['ease']} interval={sm2['interval']} "
            f"reps={sm2['reps']} next={sm2['next_review']}"
        )
    else:
        click.echo("  sm2:        not enrolled")
    click.echo("")
    click.echo(f"access_count: {access_count}")
    click.echo(f"last_access: {last_access}")
    click.echo("")
    history = access_history(conn, note_id, limit=10)
    if history:
        click.echo(f"Últimos {len(history)} acessos:")
        for h in history:
            click.echo(f"  {h['ts']}  {h['source']}  (w={h['weight']})")
    else:
        click.echo("Sem acessos registrados.")
```

E modificar o comando `stats` existente — adicionar no final, antes do return da função:

Localizar o final atual de `stats()`:
```python
    click.echo(f"links: {link_count}")
    click.echo(f"archived: {archived_count}")
```

Substituir por:
```python
    click.echo(f"links: {link_count}")
    click.echo(f"archived: {archived_count}")

    # Phase 5: events + top activations
    from brainiac.core.activation import activation_batch
    event_count = conn.execute("SELECT COUNT(*) FROM accesses").fetchone()[0]
    click.echo(f"events recorded: {event_count}")

    if event_count > 0:
        active_ids = [r[0] for r in conn.execute(
            "SELECT id FROM notes WHERE archived = 0"
        ).fetchall()]
        acts = activation_batch(conn, active_ids)
        ranked = sorted(
            [(nid, a) for nid, a in acts.items() if a != float("-inf")],
            key=lambda x: x[1], reverse=True,
        )[:5]
        if ranked:
            click.echo("top 5 by activation:")
            for nid, a in ranked:
                click.echo(f"  {nid}: {a:.2f}")
```

- [ ] **Step 6: Atualizar skill `brainiac-recall`**

Em `.claude/skills/brainiac-recall/SKILL.md`, acrescentar uma seção no final (antes de qualquer "## Observações" final, ou no fim do arquivo):

```markdown
## Sinalização de ativação (Phase 5)

Para cada resultado de recall, você pode chamar `inspect_note(id)` via MCP para enriquecer a apresentação. Se `activation > 1.5`, adicione o badge **🔥 ativação alta** ao mostrar a nota — indica que o traço de memória está em uso ativo e vale a pena ser revisitado.

Use com moderação: só chame `inspect_note` quando o usuário pedir mais contexto ou quando o resultado for ambíguo. Em recall simples, o output puro do `recall()` é suficiente.
```

- [ ] **Step 7: Rodar — esperar pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py tests/test_cli.py -v --no-cov -k "inspect or stats_command_shows_event"`
Expected: PASS (5 novos: 3 MCP + 2 CLI).

- [ ] **Step 8: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: 242 + 5 = 247 PASS.

- [ ] **Step 9: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_mcp_server.py tools/brainiac/tests/test_cli.py .claude/skills/brainiac-recall/SKILL.md
git commit -m "feat(phase-5): MCP inspect_note + CLI inspect + stats activations + skill recall update"
```

---

## Task 8: Smoke E2E DoD + cobertura

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: Acrescentar testes DoD ao final de `test_smoke_e2e.py`**

Acrescentar:

```python
# --- DoD Phase 5 ---


def test_activation_distinguishes_recent_vs_ancient(fake_brainiac, monkeypatch):
    """DoD: same access_count, different recency → activation(recent) > activation(ancient)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import timedelta
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    conn = connect(index_db_path(fake_brainiac))

    # Note A: 3 recent accesses (last 3 days)
    for d in [1, 2, 3]:
        record_access(conn, "2026-05-20-recent", "get", now=now - timedelta(days=d))
    # Note B: 3 ancient accesses (30+ days ago)
    for d in [30, 40, 50]:
        record_access(conn, "2026-05-20-ancient", "get", now=now - timedelta(days=d))

    a_recent = activation(conn, "2026-05-20-recent", now=now)
    a_ancient = activation(conn, "2026-05-20-ancient", now=now)
    assert a_recent > a_ancient


def test_activation_grows_with_recent_frequency(fake_brainiac, monkeypatch):
    """DoD: more recent accesses → higher activation."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import timedelta
    from brainiac.core.activation import activation, record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    conn = connect(index_db_path(fake_brainiac))

    for h in [1, 3, 5, 7, 9]:
        record_access(conn, "2026-05-20-many", "get", now=now - timedelta(hours=h))
    record_access(conn, "2026-05-20-one", "get", now=now - timedelta(hours=1))

    a_many = activation(conn, "2026-05-20-many", now=now)
    a_one = activation(conn, "2026-05-20-one", now=now)
    assert a_many > a_one


def test_recall_ranks_by_combined_activation_and_semantic(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: 2 notas igualmente similares; a mais ativada vem primeiro."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from datetime import timedelta
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    conn = connect(index_db_path(fake_brainiac))
    body = "# x\n\nshared semantic content for ranking test"
    for nid in ["2026-05-20-quiet", "2026-05-20-active"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, body)
        index_note(conn, fm, body, str(p.relative_to(fake_brainiac)))

    for h in [1, 2, 3, 4, 5]:
        record_access(conn, "2026-05-20-active", "get", now=now - timedelta(hours=h))

    hits = recall(conn, "shared semantic content ranking", k=5)
    ids = [h["id"] for h in hits]
    assert ids.index("2026-05-20-active") < ids.index("2026-05-20-quiet")


def test_inspect_note_shows_audit_trail(fake_brainiac, monkeypatch):
    """DoD: tool_inspect_note retorna recent_accesses com sources corretos."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.activation import record_access
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.mcp_server import tool_add_note, tool_inspect_note

    tool_add_note(
        note_id="2026-05-20-audit", note_type="semantic",
        title="x", body="# x\n\nbody",
    )
    conn = connect(index_db_path(fake_brainiac))
    record_access(conn, "2026-05-20-audit", "review")
    record_access(conn, "2026-05-20-audit", "recall_hit")

    result = tool_inspect_note("2026-05-20-audit")
    sources = {a["source"] for a in result["recent_accesses"]}
    assert sources >= {"review", "recall_hit"}
```

- [ ] **Step 2: Rodar testes DoD**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_smoke_e2e.py -v --no-cov -k "activation_distinguishes or activation_grows or recall_ranks_by_combined or inspect_note_shows_audit"`
Expected: 4 PASS.

- [ ] **Step 3: Rodar suite completa**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS (247 + 4 = 251).

- [ ] **Step 4: Verificar cobertura de `activation.py`**

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.activation --cov-report=term-missing --ignore=tests/core/test_embeddings.py 2>&1 | tail -10`
Expected: `brainiac/core/activation.py` ≥ 95%.

- [ ] **Step 5: Commit final da Fase 5**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-5): smoke E2E DoD — activation recency/frequency + recall ranking + audit trail"
```

---

## Definition of Done — Fase 5

Checklist final da spec (§8):

- [ ] **Activation captura recência**: `test_activation_distinguishes_recent_vs_ancient` passa
- [ ] **Activation captura frequência recente**: `test_activation_grows_with_recent_frequency` passa
- [ ] **Recall ranking responde a activation**: `test_recall_ranks_by_combined_activation_and_semantic` passa
- [ ] **Auditoria por nota**: `tool_inspect_note` + `brainiac inspect` retornam os 3 eixos + access_history
- [ ] **4 sources gravadas**: get / review / recall_hit / link_in — verificado por testes de integração
- [ ] **Config opcional**: 3 fields novos em `Config` com defaults; `brainiac.toml` opcional
- [ ] **Schema migration idempotente**: rodar `connect()` 2x não quebra
- [ ] **Cobertura `activation.py` ≥ 95%**
- [ ] **Suite completa verde** (~251 testes)
- [ ] **Sem regressões** nas Phases 0-4

Após Fase 5 verde, próximas extensões possíveis: Phase 6 (spreading activation iterativa), Phase 7 (consolidação probabilística com peso emocional + novidade), Phase 8 (Atkinson-Shiffrin states).
