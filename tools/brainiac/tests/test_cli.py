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
