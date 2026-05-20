# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Importante

- Sempre use o plugin context-mode
- Sempre use o superpower para execução de tarefas

## Project overview

**Brainiac** is two things in one repo:

1. **A personal knowledge base** — `.md` notes filed in cognitive-science-inspired memory directories (`longMemory/`, `shortMemory/`, `semanticMemory/`, with `memoryTransfer/` as the system layer for index + archive + logs).
2. **A Python software project** in `tools/brainiac/` that powers the knowledge base: MCP server (stdio), CLI, SQLite index (FTS5 + sqlite-vec embeddings), Ebbinghaus decay, SuperMemo-2 spaced repetition, and a pt-BR type classifier.

Content language is **Brazilian Portuguese**. Write notes and user-facing strings in pt-BR unless asked otherwise. Code, comments, docstrings, and commit messages are in English (commit subject line OK in pt-BR for project-specific terminology).

## Memory model (content side)

The directory layout mirrors a cognitive-science model of human memory:

- **`longMemory/episodic/`** — narrative pessoal com timestamp ("hoje fui à reunião"); persiste indefinidamente.
- **`shortMemory/`** — working memory; limite configurável (default 9 itens ativos via `brainiac.toml`). O sistema **recusa** adicionar quando cheia, retornando candidatos a promover/descartar.
- **`semanticMemory/`** — fatos/conceitos descontextualizados ("BM25 é uma função de ranking probabilística").
- **`memoryTransfer/`** — sistema (não conteúdo): `index.sqlite`, `archive/<ano>/`, `logs/events.jsonl`.

Tipo (`episodic` / `semantic` / `working`) é determinado pelo classificador heurístico em `core/classifier.py` quando capturamos via skill `brainiac-capture`. Se o classificador retornar ambíguo, pergunte ao usuário.

## Note conventions (token-optimized)

Notas são `.md` com frontmatter YAML carregando metadata cognitiva (`type`, `created`, `last_access`, `access_count`, `strength`, `links`, `tags`, opcionalmente `sm2`).

- Bullets densos > prosa. Evite filler ("Esta nota fala sobre...", "Em resumo...").
- Cross-refs com `[[outro-id]]` — parser converte em links explícitos no índice.
- IDs no formato `YYYY-MM-DD-slug` (kebab-case, ≤ 40 chars, descritivo).
- Nunca duplicar fato entre memórias — linkar.

Terseness é regra dura, não preferência estilística — texto longo encarece recall futuro.

## Software architecture (`tools/brainiac/`)

```
tools/brainiac/brainiac/
├── core/
│   ├── models.py          # Pydantic v2: NoteFrontmatter, SM2
│   ├── note.py            # parse/write .md + frontmatter
│   ├── paths.py           # find_root, note_path, index_db_path
│   ├── index.py           # SQLite + FTS5 + vec0; recall(), reindex_all()
│   ├── embeddings.py      # sentence-transformers lazy-load
│   ├── graph.py           # 1-hop expansion no grafo de links
│   ├── events.py          # logger append-only events.jsonl
│   ├── decay.py           # Ebbinghaus (S, R) + archive_note + run_decay
│   ├── consolidate.py     # candidates + promote_note (working → long)
│   ├── sm2.py             # SuperMemo-2 + review_queue + grade_review
│   ├── working_memory.py  # count + candidates + capacity check + status
│   ├── classifier.py      # heurística léxica pt-BR
│   └── config.py          # brainiac.toml loader (frozen dataclass)
├── mcp_server.py          # 11 MCP tools registradas
└── cli.py                 # 7 comandos click
```

**Padrão arquitetural recorrente:** módulos do `core/` separam funções puras (pure math/SQL helpers, sem I/O) de I/O (toca disco + DB + log). Veja `decay.py` e `sm2.py` como exemplos canônicos.

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
.venv/bin/brainiac review
.venv/bin/brainiac classify path/to/nota.md
.venv/bin/brainiac mcp        # servidor stdio para Claude Code
```

### Convenções de código

- **TDD obrigatório** para novas features no `core/`: RED (teste falha) → GREEN (implementação mínima) → commit. Veja qualquer plano em `docs/superpowers/plans/` para o padrão.
- **Cobertura ≥ 80%** por módulo do `core/` — ideal 100% para módulos puros.
- **Asserções concretas, nunca tautológicas.** Pinning de valor (`assert ease == pytest.approx(2.18)`) > `assert ease < 2.5`. Code reviewers pegam isso e exigem fix.
- **Sem novas deps pip sem justificativa.** Phase 0-4 inteira foi entregue só com `mcp`, `pydantic`, `python-frontmatter`, `sentence-transformers`, `sqlite-vec`, `click` + stdlib.
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

Para features grandes: skills `superpowers:writing-plans` (gera plano detalhado em `docs/superpowers/plans/`) + `superpowers:subagent-driven-development` (executa task-por-task com revisão de spec compliance + code quality). As 4 fases entregues seguiram esse pipeline; planos servem como referência viva.

## State atual

- **204 testes verdes** (fora `test_embeddings.py` que é slow)
- Roadmap de 5 fases (Foundation → Recall → Decay → SM-2 → Working memory) completo
- Specs e planos em `docs/superpowers/`
- Licença MIT
