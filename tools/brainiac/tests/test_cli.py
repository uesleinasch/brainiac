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


from datetime import datetime, timezone


class TestDecayCommand:
    def test_decay_dry_run_does_not_archive(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from brainiac.core.index import connect, reindex_all
        from brainiac.core.paths import index_db_path
        from tests.conftest import make_fm

        old_access = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
        fm = make_fm("2026-03-21-stale", "semantic",
                     last_access=old_access, access_count=0)
        write_note(fake_brainiac / "semanticMemory" / "2026-03-21-stale.md", fm, "# Stale")
        conn = connect(index_db_path(fake_brainiac))
        reindex_all(conn, fake_brainiac)

        result = CliRunner().invoke(main, ["decay", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output
        assert (fake_brainiac / "semanticMemory" / "2026-03-21-stale.md").exists()

    def test_decay_archives_weak_note(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from brainiac.core.index import connect, reindex_all
        from brainiac.core.paths import index_db_path
        from tests.conftest import make_fm

        old_access = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
        fm = make_fm("2026-03-21-weak", "semantic",
                     last_access=old_access, access_count=0)
        write_note(fake_brainiac / "semanticMemory" / "2026-03-21-weak.md", fm, "# Weak")
        conn = connect(index_db_path(fake_brainiac))
        reindex_all(conn, fake_brainiac)

        result = CliRunner().invoke(main, ["decay"])
        assert result.exit_code == 0
        assert "archived: 1" in result.output
        assert not (fake_brainiac / "semanticMemory" / "2026-03-21-weak.md").exists()

    def test_decay_output_shows_stats(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = CliRunner().invoke(main, ["decay"])
        assert result.exit_code == 0
        assert "checked" in result.output


class TestConsolidateCommand:
    def test_consolidate_no_candidates(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        result = CliRunner().invoke(main, ["consolidate", "--auto"])
        assert result.exit_code == 0
        assert "No candidates" in result.output

    def test_consolidate_auto_promotes_candidate(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.note import write_note
        from brainiac.core.index import connect, index_note
        from brainiac.core.paths import index_db_path, note_path
        from tests.conftest import make_fm
        from datetime import timedelta

        now_dt = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        recent = now_dt - timedelta(days=2)
        fm = make_fm("2026-05-18-auto", note_type="working",
                     access_count=5, last_access=recent)
        p = note_path(fake_brainiac, "2026-05-18-auto", "working")
        write_note(p, fm, "# auto\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# auto\n\nbody", str(p.relative_to(fake_brainiac)))
        conn.execute(
            "INSERT OR IGNORE INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
            ("2026-05-15-other", "2026-05-18-auto"),
        )
        conn.commit()

        result = CliRunner().invoke(main, ["consolidate", "--auto"])
        assert result.exit_code == 0
        assert "Promoted 1" in result.output
        assert (fake_brainiac / "semanticMemory" / "2026-05-18-auto.md").exists()
