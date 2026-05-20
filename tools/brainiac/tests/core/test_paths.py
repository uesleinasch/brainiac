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
