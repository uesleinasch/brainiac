# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Importante

- Sempre use o plugin context-mode
- Sempre use o superpower para execução de tarefas

## Project overview

**Brainiac** is two things in one repo:

1. **A personal knowledge base** — `.md` notes filed in cognitive-science-inspired memory directories (`longMemory/`, `shortMemory/`, `semanticMemory/`, with `memoryTransfer/` as the system layer for index + archive + logs).
2. **A Python software project** in `tools/brainiac/` that powers the knowledge base: MCP server (stdio), CLI, SQLite index (FTS5 + sqlite-vec embeddings), Ebbinghaus decay, ACT-R activation, spreading activation, probabilistic consolidation, Atkinson-Shiffrin state machine, SuperMemo-2 spaced repetition, and a pt-BR type classifier.

Content language is **Brazilian Portuguese**. Write notes and user-facing strings in pt-BR unless asked otherwise. Code, comments, docstrings, and commit messages are in English (commit subject line OK in pt-BR for project-specific terminology).

## Memory model (content side)

The directory layout mirrors a cognitive-science model of human memory, plus a transient sensory buffer in SQLite (Phase 8):

- **sensory** — buffer transiente (`sensory_buffer` table, TTL ~5 min); rascunhos crus antes de virar nota real. NÃO está no filesystem.
- **`longMemory/episodic/`** — narrative pessoal com timestamp ("hoje fui à reunião"); persiste indefinidamente.
- **`shortMemory/`** — working memory; limite configurável (default 9 itens ativos via `brainiac.toml`). O sistema **recusa** adicionar quando cheia, retornando candidatos a promover/descartar.
- **`semanticMemory/`** — fatos/conceitos descontextualizados ("BM25 é uma função de ranking probabilística").
- **`memoryTransfer/`** — sistema (não conteúdo): `index.sqlite`, `archive/<ano>/`, `logs/events.jsonl`.

Estados Atkinson-Shiffrin (`sensory → working → long_term ↔ archived`) com transições Markov-enforced em `core/states.py`. Tipo (`episodic` / `semantic` / `working`) é determinado pelo classificador heurístico em `core/classifier.py` quando capturamos via skill `brainiac-capture`. Se o classificador retornar ambíguo, pergunte ao usuário.

## Note conventions (token-optimized)

Notas são `.md` com frontmatter YAML carregando metadata cognitiva (`type`, `created`, `last_access`, `access_count`, `strength`, `links`, `tags`, `source`, `emotional_weight ∈ [0,1]` (default 0.5), opcionalmente `sm2`).

- Bullets densos > prosa. Evite filler ("Esta nota fala sobre...", "Em resumo...").
- Cross-refs com `[[outro-id]]` — parser converte em links explícitos no índice.
- IDs no formato `YYYY-MM-DD-slug` (kebab-case, ≤ 40 chars, descritivo).
- Nunca duplicar fato entre memórias — linkar.

Terseness é regra dura, não preferência estilística — texto longo encarece recall futuro.

## Software architecture (`tools/brainiac/`)

```
tools/brainiac/brainiac/
├── core/
│   ├── models.py          # Pydantic v2: NoteFrontmatter (com emotional_weight), SM2
│   ├── note.py            # parse/write .md + frontmatter
│   ├── paths.py           # find_root, note_path, index_db_path
│   ├── index.py           # SQLite + FTS5 + vec0; recall(), reindex_all()
│   │                       # Schema migrations idempotentes: archived, emotional_weight,
│   │                       # novelty_score, accesses, sensory_buffer
│   ├── embeddings.py      # sentence-transformers lazy-load
│   ├── graph.py           # 1-hop expansion (legado; recall agora usa spreading)
│   ├── events.py          # logger append-only events.jsonl
│   ├── decay.py           # Ebbinghaus (S, R) + archive_note + run_decay
│   ├── consolidate.py     # 3 paths: booleano + ACT-R borderline + probabilístico
│   ├── sm2.py             # SuperMemo-2 + review_queue + grade_review
│   ├── working_memory.py  # count + candidates + capacity check + status
│   ├── classifier.py      # heurística léxica pt-BR
│   ├── config.py          # brainiac.toml loader (frozen dataclass)
│   ├── activation.py      # ACT-R: record_access, activation, activation_batch
│   ├── spreading.py       # N-hop spreading activation no grafo
│   ├── novelty.py         # cosine-distance novelty + cache em notes.novelty_score
│   ├── sensory.py         # buffer transiente: add/list/get/commit/expire
│   └── states.py          # NoteState enum + current_state + transition_note (Markov)
│                           # + transition_probabilities (calibrado via P2/P5/P7)
├── mcp_server.py          # 17 MCP tools registradas
└── cli.py                 # 10 comandos click (group: sensory)
```

**Padrão arquitetural recorrente:** módulos do `core/` separam funções puras (pure math/SQL helpers, sem I/O) de I/O (toca disco + DB + log). Veja `decay.py`, `sm2.py`, `novelty.py` como exemplos canônicos.

### Tabelas no `index.sqlite`

- `notes` — frontmatter + body_hash + archived + emotional_weight + novelty_score
- `notes_fts` — FTS5 (id, title, body) com unicode61 + remove_diacritics
- `notes_vec` — vec0 (id, embedding[384])
- `links` — (src, dst, kind ∈ {explicit, implicit}, weight)
- `accesses` — log append-only (note_id, ts, source ∈ {get, review, recall_hit, link_in}, weight) (Phase 5)
- `sensory_buffer` — rascunhos transientes (id, title, body, created, expires_at, proposed_type, proposed_id) (Phase 8)

## Working in this repo

### Comandos comuns

```bash
# Setup uma vez
cd tools/brainiac && python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Rodar suite (exclui testes que carregam embeddings — lentos)
.venv/bin/pytest --ignore=tests/core/test_embeddings.py

# Suite com cobertura
.venv/bin/pytest --cov=brainiac --cov-report=term-missing --ignore=tests/core/test_embeddings.py

# Sub-suite específica
.venv/bin/pytest tests/core/test_sm2.py -v --no-cov

# CLI
.venv/bin/brainiac reindex
.venv/bin/brainiac stats
.venv/bin/brainiac decay --dry-run
.venv/bin/brainiac consolidate --auto
.venv/bin/brainiac review
.venv/bin/brainiac classify path/to/nota.md
.venv/bin/brainiac inspect 2026-05-20-foo    # 3 eixos + acessos
.venv/bin/brainiac state 2026-05-20-foo      # estado + transition probabilities
.venv/bin/brainiac sensory list              # rascunhos sensory ativos
.venv/bin/brainiac mcp                       # servidor stdio para Claude Code
```

### Convenções de código

- **TDD obrigatório** para novas features no `core/`: RED (teste falha) → GREEN (implementação mínima) → commit. Veja qualquer plano em `docs/superpowers/plans/` para o padrão.
- **Cobertura ≥ 80%** por módulo do `core/` — ideal 100% para módulos puros.
- **Asserções concretas, nunca tautológicas.** Pinning de valor (`assert ease == pytest.approx(2.18)`) > `assert ease < 2.5`. Code reviewers pegam isso e exigem fix.
- **Sem novas deps pip sem justificativa.** Todas as 8 fases foram entregues só com `mcp`, `pydantic`, `python-frontmatter`, `sentence-transformers`, `sqlite-vec`, `click` + stdlib (`math`, `uuid`, `enum`, `datetime`, `sqlite3`, `tomllib`).
- **Lazy imports** dentro de funções MCP/CLI para evitar ciclos e custos de cold start.
- **Sem comentários óbvios.** Docstrings só onde o WHY não é trivial (ex: fórmula SM-2, branch de decay).
- **`pt-BR` em descrições de MCP tools e mensagens de skill**; código/docstrings em inglês.

### Git workflow

Repositório git com `main` como branch base. Fases novas → branch `phase-N-<short-name>` → merge `--no-ff` com mensagem detalhada. Workflow ilustrado nas fases já mergeadas:

```bash
git log --oneline main      # ver entregas anteriores
git checkout -b phase-N-foo
# ... TDD loop, commits frequentes ...
git checkout main && git merge --no-ff phase-N-foo
git branch -d phase-N-foo
```

### Planejamento e execução com superpowers

Para features grandes: skills `superpowers:writing-plans` (gera plano detalhado em `docs/superpowers/plans/`) + `superpowers:executing-plans` ou `superpowers:subagent-driven-development` (executa task-por-task com revisão de spec compliance + code quality). As 8 fases entregues seguiram esse pipeline; planos servem como referência viva.

## State atual

- **340 testes verdes** (fora `test_embeddings.py` que é slow)
- Roadmap de 8 fases completo:
  - Phase 0 — Foundation (MCP + SQLite + FTS5)
  - Phase 1 — Recall associativo (embeddings 384-dim + 1-hop)
  - Phase 2 — Consolidação + Decay (Ebbinghaus + working → long booleano)
  - Phase 3 — SM-2 Spaced Repetition
  - Phase 4 — Working memory + tipos (limite hard + classifier)
  - Phase 5 — ACT-R Activation (`accesses` table + log-decay)
  - Phase 6 — Spreading Activation (N-hop)
  - Phase 7 — Consolidação Probabilística (`emotional_weight` + novelty)
  - Phase 8 — Atkinson-Shiffrin States (sensory_buffer + Markov + transition probs)
- Cobertura ≥ 95% nos módulos novos (`novelty`, `sensory`, `states`)
- Specs e planos em `docs/superpowers/`
- Licença MIT
