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
