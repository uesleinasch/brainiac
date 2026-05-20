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
