# Brainiac Fase 0 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o esqueleto do brainiac que permite salvar e buscar notas via Claude (MCP) com metadata cognitiva já em vigor — sem ainda implementar dinâmica temporal, embeddings ou SM-2.

**Architecture:** Package Python `brainiac` em `tools/brainiac/` expõe (a) CLI `brainiac` com comandos `reindex`/`stats`/`mcp` e (b) servidor MCP stdio com 5 tools (`add_note`, `recall`, `get_note`, `link`, `list_recent`). Notas `.md` em `shortMemory/`, `longMemory/episodic/`, `semanticMemory/` são fonte de verdade; SQLite em `memoryTransfer/index.sqlite` é cache reconstrutível via `reindex_all`. Busca é FTS5 (BM25) nesta fase — embeddings entram na Fase 1.

**Tech Stack:** Python 3.11+, Pydantic 2, python-frontmatter, mcp SDK, click, SQLite com FTS5 (stdlib). Pytest + pytest-cov para testes.

---

## Mapa de arquivos (Fase 0)

```
brainiac/
├── tools/brainiac/                          # NOVO
│   ├── pyproject.toml                       # NOVO — deps + entry points + pytest config
│   ├── brainiac/
│   │   ├── __init__.py                      # NOVO — versão
│   │   ├── cli.py                           # NOVO — click app: reindex, stats, mcp
│   │   ├── mcp_server.py                    # NOVO — MCP stdio server, 5 tools
│   │   └── core/
│   │       ├── __init__.py                  # NOVO
│   │       ├── models.py                    # NOVO — Pydantic: NoteFrontmatter, SM2
│   │       ├── paths.py                     # NOVO — root discovery + type→dir
│   │       ├── note.py                      # NOVO — parse/write/new_note
│   │       └── index.py                     # NOVO — SQLite schema + ops
│   └── tests/
│       ├── __init__.py                      # NOVO
│       ├── conftest.py                      # NOVO — fixtures comuns
│       └── core/
│           ├── __init__.py                  # NOVO
│           ├── test_models.py               # NOVO
│           ├── test_paths.py                # NOVO
│           ├── test_note.py                 # NOVO
│           └── test_index.py                # NOVO
├── .mcp.json                                # NOVO — registra o MCP server local
└── .claude/skills/                          # NOVO
    ├── brainiac-capture/SKILL.md            # NOVO
    └── brainiac-recall/SKILL.md             # NOVO
```

**Responsabilidades:**

- `models.py` — schemas Pydantic puros (zero I/O); validação de frontmatter e SM-2.
- `paths.py` — todas as decisões "onde fica X" — descoberta do root, mapeamento tipo→pasta.
- `note.py` — operações com arquivos `.md`: parse, write, construção com defaults.
- `index.py` — toda a interação com SQLite: schema, index_note, reindex_all, search_fts, link operations.
- `mcp_server.py` — só camada de tools; delega tudo pro core.
- `cli.py` — entry points pra usuário humano + lançar o MCP server.

---

## Task 1: Project scaffolding

Cria a estrutura mínima do pacote Python e verifica que `pip install -e .` funciona.

**Files:**
- Create: `tools/brainiac/pyproject.toml`
- Create: `tools/brainiac/brainiac/__init__.py`
- Create: `tools/brainiac/brainiac/core/__init__.py`
- Create: `tools/brainiac/tests/__init__.py`
- Create: `tools/brainiac/tests/core/__init__.py`

- [ ] **Step 1: Criar `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "brainiac"
version = "0.1.0"
description = "Cognitive memory system — Phase 0 foundation"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0",
    "pydantic>=2",
    "python-frontmatter>=1.1",
    "click>=8",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff>=0.6",
]

[project.scripts]
brainiac = "brainiac.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["brainiac"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=brainiac --cov-report=term-missing"

[tool.coverage.run]
branch = true
omit = ["brainiac/mcp_server.py"]  # excluído nesta fase; integration test cobre via subprocess

[tool.ruff]
target-version = "py311"
line-length = 100
```

- [ ] **Step 2: Criar `brainiac/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Criar `brainiac/core/__init__.py`**

```python
```

(arquivo vazio — só marca package)

- [ ] **Step 4: Criar `tests/__init__.py` e `tests/core/__init__.py`**

Ambos arquivos vazios.

- [ ] **Step 5: Criar venv local em `tools/brainiac/.venv`**

Run:
```bash
cd tools/brainiac && python3 -m venv .venv
```

Expected: pasta `.venv/` criada. Já está no `.gitignore`.

- [ ] **Step 6: Instalar em modo editable dentro do venv**

Run:
```bash
cd tools/brainiac && .venv/bin/pip install -e ".[dev]"
```

Expected: instalação completa sem erros; pacote `brainiac` instalado dentro do venv.

- [ ] **Step 7: Verificar import**

Run: `cd tools/brainiac && .venv/bin/python -c "import brainiac; print(brainiac.__version__)"`
Expected: `0.1.0`

**Nota para os steps seguintes**: todos os comandos `pytest` e `brainiac` devem ser executados via venv. Use `.venv/bin/pytest` e `.venv/bin/brainiac`, ou ative o venv com `source .venv/bin/activate` no início da sessão.

- [ ] **Step 8: Commit**

```bash
git add tools/brainiac/
git commit -m "feat(phase-0): project scaffolding with pyproject + venv"
```

---

## Task 2: NoteFrontmatter Pydantic model

Define o schema central que todos os outros módulos validam contra.

**Files:**
- Create: `tools/brainiac/brainiac/core/models.py`
- Test: `tools/brainiac/tests/core/test_models.py`

- [ ] **Step 1: Escrever testes failing**

Conteúdo de `tests/core/test_models.py`:

```python
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from brainiac.core.models import SM2, NoteFrontmatter


def _base_fm(**overrides):
    defaults = dict(
        id="2026-05-20-foo",
        type="semantic",
        created=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        last_access=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        access_count=0,
        strength=1.0,
    )
    defaults.update(overrides)
    return defaults


class TestNoteFrontmatter:
    def test_minimal_valid(self):
        fm = NoteFrontmatter(**_base_fm())
        assert fm.id == "2026-05-20-foo"
        assert fm.tags == []
        assert fm.links == []
        assert fm.sm2 is None
        assert fm.source == "manual"

    def test_id_pattern_enforced(self):
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(id="bad id with spaces"))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(id="2026/05/20-foo"))

    def test_type_enum(self):
        for t in ("episodic", "semantic", "working"):
            NoteFrontmatter(**_base_fm(type=t))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(type="invalid"))

    def test_strength_bounds(self):
        NoteFrontmatter(**_base_fm(strength=0.0))
        NoteFrontmatter(**_base_fm(strength=1.0))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(strength=-0.1))
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(strength=1.1))

    def test_access_count_non_negative(self):
        with pytest.raises(ValidationError):
            NoteFrontmatter(**_base_fm(access_count=-1))

    def test_sm2_optional(self):
        fm = NoteFrontmatter(
            **_base_fm(sm2=SM2(ease=2.5, interval=1, next_review=date(2026, 5, 21)))
        )
        assert fm.sm2.ease == 2.5


class TestSM2:
    def test_defaults(self):
        sm2 = SM2(next_review=date(2026, 5, 21))
        assert sm2.ease == 2.5
        assert sm2.interval == 1
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'NoteFrontmatter' from 'brainiac.core.models'`

- [ ] **Step 3: Implementar `models.py`**

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NoteType = Literal["episodic", "semantic", "working"]
NoteSource = Literal["manual", "conversation", "import"]


class SM2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ease: float = Field(default=2.5, ge=1.3)
    interval: int = Field(default=1, ge=1)
    next_review: date


class NoteFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
    type: NoteType
    created: datetime
    last_access: datetime
    access_count: int = Field(ge=0)
    strength: float = Field(ge=0.0, le=1.0)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sm2: SM2 | None = None
    source: NoteSource = "manual"
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_models.py -v`
Expected: 7 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/models.py tools/brainiac/tests/core/test_models.py
git commit -m "feat(phase-0): NoteFrontmatter and SM2 Pydantic models"
```

---

## Task 3: parse/write_note

Lê e escreve `.md` com frontmatter YAML, validando contra Pydantic.

**Files:**
- Create: `tools/brainiac/brainiac/core/note.py`
- Test: `tools/brainiac/tests/core/test_note.py`

- [ ] **Step 1: Escrever testes failing**

Conteúdo de `tests/core/test_note.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brainiac.core.models import NoteFrontmatter
from brainiac.core.note import parse_note, write_note


def _make_fm():
    return NoteFrontmatter(
        id="2026-05-20-test",
        type="semantic",
        created=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        last_access=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        access_count=0,
        strength=1.0,
        tags=["alpha", "beta"],
    )


class TestWriteAndParseRoundtrip:
    def test_roundtrip_preserves_data(self, tmp_path: Path):
        fm = _make_fm()
        body = "# Título\n\n- bullet 1\n- bullet 2\n"
        path = tmp_path / "note.md"

        write_note(path, fm, body)

        fm2, body2 = parse_note(path)
        assert fm2.id == fm.id
        assert fm2.type == fm.type
        assert fm2.tags == fm.tags
        assert fm2.access_count == fm.access_count
        assert body2.strip() == body.strip()

    def test_write_creates_parent_dir(self, tmp_path: Path):
        fm = _make_fm()
        nested = tmp_path / "a" / "b" / "note.md"
        write_note(nested, fm, "# x\n")
        assert nested.exists()

    def test_parse_rejects_invalid_frontmatter(self, tmp_path: Path):
        path = tmp_path / "bad.md"
        path.write_text("---\nid: not-valid-id-format\n---\n# body\n", encoding="utf-8")
        with pytest.raises(Exception):  # ValidationError ou similar
            parse_note(path)

    def test_parse_handles_missing_optional_sm2(self, tmp_path: Path):
        fm = _make_fm()
        write_note(tmp_path / "n.md", fm, "# body\n")
        fm2, _ = parse_note(tmp_path / "n.md")
        assert fm2.sm2 is None
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_note.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `note.py`**

```python
from pathlib import Path

import frontmatter

from brainiac.core.models import NoteFrontmatter


def parse_note(path: Path) -> tuple[NoteFrontmatter, str]:
    """Read a .md note. Returns (frontmatter, body)."""
    post = frontmatter.load(str(path))
    fm = NoteFrontmatter.model_validate(post.metadata)
    return fm, post.content


def write_note(path: Path, fm: NoteFrontmatter, body: str) -> None:
    """Write a .md note with frontmatter. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = fm.model_dump(mode="json", exclude_none=True)
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_note.py -v`
Expected: 4 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/note.py tools/brainiac/tests/core/test_note.py
git commit -m "feat(phase-0): parse_note and write_note for .md files"
```

---

## Task 4: new_note helper

Constrói uma `NoteFrontmatter` com defaults sensatos (timestamps "agora", contadores zerados).

**Files:**
- Modify: `tools/brainiac/brainiac/core/note.py` (adicionar função)
- Modify: `tools/brainiac/tests/core/test_note.py` (adicionar classe de teste)

- [ ] **Step 1: Adicionar testes failing**

Adicionar ao final de `tests/core/test_note.py`:

```python
from brainiac.core.note import new_note


class TestNewNote:
    def test_defaults(self):
        fm = new_note(note_id="2026-05-20-x", note_type="semantic")
        assert fm.access_count == 0
        assert fm.strength == 1.0
        assert fm.source == "manual"
        assert fm.created == fm.last_access  # mesma timestamp inicialmente

    def test_overrides(self):
        fm = new_note(
            note_id="2026-05-20-y",
            note_type="episodic",
            tags=["mytag"],
            source="conversation",
        )
        assert fm.tags == ["mytag"]
        assert fm.source == "conversation"
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_note.py::TestNewNote -v`
Expected: FAIL — `cannot import name 'new_note'`.

- [ ] **Step 3: Adicionar `new_note` a `note.py`**

Adicionar no início (após imports):

```python
from datetime import datetime, timezone
```

E adicionar a função no final:

```python
def new_note(
    note_id: str,
    note_type: str,
    *,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    source: str = "manual",
) -> NoteFrontmatter:
    """Build a NoteFrontmatter with sensible defaults (timestamps=now, counters=0)."""
    now = datetime.now(timezone.utc)
    return NoteFrontmatter(
        id=note_id,
        type=note_type,  # type: ignore[arg-type]
        created=now,
        last_access=now,
        access_count=0,
        strength=1.0,
        tags=tags or [],
        links=links or [],
        source=source,  # type: ignore[arg-type]
    )
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_note.py -v`
Expected: 6 testes passam (4 existentes + 2 novos).

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/note.py tools/brainiac/tests/core/test_note.py
git commit -m "feat(phase-0): new_note helper with sensible defaults"
```

---

## Task 5: paths.py — root discovery e type→dir mapping

Centraliza toda decisão "onde fica X" — necessário porque o MCP/CLI pode ser invocado de qualquer subdir.

**Files:**
- Create: `tools/brainiac/brainiac/core/paths.py`
- Test: `tools/brainiac/tests/core/test_paths.py`

- [ ] **Step 1: Escrever testes failing**

Conteúdo de `tests/core/test_paths.py`:

```python
import os
from pathlib import Path

import pytest

from brainiac.core.paths import (
    TYPE_TO_DIR,
    find_root,
    index_db_path,
    note_dir,
    note_path,
)


@pytest.fixture
def fake_brainiac(tmp_path: Path) -> Path:
    """Creates a fake brainiac root with all 3 memory dirs."""
    for d in ("shortMemory", "longMemory/episodic", "semanticMemory", "memoryTransfer"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


class TestFindRoot:
    def test_finds_root_from_root(self, fake_brainiac: Path):
        assert find_root(fake_brainiac) == fake_brainiac

    def test_finds_root_from_subdir(self, fake_brainiac: Path):
        sub = fake_brainiac / "shortMemory"
        assert find_root(sub) == fake_brainiac

    def test_finds_root_from_deep_subdir(self, fake_brainiac: Path):
        deep = fake_brainiac / "longMemory" / "episodic"
        assert find_root(deep) == fake_brainiac

    def test_raises_when_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            find_root(tmp_path)

    def test_env_var_overrides(self, fake_brainiac: Path, monkeypatch, tmp_path: Path):
        unrelated = tmp_path / "elsewhere"
        unrelated.mkdir()
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        assert find_root(unrelated) == fake_brainiac


class TestTypeToDir:
    def test_mapping_is_complete(self):
        assert set(TYPE_TO_DIR) == {"working", "episodic", "semantic"}

    def test_note_dir(self, fake_brainiac: Path):
        assert note_dir(fake_brainiac, "working") == fake_brainiac / "shortMemory"
        assert note_dir(fake_brainiac, "episodic") == fake_brainiac / "longMemory" / "episodic"
        assert note_dir(fake_brainiac, "semantic") == fake_brainiac / "semanticMemory"

    def test_note_path(self, fake_brainiac: Path):
        p = note_path(fake_brainiac, "2026-05-20-x", "semantic")
        assert p == fake_brainiac / "semanticMemory" / "2026-05-20-x.md"


class TestIndexDbPath:
    def test_returns_path(self, fake_brainiac: Path):
        assert index_db_path(fake_brainiac) == fake_brainiac / "memoryTransfer" / "index.sqlite"
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_paths.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar `paths.py`**

```python
import os
from pathlib import Path

TYPE_TO_DIR: dict[str, str] = {
    "working": "shortMemory",
    "episodic": "longMemory/episodic",
    "semantic": "semanticMemory",
}

_ROOT_MARKERS = ("shortMemory", "semanticMemory")


def find_root(start: Path | None = None) -> Path:
    """Locate the brainiac root.

    Priority: BRAINIAC_ROOT env var > walk up from `start` (or cwd) looking
    for dirs that contain both `shortMemory/` and `semanticMemory/`.
    """
    if env := os.environ.get("BRAINIAC_ROOT"):
        return Path(env).resolve()

    p = (start or Path.cwd()).resolve()
    while True:
        if all((p / m).is_dir() for m in _ROOT_MARKERS):
            return p
        if p.parent == p:
            raise FileNotFoundError(
                f"Brainiac root not found from {start or Path.cwd()}. "
                f"Set BRAINIAC_ROOT or run from inside the project."
            )
        p = p.parent


def note_dir(root: Path, note_type: str) -> Path:
    """Filesystem dir where notes of this type live."""
    return root / TYPE_TO_DIR[note_type]


def note_path(root: Path, note_id: str, note_type: str) -> Path:
    """Full path for a note with given id and type."""
    return note_dir(root, note_type) / f"{note_id}.md"


def index_db_path(root: Path) -> Path:
    """Path to the SQLite index file."""
    return root / "memoryTransfer" / "index.sqlite"
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_paths.py -v`
Expected: 9 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/paths.py tools/brainiac/tests/core/test_paths.py
git commit -m "feat(phase-0): paths module — root discovery and type→dir mapping"
```

---

## Task 6: SQLite schema + connect()

Cria a conexão e aplica o schema de forma idempotente.

**Files:**
- Create: `tools/brainiac/brainiac/core/index.py`
- Create: `tools/brainiac/tests/core/test_index.py`
- Create: `tools/brainiac/tests/conftest.py`

- [ ] **Step 1: Criar fixtures comuns em `conftest.py`**

Conteúdo de `tests/conftest.py`:

```python
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
```

- [ ] **Step 2: Escrever testes failing para schema**

Conteúdo inicial de `tests/core/test_index.py`:

```python
import sqlite3
from pathlib import Path

import pytest


class TestConnect:
    def test_creates_db_file(self, fake_brainiac: Path):
        from brainiac.core.index import connect

        db = fake_brainiac / "memoryTransfer" / "index.sqlite"
        assert not db.exists()
        conn = connect(db)
        assert db.exists()
        conn.close()

    def test_creates_required_tables(self, conn: sqlite3.Connection):
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()}
        assert "notes" in names
        assert "notes_fts" in names
        assert "links" in names

    def test_idempotent(self, fake_brainiac: Path):
        from brainiac.core.index import connect

        db = fake_brainiac / "memoryTransfer" / "index.sqlite"
        connect(db).close()
        connect(db).close()  # segundo connect não deve falhar
```

- [ ] **Step 3: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: FAIL — `ImportError` (módulo `index` não existe).

- [ ] **Step 4: Implementar `index.py` mínimo**

```python
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('episodic','semantic','working')),
    created TEXT NOT NULL,
    last_access TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    strength REAL NOT NULL DEFAULT 1.0,
    tags TEXT,
    sm2_json TEXT,
    body_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    id UNINDEXED, title, body,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS links (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('explicit','implicit')),
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src, dst, kind)
);

CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_last_access ON notes(last_access);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection and ensure schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 5: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 3 testes passam.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/conftest.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): SQLite schema and idempotent connect()"
```

---

## Task 7: index_note()

Insere ou atualiza uma nota no índice (3 tabelas: `notes`, `notes_fts`, `links`).

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

Adicionar ao `tests/core/test_index.py`:

```python
from tests.conftest import make_fm  # se imports relativos não rodarem, use direto
from brainiac.core.index import index_note


class TestIndexNote:
    def test_inserts_into_notes(self, conn):
        fm = make_fm(note_id="2026-05-20-a", tags=["x"])
        index_note(conn, fm, "# Título\n\n- bullet", "semanticMemory/2026-05-20-a.md")

        row = conn.execute("SELECT id, path, type, access_count FROM notes WHERE id=?",
                           (fm.id,)).fetchone()
        assert row == ("2026-05-20-a", "semanticMemory/2026-05-20-a.md", "semantic", 0)

    def test_inserts_into_fts(self, conn):
        fm = make_fm(note_id="2026-05-20-b")
        index_note(conn, fm, "# Distributed Key Generation\n\nDKG protocol", "x.md")

        hit = conn.execute(
            "SELECT id FROM notes_fts WHERE notes_fts MATCH 'distributed'"
        ).fetchone()
        assert hit == ("2026-05-20-b",)

    def test_explicit_links_synced(self, conn):
        fm = make_fm(note_id="2026-05-20-c", links=["2026-05-20-other"])
        index_note(conn, fm, "# t", "x.md")

        row = conn.execute(
            "SELECT src, dst, kind FROM links WHERE src=?", (fm.id,)
        ).fetchone()
        assert row == ("2026-05-20-c", "2026-05-20-other", "explicit")

    def test_replace_on_reindex(self, conn):
        fm = make_fm(note_id="2026-05-20-d", links=["a"])
        index_note(conn, fm, "# v1", "x.md")
        fm2 = make_fm(note_id="2026-05-20-d", links=["b"])
        index_note(conn, fm2, "# v2", "x.md")

        # link antigo desapareceu, novo presente
        links = {r[1] for r in conn.execute(
            "SELECT src, dst FROM links WHERE src=?", (fm.id,)
        ).fetchall()}
        assert links == {"b"}

    def test_extracts_title_from_body(self, conn):
        fm = make_fm(note_id="2026-05-20-e")
        index_note(conn, fm, "# Meu Título\n\ncorpo", "x.md")

        title = conn.execute(
            "SELECT title FROM notes_fts WHERE id=?", (fm.id,)
        ).fetchone()
        assert title == ("Meu Título",)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestIndexNote -v`
Expected: FAIL — `cannot import name 'index_note'`.

- [ ] **Step 3: Adicionar `index_note` e helpers a `index.py`**

Adicionar imports e funções:

```python
import hashlib
import json
import sqlite3
from pathlib import Path

from brainiac.core.models import NoteFrontmatter


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def index_note(
    conn: sqlite3.Connection,
    fm: NoteFrontmatter,
    body: str,
    rel_path: str,
) -> None:
    """Insert or replace a note in all index tables. Syncs explicit links."""
    title = _extract_title(body)
    bh = _body_hash(body)

    conn.execute(
        """
        INSERT OR REPLACE INTO notes
        (id, path, type, created, last_access, access_count, strength,
         tags, sm2_json, body_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fm.id, rel_path, fm.type,
            fm.created.isoformat(), fm.last_access.isoformat(),
            fm.access_count, fm.strength,
            json.dumps(fm.tags),
            fm.sm2.model_dump_json() if fm.sm2 else None,
            bh,
        ),
    )

    # FTS5: delete + insert (FTS5 não suporta INSERT OR REPLACE com UNINDEXED)
    conn.execute("DELETE FROM notes_fts WHERE id = ?", (fm.id,))
    conn.execute(
        "INSERT INTO notes_fts (id, title, body) VALUES (?, ?, ?)",
        (fm.id, title, body),
    )

    # Sync explicit links: replace todos de src=fm.id, kind=explicit
    conn.execute(
        "DELETE FROM links WHERE src = ? AND kind = 'explicit'", (fm.id,)
    )
    for dst in fm.links:
        conn.execute(
            "INSERT OR IGNORE INTO links (src, dst, kind, weight) "
            "VALUES (?, ?, 'explicit', 1.0)",
            (fm.id, dst),
        )

    conn.commit()
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 8 testes passam (3 existentes + 5 novos).

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): index_note() — sync notes, fts, and explicit links"
```

---

## Task 8: reindex_all()

Reconstrói o índice integralmente a partir dos `.md` — a invariante crítica do sistema.

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

Adicionar ao `tests/core/test_index.py`:

```python
from brainiac.core.index import reindex_all
from brainiac.core.note import write_note


class TestReindexAll:
    def test_empty_brainiac_returns_zero(self, conn, fake_brainiac):
        n = reindex_all(conn, fake_brainiac)
        assert n == 0

    def test_indexes_notes_in_correct_dirs(self, conn, fake_brainiac):
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a", note_type="semantic"),
            "# A\n",
        )
        write_note(
            fake_brainiac / "shortMemory" / "2026-05-20-b.md",
            make_fm(note_id="2026-05-20-b", note_type="working"),
            "# B\n",
        )
        write_note(
            fake_brainiac / "longMemory" / "episodic" / "2026-05-20-c.md",
            make_fm(note_id="2026-05-20-c", note_type="episodic"),
            "# C\n",
        )

        n = reindex_all(conn, fake_brainiac)
        assert n == 3

        ids = {r[0] for r in conn.execute("SELECT id FROM notes").fetchall()}
        assert ids == {"2026-05-20-a", "2026-05-20-b", "2026-05-20-c"}

    def test_ignores_files_outside_memory_dirs(self, conn, fake_brainiac):
        # nota legítima
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a"),
            "# A\n",
        )
        # arquivo fora de memory dirs — não deve ser indexado
        (fake_brainiac / "docs").mkdir()
        (fake_brainiac / "docs" / "random.md").write_text("# not a note\n")
        (fake_brainiac / "README.md").write_text("# repo readme\n")

        n = reindex_all(conn, fake_brainiac)
        assert n == 1

    def test_skips_invalid_frontmatter_without_crashing(self, conn, fake_brainiac, capsys):
        # nota válida
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-good.md",
            make_fm(note_id="2026-05-20-good"),
            "# good\n",
        )
        # nota com frontmatter quebrado
        (fake_brainiac / "semanticMemory" / "broken.md").write_text(
            "---\nid: invalid format\n---\n# x\n", encoding="utf-8"
        )

        n = reindex_all(conn, fake_brainiac)
        assert n == 1  # só a boa contou
        captured = capsys.readouterr()
        assert "broken.md" in captured.out  # log do skip

    def test_idempotent_wipes_before_rebuild(self, conn, fake_brainiac):
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm(note_id="2026-05-20-a"),
            "# A\n",
        )
        reindex_all(conn, fake_brainiac)

        # remove o arquivo e roda de novo
        (fake_brainiac / "semanticMemory" / "2026-05-20-a.md").unlink()
        n = reindex_all(conn, fake_brainiac)
        assert n == 0
        rows = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
        assert rows == (0,)
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestReindexAll -v`
Expected: FAIL — `cannot import name 'reindex_all'`.

- [ ] **Step 3: Adicionar `reindex_all` a `index.py`**

```python
from brainiac.core.note import parse_note  # adicionar ao topo do arquivo

_MEMORY_DIRS = ("shortMemory", "longMemory", "semanticMemory")


def reindex_all(conn: sqlite3.Connection, root: Path) -> int:
    """Wipe and rebuild index from .md files in memory dirs. Returns count.

    Idempotent: result depends only on filesystem state, not previous index state.
    """
    conn.execute("DELETE FROM notes")
    conn.execute("DELETE FROM notes_fts")
    conn.execute("DELETE FROM links WHERE kind = 'explicit'")

    count = 0
    for md_file in root.rglob("*.md"):
        rel = md_file.relative_to(root)
        if not rel.parts or rel.parts[0] not in _MEMORY_DIRS:
            continue
        try:
            fm, body = parse_note(md_file)
            index_note(conn, fm, body, str(rel))
            count += 1
        except Exception as exc:
            print(f"skipping {rel}: {exc}")

    conn.commit()
    return count
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 13 testes passam (8 + 5 novos).

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): reindex_all() — rebuild index from .md as source of truth"
```

---

## Task 9: search_fts()

Busca top-k via FTS5 BM25. Esta é a `recall` da Fase 0; Fase 1 substitui por embeddings.

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

```python
from brainiac.core.index import search_fts


class TestSearchFts:
    def test_returns_matching_notes(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# Pizza\n\nfood from Italy", "x.md")
        index_note(conn, make_fm("2026-05-20-b"), "# Code\n\nPython programming", "y.md")

        results = search_fts(conn, "pizza", k=5)
        assert len(results) == 1
        assert results[0]["id"] == "2026-05-20-a"
        assert results[0]["type"] == "semantic"
        assert "title" in results[0]
        assert "snippet" in results[0]

    def test_respects_k_limit(self, conn):
        for i in range(5):
            index_note(conn, make_fm(f"2026-05-20-n{i}"),
                       f"# Topic {i}\n\nshared keyword across all", "x.md")
        results = search_fts(conn, "shared", k=3)
        assert len(results) == 3

    def test_empty_corpus(self, conn):
        assert search_fts(conn, "anything", k=5) == []

    def test_no_matches(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# foo", "x.md")
        assert search_fts(conn, "bar", k=5) == []

    def test_diacritic_insensitive(self, conn):
        index_note(conn, make_fm("2026-05-20-a"), "# café da manhã", "x.md")
        results = search_fts(conn, "cafe", k=5)
        assert len(results) == 1
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestSearchFts -v`
Expected: FAIL — `cannot import name 'search_fts'`.

- [ ] **Step 3: Adicionar `search_fts` a `index.py`**

```python
def search_fts(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
) -> list[dict]:
    """Top-k search via FTS5 + BM25 ranking."""
    rows = conn.execute(
        """
        SELECT n.id, n.path, n.type, fts.title,
               snippet(notes_fts, 2, '[', ']', '...', 32) as snippet
        FROM notes_fts fts
        JOIN notes n ON n.id = fts.id
        WHERE notes_fts MATCH ?
        ORDER BY bm25(notes_fts)
        LIMIT ?
        """,
        (query, k),
    ).fetchall()
    return [
        {"id": r[0], "path": r[1], "type": r[2], "title": r[3], "snippet": r[4]}
        for r in rows
    ]
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 18 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): search_fts() — BM25 top-k search"
```

---

## Task 10: get_note() com access tracking

Lê uma nota completa e incrementa `access_count` + atualiza `last_access`. Cada acesso vira evento auditável (logs serão arquivados em fase futura — agora só atualiza DB e arquivo).

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

```python
from datetime import datetime, timezone

from brainiac.core.index import get_note


class TestGetNote:
    def test_returns_note_data(self, conn, fake_brainiac):
        fm = make_fm(note_id="2026-05-20-a")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md", fm,
                   "# Title\n\ncorpo da nota")
        reindex_all(conn, fake_brainiac)

        result = get_note(conn, fake_brainiac, "2026-05-20-a")
        assert result["id"] == "2026-05-20-a"
        assert result["type"] == "semantic"
        assert "Title" in result["body"]
        assert result["frontmatter"]["access_count"] == 1  # incrementado

    def test_increments_access_count_on_disk(self, conn, fake_brainiac):
        path = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        write_note(path, make_fm(note_id="2026-05-20-a", access_count=2), "# x")
        reindex_all(conn, fake_brainiac)

        get_note(conn, fake_brainiac, "2026-05-20-a")

        fm_after, _ = parse_note(path)
        assert fm_after.access_count == 3

    def test_updates_last_access(self, conn, fake_brainiac):
        path = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        write_note(path, make_fm(note_id="2026-05-20-a"), "# x")
        reindex_all(conn, fake_brainiac)

        before = datetime.now(timezone.utc)
        get_note(conn, fake_brainiac, "2026-05-20-a")

        fm_after, _ = parse_note(path)
        assert fm_after.last_access >= before

    def test_raises_for_missing_note(self, conn, fake_brainiac):
        with pytest.raises(KeyError):
            get_note(conn, fake_brainiac, "2026-05-20-nonexistent")
```

Adicionar import no topo do arquivo de teste (se ainda não):
```python
from brainiac.core.note import parse_note
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestGetNote -v`
Expected: FAIL — `cannot import name 'get_note'`.

- [ ] **Step 3: Implementar `get_note`**

Adicionar a `index.py`:

```python
from datetime import datetime, timezone

from brainiac.core.note import parse_note, write_note


def get_note(conn: sqlite3.Connection, root: Path, note_id: str) -> dict:
    """Read a note, increment access_count, update last_access, reindex."""
    row = conn.execute(
        "SELECT path, type FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Note not found: {note_id}")

    rel_path, note_type = row
    full = root / rel_path
    fm, body = parse_note(full)

    fm.access_count += 1
    fm.last_access = datetime.now(timezone.utc)

    write_note(full, fm, body)
    index_note(conn, fm, body, rel_path)

    return {
        "id": fm.id,
        "type": fm.type,
        "path": rel_path,
        "frontmatter": fm.model_dump(mode="json"),
        "body": body,
    }
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 22 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): get_note() with access tracking"
```

---

## Task 11: link() — adicionar link explícito

Adiciona link `src → dst` editando o frontmatter da nota fonte E sincronizando o índice.

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

```python
from brainiac.core.index import add_link


class TestAddLink:
    def test_adds_link_in_frontmatter(self, conn, fake_brainiac):
        path_a = fake_brainiac / "semanticMemory" / "2026-05-20-a.md"
        path_b = fake_brainiac / "semanticMemory" / "2026-05-20-b.md"
        write_note(path_a, make_fm(note_id="2026-05-20-a"), "# A")
        write_note(path_b, make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(path_a)
        assert "2026-05-20-b" in fm_a.links

    def test_adds_link_in_db(self, conn, fake_brainiac):
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
                   make_fm(note_id="2026-05-20-a"), "# A")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md",
                   make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        row = conn.execute(
            "SELECT src, dst, kind FROM links WHERE src=? AND dst=?",
            ("2026-05-20-a", "2026-05-20-b"),
        ).fetchone()
        assert row == ("2026-05-20-a", "2026-05-20-b", "explicit")

    def test_idempotent_no_duplicates(self, conn, fake_brainiac):
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
                   make_fm(note_id="2026-05-20-a"), "# A")
        write_note(fake_brainiac / "semanticMemory" / "2026-05-20-b.md",
                   make_fm(note_id="2026-05-20-b"), "# B")
        reindex_all(conn, fake_brainiac)

        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")
        add_link(conn, fake_brainiac, "2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md")
        assert fm_a.links.count("2026-05-20-b") == 1

    def test_raises_for_missing_source(self, conn, fake_brainiac):
        with pytest.raises(KeyError):
            add_link(conn, fake_brainiac, "2026-05-20-missing", "2026-05-20-other")
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestAddLink -v`
Expected: FAIL — `cannot import name 'add_link'`.

- [ ] **Step 3: Implementar `add_link`**

Adicionar a `index.py`:

```python
def add_link(
    conn: sqlite3.Connection,
    root: Path,
    src: str,
    dst: str,
) -> None:
    """Add explicit link src→dst. Updates both frontmatter and index. Idempotent."""
    row = conn.execute(
        "SELECT path FROM notes WHERE id = ?", (src,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Source note not found: {src}")

    rel_path = row[0]
    full = root / rel_path
    fm, body = parse_note(full)

    if dst not in fm.links:
        fm.links.append(dst)
        write_note(full, fm, body)
        index_note(conn, fm, body, rel_path)
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 26 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): add_link() — sync frontmatter and index"
```

---

## Task 12: list_recent()

Lista as últimas N notas ordenadas por `last_access` desc — útil pra debug e pra a skill `brainiac-recall` quando não há query.

**Files:**
- Modify: `tools/brainiac/brainiac/core/index.py`
- Modify: `tools/brainiac/tests/core/test_index.py`

- [ ] **Step 1: Adicionar testes failing**

```python
class TestListRecent:
    def test_orders_by_last_access_desc(self, conn):
        from datetime import datetime, timezone, timedelta
        base = datetime(2026, 5, 20, 10, tzinfo=timezone.utc)
        for i in range(3):
            fm = NoteFrontmatter(
                id=f"2026-05-20-n{i}",
                type="semantic",
                created=base,
                last_access=base + timedelta(hours=i),
                access_count=0,
                strength=1.0,
            )
            index_note(conn, fm, f"# {i}", f"x{i}.md")

        from brainiac.core.index import list_recent
        results = list_recent(conn, limit=10)
        ids = [r["id"] for r in results]
        assert ids == ["2026-05-20-n2", "2026-05-20-n1", "2026-05-20-n0"]

    def test_respects_limit(self, conn):
        for i in range(5):
            index_note(conn, make_fm(f"2026-05-20-n{i}"), f"# {i}", "x.md")
        from brainiac.core.index import list_recent
        results = list_recent(conn, limit=2)
        assert len(results) == 2

    def test_empty_returns_empty(self, conn):
        from brainiac.core.index import list_recent
        assert list_recent(conn, limit=10) == []
```

Adicionar import no topo do arquivo de teste:
```python
from brainiac.core.models import NoteFrontmatter
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/core/test_index.py::TestListRecent -v`
Expected: FAIL — `cannot import name 'list_recent'`.

- [ ] **Step 3: Implementar `list_recent`**

```python
def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Return notes ordered by last_access desc."""
    rows = conn.execute(
        """
        SELECT id, path, type, last_access, access_count
        FROM notes
        ORDER BY last_access DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "path": r[1], "type": r[2],
            "last_access": r[3], "access_count": r[4],
        }
        for r in rows
    ]
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/core/test_index.py -v`
Expected: 29 testes passam.

- [ ] **Step 5: Commit**

```bash
git add tools/brainiac/brainiac/core/index.py tools/brainiac/tests/core/test_index.py
git commit -m "feat(phase-0): list_recent() — debug/browsing utility"
```

---

## Task 13: CLI — comandos reindex e stats

Entry point `brainiac` com subcomandos `reindex` (reconstrói índice) e `stats` (contadores).

**Files:**
- Create: `tools/brainiac/brainiac/cli.py`
- Create: `tools/brainiac/tests/test_cli.py`

- [ ] **Step 1: Escrever testes failing**

Conteúdo de `tests/test_cli.py`:

```python
from pathlib import Path

from click.testing import CliRunner

from brainiac.cli import main
from brainiac.core.note import write_note
from tests.conftest import make_fm


class TestReindexCommand:
    def test_reindex_counts_notes(self, fake_brainiac: Path, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm("2026-05-20-a"),
            "# A",
        )

        result = CliRunner().invoke(main, ["reindex"])
        assert result.exit_code == 0
        assert "1" in result.output  # contagem


class TestStatsCommand:
    def test_stats_shows_counts_by_type(self, fake_brainiac: Path, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        write_note(
            fake_brainiac / "semanticMemory" / "2026-05-20-a.md",
            make_fm("2026-05-20-a", note_type="semantic"),
            "# A",
        )
        write_note(
            fake_brainiac / "shortMemory" / "2026-05-20-b.md",
            make_fm("2026-05-20-b", note_type="working"),
            "# B",
        )
        CliRunner().invoke(main, ["reindex"])

        result = CliRunner().invoke(main, ["stats"])
        assert result.exit_code == 0
        assert "semantic" in result.output
        assert "working" in result.output
        assert "1" in result.output  # cada tipo aparece com count 1
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/test_cli.py -v`
Expected: FAIL — `cannot import name 'main' from 'brainiac.cli'`.

- [ ] **Step 3: Implementar `cli.py` (sem `mcp` ainda — chega na Task 14)**

```python
import click

from brainiac.core.index import connect, reindex_all
from brainiac.core.paths import find_root, index_db_path


@click.group()
def main() -> None:
    """brainiac — cognitive memory CLI"""


@main.command()
def reindex() -> None:
    """Rebuild the SQLite index from .md files."""
    root = find_root()
    conn = connect(index_db_path(root))
    n = reindex_all(conn, root)
    click.echo(f"reindexed {n} note(s) from {root}")


@main.command()
def stats() -> None:
    """Print counters by type and totals."""
    root = find_root()
    conn = connect(index_db_path(root))

    total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    by_type = conn.execute(
        "SELECT type, COUNT(*) FROM notes GROUP BY type ORDER BY type"
    ).fetchall()
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

    click.echo(f"root: {root}")
    click.echo(f"total notes: {total}")
    for t, c in by_type:
        click.echo(f"  {t}: {c}")
    click.echo(f"links: {link_count}")
```

- [ ] **Step 4: Rodar — esperar pass**

Run: `cd tools/brainiac && pytest tests/test_cli.py -v`
Expected: 2 testes passam.

- [ ] **Step 5: Verificar entry point**

Run: `brainiac --help`
Expected: lista `reindex` e `stats`.

- [ ] **Step 6: Commit**

```bash
git add tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_cli.py
git commit -m "feat(phase-0): CLI with reindex and stats subcommands"
```

---

## Task 14: MCP server com 5 tools + `brainiac mcp` CLI

Servidor MCP stdio expondo todas as 5 tools da Fase 0. Adiciona subcomando `mcp` à CLI.

**Files:**
- Create: `tools/brainiac/brainiac/mcp_server.py`
- Modify: `tools/brainiac/brainiac/cli.py`
- Create: `tools/brainiac/tests/test_mcp_server.py`

- [ ] **Step 1: Escrever teste failing**

`tests/test_mcp_server.py` — testa as funções subjacentes às tools (não a serialização MCP em si, que é coberta pelo SDK):

```python
from pathlib import Path

import pytest

from brainiac.core.note import parse_note, write_note
from brainiac.mcp_server import (
    tool_add_note,
    tool_get_note,
    tool_link,
    tool_list_recent,
    tool_recall,
)
from tests.conftest import make_fm


class TestToolAddNote:
    def test_creates_note_and_indexes(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = tool_add_note(
            note_id="2026-05-20-new",
            note_type="semantic",
            title="Pizza",
            body="# Pizza\n\nItalian food",
            tags=["food"],
        )
        assert result["id"] == "2026-05-20-new"
        assert (fake_brainiac / "semanticMemory" / "2026-05-20-new.md").exists()


class TestToolRecall:
    def test_finds_notes(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(
            note_id="2026-05-20-a", note_type="semantic",
            title="x", body="# Pizza\n\nfood", tags=[],
        )
        results = tool_recall("pizza", k=5)
        assert any(r["id"] == "2026-05-20-a" for r in results)


class TestToolGetNote:
    def test_returns_body_and_increments(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(
            note_id="2026-05-20-a", note_type="semantic",
            title="x", body="# A\n\ncorpo", tags=[],
        )
        result = tool_get_note("2026-05-20-a")
        assert "corpo" in result["body"]
        assert result["frontmatter"]["access_count"] == 1


class TestToolLink:
    def test_creates_link(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(note_id="2026-05-20-a", note_type="semantic", title="A", body="# A", tags=[])
        tool_add_note(note_id="2026-05-20-b", note_type="semantic", title="B", body="# B", tags=[])
        tool_link("2026-05-20-a", "2026-05-20-b")

        fm_a, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-a.md")
        assert "2026-05-20-b" in fm_a.links


class TestToolListRecent:
    def test_returns_recent(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        tool_add_note(note_id="2026-05-20-a", note_type="semantic", title="A", body="# A", tags=[])
        results = tool_list_recent(limit=10)
        assert len(results) == 1
        assert results[0]["id"] == "2026-05-20-a"
```

- [ ] **Step 2: Rodar — esperar fail**

Run: `cd tools/brainiac && pytest tests/test_mcp_server.py -v`
Expected: FAIL — `cannot import 'brainiac.mcp_server'`.

- [ ] **Step 3: Implementar `mcp_server.py`**

```python
"""MCP server exposing brainiac Phase 0 tools via stdio.

Tools (5):
- add_note: create a note with frontmatter
- recall: BM25 top-k search
- get_note: read note (increments access)
- link: add explicit link src→dst
- list_recent: last N notes by last_access
"""

import asyncio
import json
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from brainiac.core.index import (
    add_link,
    connect,
    get_note,
    index_note,
    list_recent,
    search_fts,
)
from brainiac.core.note import new_note, write_note
from brainiac.core.paths import find_root, index_db_path, note_path


# --- Pure tool functions (testable without MCP plumbing) ---

def tool_add_note(
    note_id: str,
    note_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
) -> dict:
    """Create a new note. Body should start with '# title'."""
    root = find_root()
    fm = new_note(note_id=note_id, note_type=note_type, tags=tags or [])

    # ensure body starts with a title line
    body_with_title = body if body.lstrip().startswith("#") else f"# {title}\n\n{body}"

    path = note_path(root, note_id, note_type)
    write_note(path, fm, body_with_title)

    conn = connect(index_db_path(root))
    rel = path.relative_to(root)
    index_note(conn, fm, body_with_title, str(rel))

    return {"id": note_id, "path": str(rel), "type": note_type}


def tool_recall(query: str, k: int = 5) -> list[dict]:
    """BM25 top-k search."""
    root = find_root()
    conn = connect(index_db_path(root))
    return search_fts(conn, query, k=k)


def tool_get_note(note_id: str) -> dict:
    """Read note; increments access_count."""
    root = find_root()
    conn = connect(index_db_path(root))
    return get_note(conn, root, note_id)


def tool_link(src: str, dst: str) -> dict:
    """Add explicit link src→dst."""
    root = find_root()
    conn = connect(index_db_path(root))
    add_link(conn, root, src, dst)
    return {"src": src, "dst": dst, "kind": "explicit"}


def tool_list_recent(limit: int = 10) -> list[dict]:
    """Last N notes ordered by last_access desc."""
    root = find_root()
    conn = connect(index_db_path(root))
    return list_recent(conn, limit=limit)


# --- MCP server plumbing ---

server = Server("brainiac")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
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
        Tool(
            name="recall",
            description="BM25 top-k search over notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_note",
            description="Read a note. Increments access_count and last_access.",
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
        Tool(
            name="link",
            description="Add explicit link from src note to dst note.",
            inputSchema={
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        ),
        Tool(
            name="list_recent",
            description="Last N notes by last_access.",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10}},
            },
        ),
    ]


_DISPATCH = {
    "add_note": tool_add_note,
    "recall": tool_recall,
    "get_note": tool_get_note,
    "link": tool_link,
    "list_recent": tool_list_recent,
}


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name}")
    try:
        result = fn(**(arguments or {}))
    except Exception as exc:
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def _run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def run_server() -> None:
    """Sync entry point for `brainiac mcp`."""
    asyncio.run(_run())
```

- [ ] **Step 4: Adicionar comando `mcp` à CLI**

Adicionar ao final de `brainiac/cli.py`:

```python
@main.command()
def mcp() -> None:
    """Start the MCP stdio server."""
    from brainiac.mcp_server import run_server
    run_server()
```

- [ ] **Step 5: Rodar testes**

Run: `cd tools/brainiac && pytest tests/test_mcp_server.py -v`
Expected: 5 testes passam.

- [ ] **Step 6: Sanity check do servidor (manual)**

Run: `timeout 1 brainiac mcp || true`
Expected: o servidor inicia e timeout o mata (stdio aguardando input). Sem traceback.

- [ ] **Step 7: Commit**

```bash
git add tools/brainiac/brainiac/mcp_server.py tools/brainiac/brainiac/cli.py tools/brainiac/tests/test_mcp_server.py
git commit -m "feat(phase-0): MCP server with 5 tools + brainiac mcp command"
```

---

## Task 15: Skills `brainiac-capture` e `brainiac-recall`

Skills locais que orquestram os workflows mais comuns. Salvas em `.claude/skills/` na raiz do projeto (não em `tools/`).

**Files:**
- Create: `.claude/skills/brainiac-capture/SKILL.md`
- Create: `.claude/skills/brainiac-recall/SKILL.md`

- [ ] **Step 1: Criar diretórios**

Run:
```bash
mkdir -p .claude/skills/brainiac-capture .claude/skills/brainiac-recall
```

- [ ] **Step 2: Escrever `brainiac-capture/SKILL.md`**

```markdown
---
name: brainiac-capture
description: Salva uma nova nota no brainiac. Use quando o usuário diz "anota isso", "guarda essa ideia", "salva no brainiac", ou pede explicitamente para registrar conhecimento. Determina tipo (episódico / semântico / working), gera id YYYY-MM-DD-slug, popula frontmatter completo.
---

# Brainiac Capture

Orquestra a criação de uma nota bem-formada via MCP tool `add_note`.

## Quando usar

- Usuário pede explicitamente: "salva isso", "anota", "guarda no brainiac"
- Usuário compartilha um aprendizado/conceito/decisão que tem valor de longo prazo
- Ao final de uma exploração técnica que vale persistir

## Passos

1. **Determinar tipo** da nota:
   - `episodic` — narrativa pessoal com timestamp/contexto ("hoje eu fiz X", "decidimos Y na reunião")
   - `semantic` — conceito/fato descontextualizado ("Kubernetes scheduler funciona assim", "BM25 é uma função de ranking")
   - `working` — ideia ainda crua, a ser refinada/promovida depois (rascunho)
   Se ambíguo, pergunte ao usuário.

2. **Gerar `note_id`**: formato `YYYY-MM-DD-slug` onde `slug` é kebab-case ≤ 40 chars, descritivo (não genérico como "note" ou "ideia").

3. **Escrever body tokenizado** (regra do README): bullets densos > prosa. Sem prefácios ("Esta nota fala sobre..."). Direto ao ponto. Use `[[outro-id]]` para cross-refs.

4. **Tags**: 1-3 tags em kebab-case que ajudariam buscar isso depois.

5. **Chamar `add_note`** via MCP com `note_id`, `note_type`, `title`, `body`, `tags`.

6. **Confirmar ao usuário**: arquivo salvo em `<pasta>/<id>.md`.

## Exemplo

Usuário: "anota que `bm25` é uma função de ranking que considera frequência do termo e tamanho do doc"

Você:
- Tipo: `semantic` (conceito impessoal)
- ID: `2026-05-20-bm25-ranking`
- Body: `# BM25\n\n- função de ranking probabilística para busca textual\n- inputs: frequência do termo, tamanho do documento, idf\n- usada em [[fts5-sqlite]] como default scoring`
- Tags: `["information-retrieval", "ranking"]`
- Chamar `add_note(...)`
- Confirmar: "Salvo em semanticMemory/2026-05-20-bm25-ranking.md"
```

- [ ] **Step 3: Escrever `brainiac-recall/SKILL.md`**

```markdown
---
name: brainiac-recall
description: Busca no brainiac por uma query e sintetiza uma resposta contextual com as notas relevantes. Use quando o usuário pergunta sobre algo que ele provavelmente já registrou, ou pede explicitamente "veja no brainiac", "lembre o que sabemos sobre X".
---

# Brainiac Recall

Orquestra busca + leitura das notas mais relevantes via MCP tools `recall` + `get_note`.

## Quando usar

- Usuário pergunta sobre tópico que ele provavelmente já anotou
- Usuário pede: "veja no brainiac", "o que sabemos sobre X", "lembra aquilo de..."
- Antes de explicar conceito que pode ter sido registrado anteriormente — vale checar

## Passos

1. **Chamar `recall(query, k=5)`** com a query em pt-BR (FTS5 funciona com pt-BR direto). Receba lista de notas com `id`, `title`, `snippet`, `path`.

2. **Avaliar os snippets**: se algum parece claramente relevante, leia integralmente via `get_note(note_id)`. Isso também incrementa `access_count` (sinal de relevância pra fase 2).

3. **Sintetizar resposta**:
   - Use o conhecimento da(s) nota(s) como contexto autoritativo
   - Cite cada nota usada por `id` (ex: "conforme anotado em `2026-05-20-bm25-ranking`...")
   - Se houver gaps na informação, diga claramente — não invente

4. **Sugerir nota nova** se a resposta levou a um insight que vale a pena persistir (handoff implícito pra `brainiac-capture`).

## Quando não usar

- Pergunta sobre algo claramente fora do escopo das notas do usuário (ex: "qual a capital da França" — não invocar)
- Conversa puramente operacional (rodar comando, debugar erro local)

## Exemplo

Usuário: "lembra como funciona aquele algoritmo de ranking que vimos?"

Você:
1. `recall("algoritmo de ranking", k=5)` → retorna `[{id: "2026-05-20-bm25-ranking", snippet: "função de ranking probabilística..."}]`
2. `get_note("2026-05-20-bm25-ranking")` → corpo completo
3. Resposta: "Você anotou sobre BM25 em `2026-05-20-bm25-ranking`. É uma função de ranking probabilística que considera frequência do termo, tamanho do doc e IDF. Foi mencionada como default scoring do FTS5 do SQLite. Quer expandir algum ponto?"
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/
git commit -m "feat(phase-0): brainiac-capture and brainiac-recall skills"
```

---

## Task 16: `.mcp.json` + E2E smoke test + coverage check

Registra o servidor MCP no projeto e valida o fluxo completo end-to-end.

**Files:**
- Create: `.mcp.json`
- Create: `tools/brainiac/tests/test_smoke_e2e.py`

- [ ] **Step 1: Criar `.mcp.json` na raiz do projeto**

```json
{
  "mcpServers": {
    "brainiac": {
      "command": "brainiac",
      "args": ["mcp"]
    }
  }
}
```

- [ ] **Step 2: Escrever smoke test E2E**

Conteúdo de `tools/brainiac/tests/test_smoke_e2e.py`:

```python
"""End-to-end smoke: exerce o fluxo capture → recall → get → reindex sem MCP plumbing."""

from pathlib import Path

import pytest

from brainiac.core.note import parse_note
from brainiac.mcp_server import (
    tool_add_note,
    tool_get_note,
    tool_link,
    tool_list_recent,
    tool_recall,
)


def test_full_workflow(fake_brainiac: Path, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))

    # 1. Capture 3 notas
    tool_add_note(
        note_id="2026-05-20-bm25",
        note_type="semantic",
        title="BM25",
        body="# BM25\n\n- função de ranking probabilística\n- usada em FTS5",
        tags=["ir", "ranking"],
    )
    tool_add_note(
        note_id="2026-05-20-fts5",
        note_type="semantic",
        title="FTS5",
        body="# FTS5\n\n- extensão SQLite para full-text search\n- usa [[2026-05-20-bm25]] por default",
        tags=["sqlite"],
    )
    tool_add_note(
        note_id="2026-05-20-jantar",
        note_type="episodic",
        title="Jantar de aniversário",
        body="# Jantar\n\nHoje jantei na pizzaria",
        tags=["pessoal"],
    )

    # 2. Link explícito
    tool_link("2026-05-20-fts5", "2026-05-20-bm25")

    # 3. Recall por conceito (deve encontrar bm25)
    results = tool_recall("ranking", k=5)
    assert any(r["id"] == "2026-05-20-bm25" for r in results)

    # 4. Recall em pt-BR
    results_pt = tool_recall("aniversário", k=5)
    assert any(r["id"] == "2026-05-20-jantar" for r in results_pt)

    # 5. get_note incrementa access
    note = tool_get_note("2026-05-20-bm25")
    assert "ranking" in note["body"]
    assert note["frontmatter"]["access_count"] == 1

    # 6. list_recent ordena por last_access (bm25 acessado mais recente)
    recent = tool_list_recent(limit=10)
    assert recent[0]["id"] == "2026-05-20-bm25"

    # 7. Arquivos físicos batem
    assert (fake_brainiac / "semanticMemory" / "2026-05-20-bm25.md").exists()
    assert (fake_brainiac / "semanticMemory" / "2026-05-20-fts5.md").exists()
    assert (fake_brainiac / "longMemory" / "episodic" / "2026-05-20-jantar.md").exists()

    # 8. Link foi persistido no frontmatter
    fm_fts5, _ = parse_note(fake_brainiac / "semanticMemory" / "2026-05-20-fts5.md")
    assert "2026-05-20-bm25" in fm_fts5.links


def test_reindex_after_manual_edit(fake_brainiac: Path, monkeypatch):
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))

    tool_add_note(
        note_id="2026-05-20-x",
        note_type="semantic",
        title="x", body="# x\n\noriginal", tags=[],
    )

    # simula edição manual do .md (adiciona tag)
    from brainiac.core.note import parse_note, write_note
    path = fake_brainiac / "semanticMemory" / "2026-05-20-x.md"
    fm, body = parse_note(path)
    fm.tags = ["manually-added"]
    write_note(path, fm, body)

    # reindex via CLI-equivalent
    from brainiac.core.index import connect, reindex_all
    from brainiac.core.paths import index_db_path
    conn = connect(index_db_path(fake_brainiac))
    n = reindex_all(conn, fake_brainiac)
    assert n == 1

    # recall via tag agora funciona (tags estão em notes.tags JSON)
    result = conn.execute(
        "SELECT tags FROM notes WHERE id = ?", ("2026-05-20-x",)
    ).fetchone()
    assert "manually-added" in result[0]
```

- [ ] **Step 3: Rodar todos os testes**

Run: `cd tools/brainiac && pytest -v`
Expected: TODOS os testes passam (deve estar próximo de 35).

- [ ] **Step 4: Verificar coverage**

Run: `cd tools/brainiac && pytest --cov=brainiac.core --cov-report=term-missing`
Expected: cobertura ≥ 80% em `brainiac.core.note` e `brainiac.core.index`. Se falhar nesse threshold, adicionar tests pra cobrir branches faltando.

- [ ] **Step 5: Validar config MCP (manual)**

No Claude Code, com `.mcp.json` em vigor, reinicie a sessão e verifique que o server `brainiac` aparece em `/mcp`. Teste invocar `add_note` e `recall` via prompt.

- [ ] **Step 6: Commit final da Fase 0**

```bash
git add .mcp.json tools/brainiac/tests/test_smoke_e2e.py
git commit -m "feat(phase-0): .mcp.json registration + E2E smoke test

DoD da Fase 0 atingida:
- brainiac mcp inicia e responde ao Claude Code
- /brainiac-capture salva nota com frontmatter válido
- /brainiac-recall recupera por query
- brainiac reindex reconstrói o índice corretamente
- Cobertura ≥ 80% em note.py e index.py"
```

---

## Definition of Done — Fase 0

Checklist final da spec (§5 Fase 0):

- [ ] `brainiac mcp` inicia e Claude Code conecta via `.mcp.json`
- [ ] `/brainiac-capture` salva nota; arquivo aparece na pasta correta com frontmatter válido
- [ ] `/brainiac-recall "termo"` recupera a nota
- [ ] `brainiac reindex` reconstrói índice corretamente após edição manual de `.md`
- [ ] Cobertura de testes ≥ 80% em `note.py` e `index.py`

Após a Fase 0 estar verde, gerar o plano da **Fase 1 — Recall associativo** invocando novamente `superpowers:writing-plans`.
