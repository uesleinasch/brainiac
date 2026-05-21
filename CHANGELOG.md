# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Estrutura completa de governança open-source: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`
- Templates de issue (bug, feature, question) e pull request em `.github/`
- `CODEOWNERS` para reviewers automáticos
- Workflow de CI (`.github/workflows/ci.yml`): pytest em Python 3.11/3.12, ruff lint, shellcheck nos scripts
- `scripts/install.sh` — instalador one-line para Linux (clona, cria venv, configura memory root, instala skills, registra MCP server)
- `scripts/update.sh` — atualizador idempotente
- `docs/MAINTAINING.md` com guia de branch protection rules e processo de release

---

## [0.1.0] — 2026-05-21

Primeira release pública. Todas as 8 fases do roadmap inicial implementadas com 340 testes verdes.

### Adicionado

#### Phase 0 — Foundation
- Servidor MCP via stdio (`mcp>=1.0`)
- Índice SQLite com FTS5 (busca textual)
- CRUD de notas com frontmatter YAML strict (Pydantic v2)
- CLI `brainiac` com Click 8

#### Phase 1 — Recall associativo
- Embeddings multilíngues 384-dim (`paraphrase-multilingual-MiniLM-L12-v2`)
- Índice vetorial via `sqlite-vec` (cosine distance)
- Expansão 1-hop no grafo de links explícitos `[[note-id]]`

#### Phase 2 — Consolidação + Decay
- Curva de Ebbinghaus (`R = e^(-t/S)`) com `S` cumulativo por acesso
- Arquivamento automático de notas abaixo do threshold de retenção
- Promoção working → long_term via critério booleano (`access_count ≥ 3 AND fan_in ≥ 1`)

#### Phase 3 — SM-2 Spaced Repetition
- Algoritmo SuperMemo-2 (Wozniak) com grade 0-5
- Fila de revisão ordenada por urgência
- Campo `sm2` opcional no frontmatter (`ease`, `interval`, `reps`, `next_review`)

#### Phase 4 — Working memory + tipos
- Limite hard de working memory (`working_memory_limit`, default 9)
- Recusa de inserção quando cheio, com candidatos a promover/descartar
- Classificador heurístico léxico pt-BR (`episodic` / `semantic` / `working`)

#### Phase 5 — ACT-R Activation
- Tabela `accesses` (log append-only)
- Cálculo de activation ACT-R: `A(t) = ln Σᵢ tᵢ^(-d)` (Anderson 1996)
- Sources de access: `get`, `review`, `recall_hit`, `link_in`
- 2º caminho de promoção: borderline (`access_count = 2 + activation ≥ 1.5`)
- MCP tool `inspect_note` + CLI `brainiac inspect`

#### Phase 6 — Spreading Activation
- Propagação N-hop no grafo (default `max_hops=3`)
- Decay multiplicativo por hop (default `decay=0.5`)
- Floor e epsilon para evitar runaway
- Combinação z-score normalizada de semantic + activation no ranking

#### Phase 7 — Consolidação Probabilística
- Campo `emotional_weight ∈ [0,1]` no frontmatter (default 0.5)
- Coluna `novelty_score` em `notes` (cache de `1 − max cosine_sim` com top-3 vizinhos)
- 3º caminho de promoção: `P = 1 − e^(−α·R·E·n) ≥ 0.6`
- Parâmetro `emotional_weight` no MCP tool `add_note`

#### Phase 8 — Atkinson-Shiffrin States
- Tabela `sensory_buffer` (rascunhos transientes, TTL 5 min default)
- Enum `NoteState`: `sensory → working → long_term ↔ archived`
- `transition_note()` com enforcement de Markov chain (pulos rejeitados)
- `_resurrect()` para `archived → long_term`
- `transition_probabilities()` calibrada via P_enc / P_cons (Phase 7) / P_forget (Ebbinghaus)
- 5 novos MCP tools: `capture_sensory`, `list_sensory`, `commit_sensory`, `transition_note`, `note_state`
- 2 novos CLI commands: `brainiac state <id>`, `brainiac sensory list`

### Tecnologia
- Python ≥ 3.11
- Sem deps externas além de: `mcp`, `pydantic`, `python-frontmatter`, `click`, `sentence-transformers`, `sqlite-vec`, `numpy`
- 100% local: nenhum serviço de rede, banco externo ou UI

### Qualidade
- 340 testes (excluindo `test_embeddings.py` slow)
- Cobertura ≥ 80% global; ≥ 95% nos módulos críticos (`novelty`, `sensory`, `states`)
- TDD aplicado durante todas as 8 phases
- Schema migrations idempotentes em `connect()`

---

[Não lançado]: https://github.com/uesleinasch/brainiac/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/uesleinasch/brainiac/releases/tag/v0.1.0
