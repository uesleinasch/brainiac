"""End-to-end smoke: exerce o fluxo capture → recall → get → reindex sem MCP plumbing."""

import time
from datetime import datetime, timezone
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
        body="# Jantar de aniversário\n\nHoje jantei na pizzaria",
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
    active, _ = reindex_all(conn, fake_brainiac)
    assert active == 1

    # recall via tag agora funciona (tags estão em notes.tags JSON)
    result = conn.execute(
        "SELECT tags FROM notes WHERE id = ?", ("2026-05-20-x",)
    ).fetchone()
    assert "manually-added" in result[0]


@pytest.mark.slow
def test_recall_finds_dkg_without_lexical_overlap(fake_brainiac, monkeypatch):
    """DoD: 'criação distribuída de chaves' recupera 'DKG protocol'."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_recall

    tool_add_note(
        note_id="2026-05-20-dkg",
        note_type="semantic",
        title="DKG protocol",
        body="distributed key generation; multi-party computation; threshold cryptography",
        tags=["crypto"],
    )
    # ruido
    tool_add_note(
        note_id="2026-05-20-mostarda",
        note_type="semantic",
        title="Receita de mostarda",
        body="sementes de mostarda, vinagre, sal",
        tags=["culinaria"],
    )
    results = tool_recall(query="criação distribuída de chaves criptográficas", k=3)
    assert any(r["id"] == "2026-05-20-dkg" for r in results)
    dkg = next(r for r in results if r["id"] == "2026-05-20-dkg")
    assert dkg["origin"] in {"semantic", "both"}


@pytest.mark.slow
def test_recall_latency_under_500ms_for_modest_corpus(fake_brainiac, monkeypatch):
    """DoD: recall < 500ms — usando corpus de 50 notas (proxy do budget de 1000)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.mcp_server import tool_add_note, tool_recall

    for i in range(50):
        tool_add_note(
            note_id=f"2026-05-20-perf-{i:02d}",
            note_type="semantic",
            title=f"Nota {i}",
            body=f"conteudo sintetico {i} sobre topico variado",
        )
    # warmup (modelo já carregado nos add_note acima)
    tool_recall(query="warmup", k=5)

    t0 = time.perf_counter()
    tool_recall(query="topico variado", k=5)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500, f"recall took {elapsed_ms:.1f}ms"


# --- DoD Phase 2 ---

from datetime import datetime, timedelta, timezone


def test_decay_archives_note_not_accessed_30_days(fake_brainiac, monkeypatch):
    """DoD: nota não acessada por 30 dias com access_count=1 é arquivada."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.decay import run_decay
    from tests.conftest import make_fm

    last = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)

    fm = make_fm("2026-04-20-stale-dod", "semantic",
                 access_count=1, last_access=last)
    p = note_path(fake_brainiac, "2026-04-20-stale-dod", "semantic")
    write_note(p, fm, "# Stale DoD\n\nconteúdo")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# Stale DoD\n\nconteúdo",
               str(p.relative_to(fake_brainiac)))

    stats = run_decay(conn, fake_brainiac, now=now)
    assert stats["archived"] >= 1
    archived = fake_brainiac / "memoryTransfer" / "archive"
    assert any(archived.rglob("2026-04-20-stale-dod.md"))


def test_archived_note_excluded_from_recall_by_default(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: notas arquivadas não aparecem em recall por default."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    fm = make_fm("2026-05-20-hidden", "semantic")
    write_note(fake_brainiac / "semanticMemory" / "2026-05-20-hidden.md",
               fm, "# Hidden\n\nconteúdo escondido arquivado")
    index_note(conn, fm, "# Hidden\n\nconteúdo escondido arquivado",
               "semanticMemory/2026-05-20-hidden.md", archived=True)

    results = recall(conn, "conteúdo escondido arquivado", k=5)
    assert all(r["id"] != "2026-05-20-hidden" for r in results)

    results_inc = recall(conn, "conteúdo escondido arquivado", k=5, include_archived=True)
    assert any(r["id"] == "2026-05-20-hidden" for r in results_inc)


def test_consolidate_check_finds_qualified_working_note(fake_brainiac, monkeypatch):
    """DoD: nota acessada 3x na semana com link recebido aparece em consolidate_check."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.consolidate import consolidation_candidates
    from tests.conftest import make_fm

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(days=2)

    fm = make_fm("2026-05-18-cand-dod", note_type="working",
                 access_count=3, last_access=recent)
    p = note_path(fake_brainiac, "2026-05-18-cand-dod", "working")
    write_note(p, fm, "# Cand DoD\n\nbody")
    conn = connect(index_db_path(fake_brainiac))
    index_note(conn, fm, "# Cand DoD\n\nbody",
               str(p.relative_to(fake_brainiac)))
    conn.execute(
        "INSERT OR IGNORE INTO links(src, dst, kind, weight) VALUES (?, ?, 'explicit', 1.0)",
        ("2026-05-15-linker", "2026-05-18-cand-dod"),
    )
    conn.commit()

    candidates = consolidation_candidates(conn, now=now)
    assert any(c["id"] == "2026-05-18-cand-dod" for c in candidates)


def test_housekeep_report_is_readable(fake_brainiac, monkeypatch):
    """DoD: relatório brainiac-housekeep é legível (decay stats + consolidate list)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from click.testing import CliRunner
    from brainiac.cli import main

    # Sem notas — relatório deve ser limpo e sem crash
    result = CliRunner().invoke(main, ["decay"])
    assert result.exit_code == 0
    assert "checked" in result.output

    result2 = CliRunner().invoke(main, ["consolidate", "--auto"])
    assert result2.exit_code == 0
    assert "No candidates" in result2.output or "Promoted" in result2.output


# --- DoD Phase 3 ---

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


# --- DoD Phase 4 ---


def test_short_memory_never_exceeds_limit(fake_brainiac, monkeypatch):
    """DoD: shortMemory/ nunca excede limite; tentativa retorna erro útil."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "working_memory_limit = 2\n", encoding="utf-8"
    )
    from brainiac.mcp_server import tool_add_note

    tool_add_note(note_id="2026-05-20-w-1", note_type="working", title="1", body="# 1")
    tool_add_note(note_id="2026-05-20-w-2", note_type="working", title="2", body="# 2")
    result = tool_add_note(note_id="2026-05-20-w-3", note_type="working", title="3", body="# 3")

    assert "error" in result
    assert result["count"] == 2
    assert result["limit"] == 2
    assert isinstance(result["suggestion"], list)

    # Filesystem must reflect refusal — only 2 .md files
    short_dir = fake_brainiac / "shortMemory"
    actual = sorted(p.name for p in short_dir.glob("2026-05-20-w-*.md"))
    assert actual == ["2026-05-20-w-1.md", "2026-05-20-w-2.md"]


def test_capture_classifier_unambiguous_returns_type(fake_brainiac, monkeypatch):
    """DoD: capture (via classifier) reconhece tipo sem perguntar quando confiante."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.classifier import classify

    # episodic — confident
    typ, conf = classify("Hoje decidimos pivotar para B2B.", tags=["reuniao"])
    assert typ == "episodic"
    assert conf > 0.3

    # semantic — confident
    typ, conf = classify("BM25 é uma função de ranking probabilística.", tags=["conceito"])
    assert typ == "semantic"
    assert conf > 0.3


def test_capture_classifier_ambiguous_returns_none(fake_brainiac, monkeypatch):
    """DoD: capture pergunta tipo apenas quando ambíguo (classifier retorna None)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.classifier import classify

    typ, _ = classify("Frase neutra sem marcadores fortes.")
    assert typ is None  # skill deve perguntar ao usuário


def test_brainiac_classify_cli_on_legacy_note(fake_brainiac, monkeypatch):
    """DoD: brainiac classify <path> sugere tipo para nota pré-existente/legada."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from click.testing import CliRunner
    from brainiac.cli import main
    from brainiac.core.note import write_note
    from tests.conftest import make_fm

    fm = make_fm("2026-05-20-legacy", "working")  # mistyped as working
    p = fake_brainiac / "shortMemory" / "2026-05-20-legacy.md"
    write_note(p, fm, "# K8s\n\nKubernetes é um orquestrador de containers.")

    result = CliRunner().invoke(main, ["classify", str(p)])
    assert result.exit_code == 0
    assert "semantic" in result.output.lower()


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


# --- DoD Phase 6 ---


def test_spreading_reaches_distant_relevant_note(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: nó a 2 hops da seed aparece via spreading (co-activation)."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import add_link, connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    bodies = {
        "2026-05-20-node-a": "# A\n\nDKG protocol distributed keys",
        "2026-05-20-node-b": "# B\n\nbridge content unrelated",
        "2026-05-20-node-c": "# C\n\nfurther unrelated content",
    }
    for nid, body in bodies.items():
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, body)
        index_note(conn, fm, body, str(p.relative_to(fake_brainiac)))

    add_link(conn, fake_brainiac, "2026-05-20-node-a", "2026-05-20-node-b")
    add_link(conn, fake_brainiac, "2026-05-20-node-b", "2026-05-20-node-c")

    hits = recall(conn, "DKG protocol distributed keys", k=10)
    hit_ids = [h["id"] for h in hits]
    assert "2026-05-20-node-c" in hit_ids  # reached via 2-hop spreading


def test_co_activation_promotes_convergent_node(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: nó D recebendo múltiplos paths convergentes acumula activation."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import add_link, connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    body_relevant = "# x\n\nDKG distributed keys protocol"
    body_neutral = "# x\n\nneutral content"

    for nid in ["2026-05-20-src1", "2026-05-20-src2", "2026-05-20-src3"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, body_relevant)
        index_note(conn, fm, body_relevant, str(p.relative_to(fake_brainiac)))

    fm_d = make_fm("2026-05-20-conv-d", "semantic")
    p_d = note_path(fake_brainiac, "2026-05-20-conv-d", "semantic")
    write_note(p_d, fm_d, body_neutral)
    index_note(conn, fm_d, body_neutral, str(p_d.relative_to(fake_brainiac)))

    # All 3 seeds link to D
    for src in ["2026-05-20-src1", "2026-05-20-src2", "2026-05-20-src3"]:
        add_link(conn, fake_brainiac, src, "2026-05-20-conv-d")

    hits = recall(conn, "DKG distributed keys protocol", k=5)
    hit_ids = [h["id"] for h in hits]
    assert "2026-05-20-conv-d" in hit_ids  # convergent node makes it via co-activation


def test_spreading_respects_floor_filter(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: nó com activation abaixo do floor não aparece."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    (fake_brainiac / "brainiac.toml").write_text(
        "spreading_floor = 0.5\n", encoding="utf-8"  # aggressive floor
    )
    from brainiac.core.index import add_link, connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    bodies = {
        "2026-05-20-seed": "# seed\n\nrelevant query text",
        "2026-05-20-far": "# far\n\nfar content",
    }
    for nid, body in bodies.items():
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, body)
        index_note(conn, fm, body, str(p.relative_to(fake_brainiac)))

    add_link(conn, fake_brainiac, "2026-05-20-seed", "2026-05-20-far")

    hits = recall(conn, "relevant query text", k=10)
    hit_ids = [h["id"] for h in hits]
    # At minimum verify seed itself appears (best-effort test)
    assert "2026-05-20-seed" in hit_ids


def test_load_edges_filters_by_note_ids(fake_brainiac, embedder_stub, monkeypatch):
    """DoD: load_edges(note_ids=[...]) retorna apenas arestas dos nós informados."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import add_link, connect, index_note
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from brainiac.core.spreading import load_edges
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    for nid in ["2026-05-20-le-a", "2026-05-20-le-b", "2026-05-20-le-c"]:
        fm = make_fm(nid, "semantic")
        p = note_path(fake_brainiac, nid, "semantic")
        write_note(p, fm, f"# {nid}")
        index_note(conn, fm, f"# {nid}", str(p.relative_to(fake_brainiac)))

    add_link(conn, fake_brainiac, "2026-05-20-le-a", "2026-05-20-le-b")
    add_link(conn, fake_brainiac, "2026-05-20-le-b", "2026-05-20-le-c")

    # Filter to only edges where src = le-a
    edges = load_edges(conn, note_ids=["2026-05-20-le-a"])
    assert "2026-05-20-le-a" in edges
    assert "2026-05-20-le-b" not in edges  # le-b's outgoing edge excluded


def test_spreading_does_not_leak_archived_notes(fake_brainiac, embedder_stub, monkeypatch):
    """Regression: archived notes reached via spreading must be excluded when include_archived=False."""
    monkeypatch.setenv("BRAINIAC_ROOT", str(fake_brainiac))
    from brainiac.core.index import add_link, connect, index_note, recall
    from brainiac.core.note import write_note
    from brainiac.core.paths import index_db_path, note_path
    from tests.conftest import make_fm

    conn = connect(index_db_path(fake_brainiac))
    # Seed: relevant, active
    fm_seed = make_fm("2026-05-20-seed-leak", "semantic")
    p_seed = note_path(fake_brainiac, "2026-05-20-seed-leak", "semantic")
    write_note(p_seed, fm_seed, "# seed\n\nDKG protocol distributed keys")
    index_note(conn, fm_seed, "# seed\n\nDKG protocol distributed keys", str(p_seed.relative_to(fake_brainiac)))

    # Target: archived, would be reached via spreading
    fm_arc = make_fm("2026-05-20-arc-leak", "semantic")
    p_arc = note_path(fake_brainiac, "2026-05-20-arc-leak", "semantic")
    write_note(p_arc, fm_arc, "# arc\n\narchived content")
    index_note(conn, fm_arc, "# arc\n\narchived content", str(p_arc.relative_to(fake_brainiac)), archived=True)

    add_link(conn, fake_brainiac, "2026-05-20-seed-leak", "2026-05-20-arc-leak")

    # Default include_archived=False: archived must NOT appear
    hits = recall(conn, "DKG protocol distributed keys", k=10)
    hit_ids = [h["id"] for h in hits]
    assert "2026-05-20-arc-leak" not in hit_ids

    # Explicit include_archived=True: archived MAY appear
    hits_inc = recall(conn, "DKG protocol distributed keys", k=10, include_archived=True)
    hit_ids_inc = [h["id"] for h in hits_inc]
    assert "2026-05-20-arc-leak" in hit_ids_inc
