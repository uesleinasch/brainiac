# Fase 8 — Atkinson-Shiffrin States Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modelar explicitamente 4 estados cognitivos (`sensory → working → long_term ↔ archived`) com enforcement Markov nas transições e probabilidades calibradas. Adiciona buffer sensory (TTL transiente) + transition_note unificada + transition_probabilities + 5 MCP tools + 2 CLI commands.

**Architecture:** Novo módulo `core/states.py` (state enum, current_state, transition_note, transition_probabilities). Novo módulo `core/sensory.py` (CRUD do buffer transiente). Schema ganha tabela `sensory_buffer`. Config ganha 1 field (`sensory_ttl_minutes`). MCP layer ganha 5 tools novos. CLI ganha 2 commands. Sem novas deps pip.

**Tech Stack:** Python stdlib `enum`, `uuid`, `datetime` + sqlite3 + existing brainiac.

---

## Mapa de arquivos

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── states.py             # CREATE
│   │   ├── sensory.py            # CREATE
│   │   ├── config.py             # MODIFY: +1 field
│   │   └── index.py              # MODIFY: connect() migration sensory_buffer
│   ├── mcp_server.py             # MODIFY: 5 tools novos
│   └── cli.py                    # MODIFY: state + sensory commands
└── tests/
    ├── core/
    │   ├── test_states.py        # CREATE
    │   ├── test_sensory.py       # CREATE
    │   ├── test_config.py        # MODIFY
    │   └── test_index_vec.py     # MODIFY: schema migration
    ├── test_mcp_server.py        # MODIFY
    ├── test_cli.py               # MODIFY
    └── test_smoke_e2e.py         # MODIFY: 4 DoD tests
```

---

## Task 1: Schema sensory_buffer + Config + estado enum

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/brainiac/core/config.py`
- Modify: `tools/brainiac/tests/core/test_index_vec.py`
- Modify: `tools/brainiac/tests/core/test_config.py`

- [ ] **Step 1: Testes failing**

Em `test_config.py`:

```python
def test_config_has_sensory_ttl_default(fake_brainiac):
    from brainiac.core.config import load_config
    cfg = load_config(fake_brainiac)
    assert cfg.sensory_ttl_minutes == 5
```

Em `test_index_vec.py`:

```python
def test_connect_creates_sensory_buffer_table(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    conn = connect(index_db_path(fake_brainiac))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sensory_buffer)").fetchall()]
    expected = {"id", "title", "body", "created", "expires_at", "proposed_type", "proposed_id"}
    assert set(cols) == expected


def test_connect_creates_sensory_expires_index(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    conn = connect(index_db_path(fake_brainiac))
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(sensory_buffer)").fetchall()]
    assert "idx_sensory_expires" in indexes
```

- [ ] **Step 2: Fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py tests/core/test_index_vec.py -v --no-cov -k "sensory"`
Expected: FAIL.

- [ ] **Step 3: Config + migration**

Em `config.py`, adicionar:
```python
    # Atkinson-Shiffrin states (Phase 8)
    sensory_ttl_minutes: int = 5
```

Em `index.py::connect()`, após bloco Phase 7, acrescentar:

```python
    # Phase 8: sensory_buffer (transient drafts)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sensory_buffer (
            id TEXT PRIMARY KEY,
            title TEXT,
            body TEXT NOT NULL,
            created TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            proposed_type TEXT,
            proposed_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sensory_expires ON sensory_buffer(expires_at);
    """)
    conn.commit()
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_config.py tests/core/test_index_vec.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/brainiac/core/config.py tools/brainiac/tests/core/test_config.py tools/brainiac/tests/core/test_index_vec.py
git commit -m "feat(phase-8): schema sensory_buffer + Config sensory_ttl_minutes"
```

---

## Task 2: `core/sensory.py` — CRUD do buffer

**Files:**
- Create: `tools/brainiac/brainiac/core/sensory.py`
- Create: `tools/brainiac/tests/core/test_sensory.py`

- [ ] **Step 1: Testes failing**

Criar `tests/core/test_sensory.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest


NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_add_sensory_inserts_with_generated_id(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="rascunho rápido", title="ideia", now=NOW)
    assert sid.startswith("sensory-")
    row = conn.execute(
        "SELECT body, title FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    assert row[0] == "rascunho rápido"
    assert row[1] == "ideia"


def test_add_sensory_sets_expires_at(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="x", now=NOW, ttl_minutes=10)
    row = conn.execute(
        "SELECT expires_at FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    expected = (NOW + timedelta(minutes=10)).isoformat()
    assert row[0] == expected


def test_list_sensory_excludes_expired_by_default(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, list_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid_fresh = add_sensory(conn, body="fresh", now=NOW, ttl_minutes=5)
    sid_old = add_sensory(conn, body="old", now=NOW - timedelta(minutes=30), ttl_minutes=5)

    fresh = list_sensory(conn, now=NOW)
    ids = {e["id"] for e in fresh}
    assert sid_fresh in ids
    assert sid_old not in ids


def test_list_sensory_includes_expired_when_flag(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, list_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid_old = add_sensory(conn, body="old", now=NOW - timedelta(minutes=30), ttl_minutes=5)
    all_items = list_sensory(conn, now=NOW, include_expired=True)
    ids = {e["id"] for e in all_items}
    assert sid_old in ids


def test_commit_sensory_creates_real_note(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.sensory import add_sensory, commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="# Title\n\nbody content", title="Title", now=NOW)
    final_id = commit_sensory(
        conn, fake_brainiac, sid, note_type="semantic", final_id="2026-05-20-committed"
    )
    assert final_id == "2026-05-20-committed"
    assert (fake_brainiac / "semanticMemory" / "2026-05-20-committed.md").exists()


def test_commit_sensory_deletes_buffer_entry(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="# x\n\nbody", title="x", now=NOW)
    commit_sensory(conn, fake_brainiac, sid, note_type="semantic", final_id="2026-05-20-c")
    row = conn.execute(
        "SELECT id FROM sensory_buffer WHERE id = ?", (sid,)
    ).fetchone()
    assert row is None


def test_commit_sensory_raises_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import commit_sensory

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        commit_sensory(conn, fake_brainiac, "sensory-ghost", note_type="semantic", final_id="x")


def test_expire_sensory_deletes_old_entries(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, expire_sensory

    conn = connect(index_db_path(fake_brainiac))
    add_sensory(conn, body="fresh", now=NOW, ttl_minutes=5)
    add_sensory(conn, body="old1", now=NOW - timedelta(minutes=30), ttl_minutes=5)
    add_sensory(conn, body="old2", now=NOW - timedelta(minutes=60), ttl_minutes=5)

    deleted = expire_sensory(conn, now=NOW)
    assert deleted == 2

    remaining = conn.execute("SELECT COUNT(*) FROM sensory_buffer").fetchone()[0]
    assert remaining == 1


def test_get_sensory_returns_entry(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory, get_sensory

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="body", title="t", now=NOW)
    entry = get_sensory(conn, sid)
    assert entry["id"] == sid
    assert entry["body"] == "body"
    assert entry["title"] == "t"


def test_get_sensory_returns_none_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import get_sensory

    conn = connect(index_db_path(fake_brainiac))
    assert get_sensory(conn, "sensory-ghost") is None
```

- [ ] **Step 2: Fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sensory.py -v --no-cov`
Expected: FAIL.

- [ ] **Step 3: Implementar `sensory.py`**

Criar `tools/brainiac/brainiac/core/sensory.py`:

```python
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _gen_id(now: datetime) -> str:
    """sensory-<timestamp>-<short_uuid>."""
    ts = now.strftime("%Y%m%d-%H%M%S")
    suf = uuid.uuid4().hex[:8]
    return f"sensory-{ts}-{suf}"


def add_sensory(
    conn: sqlite3.Connection,
    body: str,
    *,
    title: str | None = None,
    proposed_type: str | None = None,
    proposed_id: str | None = None,
    now: datetime | None = None,
    ttl_minutes: int = 5,
) -> str:
    """Insert a sensory draft. Returns generated id."""
    now = now or datetime.now(timezone.utc)
    sid = _gen_id(now)
    expires = now + timedelta(minutes=ttl_minutes)
    conn.execute(
        """
        INSERT INTO sensory_buffer (id, title, body, created, expires_at, proposed_type, proposed_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, title, body, now.isoformat(), expires.isoformat(), proposed_type, proposed_id),
    )
    conn.commit()
    return sid


def list_sensory(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    include_expired: bool = False,
) -> list[dict]:
    """List sensory buffer entries. Excludes expired unless include_expired=True."""
    now = now or datetime.now(timezone.utc)
    if include_expired:
        sql = "SELECT id, title, body, created, expires_at, proposed_type, proposed_id FROM sensory_buffer ORDER BY created DESC"
        params: tuple = ()
    else:
        sql = """
            SELECT id, title, body, created, expires_at, proposed_type, proposed_id
            FROM sensory_buffer WHERE expires_at > ? ORDER BY created DESC
        """
        params = (now.isoformat(),)
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": r[0], "title": r[1], "body": r[2],
            "created": r[3], "expires_at": r[4],
            "proposed_type": r[5], "proposed_id": r[6],
        }
        for r in rows
    ]


def get_sensory(conn: sqlite3.Connection, sensory_id: str) -> dict | None:
    """Return one entry, or None if missing."""
    row = conn.execute(
        "SELECT id, title, body, created, expires_at, proposed_type, proposed_id FROM sensory_buffer WHERE id = ?",
        (sensory_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "title": row[1], "body": row[2],
        "created": row[3], "expires_at": row[4],
        "proposed_type": row[5], "proposed_id": row[6],
    }


def commit_sensory(
    conn: sqlite3.Connection,
    root: Path,
    sensory_id: str,
    *,
    note_type: str,
    final_id: str,
) -> str:
    """Promote sensory draft → working note. Returns final_id.

    Raises KeyError if sensory_id not found.
    """
    from brainiac.core.index import index_note
    from brainiac.core.note import new_note, write_note
    from brainiac.core.paths import note_path

    entry = get_sensory(conn, sensory_id)
    if entry is None:
        raise KeyError(f"sensory entry not found: {sensory_id}")

    fm = new_note(note_id=final_id, note_type=note_type)
    body = entry["body"]
    if not body.lstrip().startswith("#"):
        title = entry["title"] or final_id
        body = f"# {title}\n\n{body}"

    path = note_path(root, final_id, note_type)
    write_note(path, fm, body)
    rel = str(path.relative_to(root))
    index_note(conn, fm, body, rel)

    conn.execute("DELETE FROM sensory_buffer WHERE id = ?", (sensory_id,))
    conn.commit()
    return final_id


def expire_sensory(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Delete expired entries. Returns count deleted."""
    now = now or datetime.now(timezone.utc)
    cur = conn.execute(
        "DELETE FROM sensory_buffer WHERE expires_at <= ?",
        (now.isoformat(),),
    )
    conn.commit()
    return cur.rowcount
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_sensory.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/sensory.py tools/brainiac/tests/core/test_sensory.py
git commit -m "feat(phase-8): sensory.py — buffer CRUD + TTL expiration"
```

---

## Task 3: `core/states.py` — enum + current_state + transition_note

**Files:**
- Create: `tools/brainiac/brainiac/core/states.py`
- Create: `tools/brainiac/tests/core/test_states.py`

- [ ] **Step 1: Testes failing**

Criar `tests/core/test_states.py`:

```python
import pytest


def test_current_state_working_for_working_type(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-w", "working")
    p = note_path(fake_brainiac, "2026-05-20-w", "working")
    write_note(p, fm, "# w")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# w", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-w") == NoteState.WORKING


def test_current_state_long_term_for_semantic(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-s", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-s", "semantic")
    write_note(p, fm, "# s")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# s", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-s") == NoteState.LONG_TERM


def test_current_state_long_term_for_episodic(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-e", "episodic")
    p = note_path(fake_brainiac, "2026-05-20-e", "episodic")
    write_note(p, fm, "# e")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# e", str(p.relative_to(fake_brainiac)))

    assert current_state(conn, "2026-05-20-e") == NoteState.LONG_TERM


def test_current_state_archived(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-a", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-a", "semantic")
    write_note(p, fm, "# a")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# a", str(p.relative_to(fake_brainiac)), archived=True)

    assert current_state(conn, "2026-05-20-a") == NoteState.ARCHIVED


def test_current_state_sensory_when_in_buffer(fake_brainiac):
    from datetime import datetime, timezone
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.sensory import add_sensory
    from brainiac.core.states import NoteState, current_state

    conn = connect(index_db_path(fake_brainiac))
    sid = add_sensory(conn, body="x", now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    assert current_state(conn, sid) == NoteState.SENSORY


def test_current_state_raises_for_unknown(fake_brainiac):
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.states import current_state

    conn = connect(index_db_path(fake_brainiac))
    with pytest.raises(KeyError):
        current_state(conn, "2026-05-20-ghost-state")


def test_transition_working_to_long_term_succeeds(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-wlt", "working")
    p = note_path(fake_brainiac, "2026-05-20-wlt", "working")
    write_note(p, fm, "# wlt")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# wlt", str(p.relative_to(fake_brainiac)))

    new_state = transition_note(conn, fake_brainiac, "2026-05-20-wlt", NoteState.LONG_TERM)
    assert new_state == NoteState.LONG_TERM
    assert current_state(conn, "2026-05-20-wlt") == NoteState.LONG_TERM


def test_transition_working_to_archived_rejected(fake_brainiac):
    """Markov enforcement: can't skip from working directly to archived."""
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-wskip", "working")
    p = note_path(fake_brainiac, "2026-05-20-wskip", "working")
    write_note(p, fm, "# x")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# x", str(p.relative_to(fake_brainiac)))

    with pytest.raises(ValueError, match="invalid transition"):
        transition_note(conn, fake_brainiac, "2026-05-20-wskip", NoteState.ARCHIVED)


def test_transition_long_term_to_archived_succeeds(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-lta", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-lta", "semantic")
    write_note(p, fm, "# lta")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# lta", str(p.relative_to(fake_brainiac)))

    transition_note(conn, fake_brainiac, "2026-05-20-lta", NoteState.ARCHIVED)
    assert current_state(conn, "2026-05-20-lta") == NoteState.ARCHIVED


def test_transition_archived_to_long_term_resurrects(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-res", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-res", "semantic")
    write_note(p, fm, "# res")
    conn = connect(index_db_path(fake_brainiac))
    # Insert as archived
    index_note(conn, fm, "# res", str(p.relative_to(fake_brainiac)), archived=True)
    # Move file to archive dir to match
    import shutil
    archive_dir = fake_brainiac / "memoryTransfer" / "archive" / "2026"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(archive_dir / "2026-05-20-res.md"))
    # Fix path in DB
    conn.execute(
        "UPDATE notes SET path = ? WHERE id = ?",
        ("memoryTransfer/archive/2026/2026-05-20-res.md", "2026-05-20-res"),
    )
    conn.commit()

    assert current_state(conn, "2026-05-20-res") == NoteState.ARCHIVED
    transition_note(conn, fake_brainiac, "2026-05-20-res", NoteState.LONG_TERM)
    assert current_state(conn, "2026-05-20-res") == NoteState.LONG_TERM


def test_transition_creates_audit_event(fake_brainiac):
    import json
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-aud", "working")
    p = note_path(fake_brainiac, "2026-05-20-aud", "working")
    write_note(p, fm, "# aud")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# aud", str(p.relative_to(fake_brainiac)))

    transition_note(conn, fake_brainiac, "2026-05-20-aud", NoteState.LONG_TERM)

    events_file = fake_brainiac / "memoryTransfer" / "logs" / "events.jsonl"
    entries = [json.loads(l) for l in events_file.read_text().strip().split("\n") if l]
    transitions = [e for e in entries if e["action"] == "state_transition"]
    assert len(transitions) >= 1
    assert "working" in transitions[-1]["detail"]
    assert "long_term" in transitions[-1]["detail"]


def test_transition_probabilities_working_note(fake_brainiac):
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import transition_probabilities
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-prob", "working")
    p = note_path(fake_brainiac, "2026-05-20-prob", "working")
    write_note(p, fm, "# prob")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# prob", str(p.relative_to(fake_brainiac)))

    result = transition_probabilities(conn, "2026-05-20-prob")
    assert result["current_state"] == "working"
    assert "long_term" in result["transitions"]
    assert 0.0 <= result["transitions"]["long_term"]["probability"] <= 1.0
    assert "reason" in result["transitions"]["long_term"]
```

- [ ] **Step 2: Fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_states.py -v --no-cov`
Expected: FAIL.

- [ ] **Step 3: Implementar `states.py`**

Criar `tools/brainiac/brainiac/core/states.py`:

```python
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class NoteState(str, Enum):
    SENSORY = "sensory"
    WORKING = "working"
    LONG_TERM = "long_term"
    ARCHIVED = "archived"


VALID_TRANSITIONS: dict[NoteState, set[NoteState]] = {
    NoteState.SENSORY: {NoteState.WORKING},
    NoteState.WORKING: {NoteState.LONG_TERM},
    NoteState.LONG_TERM: {NoteState.ARCHIVED},
    NoteState.ARCHIVED: {NoteState.LONG_TERM},
}


def current_state(conn: sqlite3.Connection, note_id: str) -> NoteState:
    """Derive state from notes table + sensory_buffer."""
    # Check sensory_buffer first
    sensory_row = conn.execute(
        "SELECT id FROM sensory_buffer WHERE id = ?", (note_id,)
    ).fetchone()
    if sensory_row is not None:
        return NoteState.SENSORY

    note_row = conn.execute(
        "SELECT type, archived FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if note_row is None:
        raise KeyError(f"Note not found: {note_id}")

    note_type, archived = note_row
    if archived == 1:
        return NoteState.ARCHIVED
    if note_type == "working":
        return NoteState.WORKING
    if note_type in ("semantic", "episodic"):
        return NoteState.LONG_TERM
    raise ValueError(f"Unknown type for {note_id}: {note_type}")


def transition_note(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    target: NoteState,
    *,
    now: datetime | None = None,
    target_type: str = "semantic",
) -> NoteState:
    """Transition note to target state. Raises ValueError if invalid transition.

    target_type only used for working → long_term (determines if semantic or episodic).
    """
    from brainiac.core.consolidate import promote_note
    from brainiac.core.decay import archive_note
    from brainiac.core.events import log_event

    now = now or datetime.now(timezone.utc)
    cur = current_state(conn, note_id)

    if target not in VALID_TRANSITIONS[cur]:
        raise ValueError(f"invalid transition: {cur.value} → {target.value}")

    # Execute the transition
    if cur == NoteState.WORKING and target == NoteState.LONG_TERM:
        promote_note(conn, root, note_id, target_type, now=now)
    elif cur == NoteState.LONG_TERM and target == NoteState.ARCHIVED:
        archive_note(conn, root, note_id, now=now)
    elif cur == NoteState.ARCHIVED and target == NoteState.LONG_TERM:
        _resurrect(conn, root, note_id, now=now)
    elif cur == NoteState.SENSORY and target == NoteState.WORKING:
        raise ValueError("Use commit_sensory(sensory_id, note_type, final_id) for sensory → working")

    log_event(
        root, note_id, "state_transition",
        f"{cur.value} → {target.value}",
    )
    return target


def _resurrect(
    conn: sqlite3.Connection,
    root: Path,
    note_id: str,
    *,
    now: datetime,
) -> None:
    """Move note from archive back to active (long-term)."""
    import shutil
    from brainiac.core.index import index_note
    from brainiac.core.note import parse_note, write_note
    from brainiac.core.paths import note_path

    row = conn.execute(
        "SELECT path, type FROM notes WHERE id = ? AND archived = 1",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Archived note not found: {note_id}")

    old_rel, note_type = row
    old_path = root / old_rel
    fm, body = parse_note(old_path)
    new_path = note_path(root, note_id, note_type)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_path), str(new_path))
    new_rel = str(new_path.relative_to(root))

    conn.execute(
        "UPDATE notes SET archived = 0, path = ? WHERE id = ?",
        (new_rel, note_id),
    )
    conn.commit()
    write_note(new_path, fm, body)
    index_note(conn, fm, body, new_rel)


def transition_probabilities(conn: sqlite3.Connection, note_id: str) -> dict:
    """Compute probability + reason for each possible transition from current state."""
    from brainiac.core.config import Config, load_config
    from brainiac.core.novelty import get_or_compute_novelty
    from brainiac.core.paths import find_root

    cur = current_state(conn, note_id)
    result: dict = {"current_state": cur.value, "transitions": {}}

    if cur == NoteState.SENSORY:
        result["transitions"]["working"] = {
            "probability": 1.0,
            "reason": "P_enc=1.0 on user commit_sensory",
        }
        return result

    if cur == NoteState.WORKING:
        # P_cons via Phase 7 formula
        config = load_config(find_root()) if find_root() else Config()
        row = conn.execute(
            "SELECT access_count, emotional_weight FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if row:
            R, E = row
            n_score = get_or_compute_novelty(conn, note_id)
            alpha = config.consolidation_learning_rate
            p = 1.0 - math.exp(-alpha * R * E * n_score)
        else:
            p = 0.0
        result["transitions"]["long_term"] = {
            "probability": p,
            "reason": f"P_cons = 1 - exp(-α·R·E·n)",
        }
        return result

    if cur == NoteState.LONG_TERM:
        row = conn.execute(
            "SELECT strength FROM notes WHERE id = ?", (note_id,),
        ).fetchone()
        strength = row[0] if row else 0.5
        p_forget = 1.0 - strength
        result["transitions"]["archived"] = {
            "probability": p_forget,
            "reason": "P_forget = 1 - retention(Ebbinghaus)",
        }
        return result

    if cur == NoteState.ARCHIVED:
        result["transitions"]["long_term"] = {
            "probability": None,  # manual action only
            "reason": "manual via transition_note(target=LONG_TERM)",
        }
        return result

    return result
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/core/test_states.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/states.py tools/brainiac/tests/core/test_states.py
git commit -m "feat(phase-8): states.py — NoteState enum + current_state + transition_note + probabilities"
```

---

## Task 4: MCP tools — capture_sensory, list_sensory, commit_sensory, transition_note, note_state

**Files:**
- Modify: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/tests/test_mcp_server.py`

- [ ] **Step 1: Testes failing**

Acrescentar ao final de `test_mcp_server.py`:

```python
def test_tool_capture_sensory_inserts_into_buffer(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_capture_sensory

    result = tool_capture_sensory(body="rascunho", title="x")
    assert result["id"].startswith("sensory-")


def test_tool_list_sensory_returns_active_entries(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_capture_sensory, tool_list_sensory

    tool_capture_sensory(body="a")
    tool_capture_sensory(body="b")
    entries = tool_list_sensory()
    assert len(entries) == 2


def test_tool_commit_sensory_promotes_to_working(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_capture_sensory, tool_commit_sensory

    s = tool_capture_sensory(body="# title\n\nbody")
    result = tool_commit_sensory(
        sensory_id=s["id"], note_type="semantic", final_id="2026-05-20-promoted",
    )
    assert result["id"] == "2026-05-20-promoted"


def test_tool_transition_note_working_to_long_term(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_transition_note

    tool_add_note(
        note_id="2026-05-20-t", note_type="working",
        title="x", body="# x",
    )
    result = tool_transition_note(note_id="2026-05-20-t", target_state="long_term")
    assert result["new_state"] == "long_term"


def test_tool_note_state_returns_state_and_probabilities(fake_brainiac, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_note_state

    tool_add_note(
        note_id="2026-05-20-ns", note_type="working",
        title="x", body="# x",
    )
    result = tool_note_state(note_id="2026-05-20-ns")
    assert result["current_state"] == "working"
    assert "transitions" in result
```

- [ ] **Step 2: Fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov -k "sensory or transition_note or note_state"`
Expected: FAIL.

- [ ] **Step 3: Adicionar 5 tools em `mcp_server.py`**

Atualizar docstring no topo:

```python
"""MCP server exposing brainiac tools via stdio.

Tools (17): add_note, recall, get_note, link, list_recent,
            consolidate_check, forget,
            review_queue, grade_review, start_review,
            working_status, inspect_note,
            capture_sensory, list_sensory, commit_sensory,
            transition_note, note_state
"""
```

Antes de `# --- MCP server plumbing ---`, acrescentar:

```python
def tool_capture_sensory(body: str, title: str | None = None, proposed_type: str | None = None) -> dict:
    """Insert a transient sensory draft. TTL ~5 minutes."""
    from brainiac.core.sensory import add_sensory
    root = find_root()
    conn = connect(index_db_path(root))
    sid = add_sensory(conn, body=body, title=title, proposed_type=proposed_type)
    return {"id": sid, "body": body, "title": title}


def tool_list_sensory(include_expired: bool = False) -> list[dict]:
    """List sensory buffer entries (active by default)."""
    from brainiac.core.sensory import list_sensory
    root = find_root()
    conn = connect(index_db_path(root))
    return list_sensory(conn, include_expired=include_expired)


def tool_commit_sensory(sensory_id: str, note_type: str, final_id: str) -> dict:
    """Promote sensory draft to a working/semantic/episodic note."""
    from brainiac.core.sensory import commit_sensory
    root = find_root()
    conn = connect(index_db_path(root))
    fid = commit_sensory(conn, root, sensory_id, note_type=note_type, final_id=final_id)
    return {"id": fid, "type": note_type}


def tool_transition_note(note_id: str, target_state: str, target_type: str = "semantic") -> dict:
    """Transition note to target_state. target_type only used for working→long_term."""
    from brainiac.core.states import NoteState, transition_note
    root = find_root()
    conn = connect(index_db_path(root))
    try:
        ts = NoteState(target_state)
    except ValueError:
        raise ValueError(f"Unknown state: {target_state}")
    new_state = transition_note(conn, root, note_id, ts, target_type=target_type)
    return {"id": note_id, "new_state": new_state.value}


def tool_note_state(note_id: str) -> dict:
    """Return current state + transition probabilities for a note."""
    from brainiac.core.states import transition_probabilities
    root = find_root()
    conn = connect(index_db_path(root))
    return transition_probabilities(conn, note_id)
```

Atualizar `_list_tools()` adicionando 5 entries (sigam o padrão dos anteriores; cada uma com inputSchema apropriado).

Atualizar `_DISPATCH`:

```python
_DISPATCH = {
    # ... existing 12 ...
    "capture_sensory": tool_capture_sensory,
    "list_sensory": tool_list_sensory,
    "commit_sensory": tool_commit_sensory,
    "transition_note": tool_transition_note,
    "note_state": tool_note_state,
}
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_mcp_server.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/tests/test_mcp_server.py
git commit -m "feat(phase-8): MCP 5 tools — sensory CRUD + transition_note + note_state"
```

---

## Task 5: CLI `brainiac state <id>` + `brainiac sensory list`

**Files:**
- Modify: `tools/brainiac/brainiac/cli.py`
- Modify: `tools/brainiac/tests/test_cli.py`

- [ ] **Step 1: Testes failing**

Acrescentar ao final de `test_cli.py`:

```python
class TestStateCommand:
    def test_state_command_outputs_state_and_probabilities(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import write_note
        from brainiac.core.paths import index_db_path, note_path
        from tests.conftest import make_fm

        fm = make_fm("2026-05-20-st", "working")
        p = note_path(fake_brainiac, "2026-05-20-st", "working")
        write_note(p, fm, "# st")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# st", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["state", "2026-05-20-st"])
        assert result.exit_code == 0
        assert "working" in result.output.lower()
        assert "long_term" in result.output.lower()


class TestSensoryListCommand:
    def test_sensory_list_empty(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = CliRunner().invoke(main, ["sensory", "list"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower() or "0" in result.output

    def test_sensory_list_shows_entries(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect
        from brainiac.core.paths import index_db_path
        from brainiac.core.sensory import add_sensory

        conn = connect(index_db_path(fake_brainiac))
        add_sensory(conn, body="primeiro rascunho", title="t1")

        result = CliRunner().invoke(main, ["sensory", "list"])
        assert result.exit_code == 0
        assert "primeiro rascunho" in result.output or "t1" in result.output
```

- [ ] **Step 2: Fail**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov -k "state_command or sensory"`
Expected: FAIL.

- [ ] **Step 3: Adicionar comandos em `cli.py`**

Antes do comando `mcp`, acrescentar:

```python
@main.command()
@click.argument("note_id")
def state(note_id: str) -> None:
    """Show current state + transition probabilities for a note."""
    from brainiac.core.states import transition_probabilities

    root = find_root()
    conn = connect(index_db_path(root))
    try:
        result = transition_probabilities(conn, note_id)
    except KeyError as e:
        raise click.ClickException(str(e))

    click.echo(f"id: {note_id}")
    click.echo(f"current_state: {result['current_state']}")
    click.echo("")
    click.echo("Transition probabilities:")
    for target, info in result["transitions"].items():
        prob = info["probability"]
        prob_str = f"{prob:.3f}" if prob is not None else "manual"
        click.echo(f"  → {target}: {prob_str}  ({info['reason']})")


@main.group()
def sensory() -> None:
    """Manage sensory buffer (transient drafts)."""


@sensory.command("list")
def sensory_list() -> None:
    """List active sensory buffer entries."""
    from brainiac.core.sensory import list_sensory

    root = find_root()
    conn = connect(index_db_path(root))
    entries = list_sensory(conn)
    if not entries:
        click.echo("Sensory buffer is empty.")
        return

    click.echo(f"{len(entries)} active sensory entries:")
    for e in entries:
        title = e["title"] or "(untitled)"
        click.echo(f"  {e['id']}  expires={e['expires_at']}  {title}")
        body_preview = e["body"][:80].replace("\n", " ")
        click.echo(f"    body: {body_preview}...")
```

- [ ] **Step 4: Pass**

Run: `cd tools/brainiac && .venv/bin/pytest tests/test_cli.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_cli.py
git commit -m "feat(phase-8): CLI brainiac state + sensory list commands"
```

---

## Task 6: Smoke E2E DoD + cobertura

**Files:**
- Modify: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: 4 testes DoD**

Acrescentar:

```python
# --- DoD Phase 8 ---


def test_sensory_to_working_full_cycle(fake_brainiac, monkeypatch):
    """DoD: capture sensory → list → commit → real note exists in working."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect
    from brainiac.core.paths import index_db_path
    from brainiac.core.states import NoteState, current_state
    from brainiac.mcp_server import tool_capture_sensory, tool_commit_sensory, tool_list_sensory

    s = tool_capture_sensory(body="# Test\n\nrascunho", title="Test")
    sid = s["id"]

    entries = tool_list_sensory()
    assert any(e["id"] == sid for e in entries)

    tool_commit_sensory(sensory_id=sid, note_type="working", final_id="2026-05-20-cycle")
    assert (fake_brainiac / "shortMemory" / "2026-05-20-cycle.md").exists()

    conn = connect(index_db_path(fake_brainiac))
    assert current_state(conn, "2026-05-20-cycle") == NoteState.WORKING


def test_state_machine_enforces_markov(fake_brainiac, monkeypatch):
    """DoD: working → archived (skip long_term) is rejected."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    import pytest
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-mk", "working")
    p = note_path(fake_brainiac, "2026-05-20-mk", "working")
    write_note(p, fm, "# x")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# x", str(p.relative_to(fake_brainiac)))

    with pytest.raises(ValueError, match="invalid transition"):
        transition_note(conn, fake_brainiac, "2026-05-20-mk", NoteState.ARCHIVED)


def test_state_archived_to_long_term_resurrects(fake_brainiac, monkeypatch):
    """DoD: archived can be resurrected to long_term."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.decay import archive_note
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.states import NoteState, current_state, transition_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-resurrect", "semantic")
    p = note_path(fake_brainiac, "2026-05-20-resurrect", "semantic")
    write_note(p, fm, "# r")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# r", str(p.relative_to(fake_brainiac)))

    # archive properly via archive_note (moves file + updates DB)
    archive_note(conn, fake_brainiac, "2026-05-20-resurrect")
    assert current_state(conn, "2026-05-20-resurrect") == NoteState.ARCHIVED

    transition_note(conn, fake_brainiac, "2026-05-20-resurrect", NoteState.LONG_TERM)
    assert current_state(conn, "2026-05-20-resurrect") == NoteState.LONG_TERM


def test_note_state_returns_calibrated_probabilities(fake_brainiac, monkeypatch):
    """DoD: tool_note_state reflects current metrics in probability."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect
    from brainiac.core.novelty import cache_novelty
    from brainiac.core.paths import index_db_path
    from brainiac.mcp_server import tool_add_note, tool_note_state

    tool_add_note(
        note_id="2026-05-20-prob-note", note_type="working",
        title="x", body="# x", emotional_weight=1.0,
    )
    conn = connect(index_db_path(fake_brainiac))
    conn.execute(
        "UPDATE notes SET access_count = 5 WHERE id = ?",
        ("2026-05-20-prob-note",),
    )
    conn.commit()
    cache_novelty(conn, "2026-05-20-prob-note", 1.0)

    result = tool_note_state(note_id="2026-05-20-prob-note")
    assert result["current_state"] == "working"
    p_cons = result["transitions"]["long_term"]["probability"]
    # P_cons = 1 - exp(-0.5 * 5 * 1.0 * 1.0) ≈ 0.918
    assert p_cons > 0.6
```

- [ ] **Step 2: Pass + cobertura**

Run: `cd tools/brainiac && .venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov`
Expected: PASS.

Run: `cd tools/brainiac && .venv/bin/pytest --cov=brainiac.core.states --cov=brainiac.core.sensory --cov-report=term --ignore=tests/core/test_embeddings.py 2>&1 | tail -8`
Expected: ambos ≥ 95%.

- [ ] **Step 3: Commit final**

```bash
git add tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-8): smoke E2E DoD — sensory cycle + markov enforcement + resurrect + calibrated P"
```

---

## Definition of Done — Fase 8

- [ ] `current_state` correto para 4 estados
- [ ] `transition_note` enforça Markov chain (rejeita pulos)
- [ ] `transition_probabilities` calibradas via Phases 2/5/7 metrics
- [ ] Sensory buffer funcional (add/list/commit/expire/get)
- [ ] 5 MCP tools novos
- [ ] CLI `brainiac state <id>` e `brainiac sensory list`
- [ ] Cobertura `states.py` e `sensory.py` ≥ 95%
- [ ] Suite verde sem regressões

Após Phase 8, brainiac terá modelo de memória cognitiva completo:
- 4 estados explícitos
- 3 eixos de medição (retention, activation, sm2)
- 3 caminhos de promoção (booleano, ACT-R borderline, probabilístico)
- Spreading activation multi-hop
- Sensory buffer transiente
- Auditoria completa via events.jsonl
