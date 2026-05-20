"""End-to-end smoke: exerce o fluxo capture → recall → get → reindex sem MCP plumbing."""

import time
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
