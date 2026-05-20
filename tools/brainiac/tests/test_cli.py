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


from datetime import date, datetime, timezone


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

        fm = make_fm("2026-05-19-due-review", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-due-review", "semantic")
        write_note(p, fm, "# due\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# due\n\nbody", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["review"], input="5\n")
        assert result.exit_code == 0
        assert "2026-05-19-due-review" in result.output
        assert "Reviewed →" in result.output

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

    def test_review_quit_via_q(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import parse_note, write_note
        from brainiac.core.paths import index_db_path, note_path
        from brainiac.core.models import SM2
        from tests.conftest import make_fm

        fm = make_fm("2026-05-19-quit", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-quit", "semantic")
        write_note(p, fm, "# quit\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# quit\n\nbody", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["review"], input="q\n")
        assert result.exit_code == 0
        assert "Session complete" in result.output
        # state unchanged after quit
        fm_after, _ = parse_note(p)
        assert fm_after.sm2.reps == 0
        assert fm_after.sm2.next_review == date(2026, 5, 19)

    def test_review_invalid_input_treated_as_skip(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import parse_note, write_note
        from brainiac.core.paths import index_db_path, note_path
        from brainiac.core.models import SM2
        from tests.conftest import make_fm

        fm = make_fm("2026-05-19-bad", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-bad", "semantic")
        write_note(p, fm, "# bad\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# bad\n\nbody", str(p.relative_to(fake_brainiac)))

        # garbage input + out-of-range
        result = CliRunner().invoke(main, ["review"], input="abc\n")
        assert result.exit_code == 0
        assert "invalid input" in result.output
        # state unchanged
        fm_after, _ = parse_note(p)
        assert fm_after.sm2.reps == 0

    def test_review_out_of_range_grade_skipped(self, fake_brainiac, monkeypatch):
        monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
        from brainiac.core.index import connect, index_note
        from brainiac.core.note import parse_note, write_note
        from brainiac.core.paths import index_db_path, note_path
        from brainiac.core.models import SM2
        from tests.conftest import make_fm

        fm = make_fm("2026-05-19-oor", "semantic")
        fm.sm2 = SM2(ease=2.5, interval=1, reps=0, next_review=date(2026, 5, 19))
        p = note_path(fake_brainiac, "2026-05-19-oor", "semantic")
        write_note(p, fm, "# oor\n\nbody")
        conn = connect(index_db_path(fake_brainiac))
        index_note(conn, fm, "# oor\n\nbody", str(p.relative_to(fake_brainiac)))

        result = CliRunner().invoke(main, ["review"], input="9\n")
        assert result.exit_code == 0
        assert "out of range" in result.output
        # state unchanged
        fm_after, _ = parse_note(p)
        assert fm_after.sm2.reps == 0


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
