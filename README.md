# Brainiac

Um "segundo cérebro" pessoal em arquivos Markdown que replica mecânicas centrais da memória humana: **modelo Atkinson-Shiffrin** (sensory → working → long_term ↔ archived), consolidação probabilística com peso emocional + novidade, curva de esquecimento (Ebbinghaus), recall associativo via embeddings + spreading activation N-hop no grafo, revisão espaçada (SuperMemo-2), ativação ACT-R, e distinção episódico/semântico com limite de working memory.

Conteúdo em **português brasileiro**, armazenado em formato tokenizado (bullets densos > prosa) para otimizar buscas e custo de contexto futuro.

## Modelo de memória

```
brainiac/
├── longMemory/          # retenção indefinida (anos/vida)
│   └── episodic/        # narrativa pessoal com timestamp
├── shortMemory/         # working memory (limite configurável, default 9)
├── semanticMemory/      # fatos/conceitos descontextualizados
└── memoryTransfer/      # sistema: índice SQLite, archive, logs
    ├── archive/<ano>/   # notas arquivadas por decay
    ├── logs/events.jsonl
    └── index.sqlite     # FTS5 + vec0 (embeddings 384-dim) + accesses + sensory_buffer
```

### 4 estados Atkinson-Shiffrin

```
sensory ──► working ──► long_term ◄──► archived
(TTL 5min)  (≤ 9)       (semantic|episodic)
```

- **sensory** — rascunho transiente no buffer (5 min TTL, derivado de `sensory_buffer`)
- **working** — ideia em construção em `shortMemory/` (limite hard configurável)
- **long_term** — `semanticMemory/` ou `longMemory/episodic/`, retenção indefinida
- **archived** — `memoryTransfer/archive/<ano>/`, reversível via `transition_note`

Transições enforcam Markov chain: pulos inválidos (ex: `working → archived`) são rejeitados.

### 3 eixos cognitivos por nota

- **retention** (Ebbinghaus): `strength ∈ [0,1]`, decai com idade desde último acesso
- **activation** (ACT-R): soma de log-decays sobre os timestamps em `accesses`, com booster de recall_hit e link_in
- **sm2** (SuperMemo-2): `ease`, `interval`, `reps`, `next_review` para revisão espaçada opcional

### 3 caminhos de promoção working → long_term

1. **Booleano** (Phase 2): `access_count ≥ 3 AND fan_in ≥ 1`
2. **ACT-R borderline** (Phase 5): `access_count = 2 AND fan_in ≥ 1 AND activation ≥ 1.5`
3. **Probabilístico** (Phase 7): `P = 1 − e^(−α·R·E·n) ≥ 0.6`, onde
   - `R` = access_count, `E` = emotional_weight ∈ [0,1], `n` = novelty (1 − max cosine_sim com top-3 vizinhos)
   - permite promover notas importantes/novas com baixo R desde que E e n compensem

### Recall com spreading activation N-hop

Query → top-k semântico (cosine) + propagação por arestas no grafo até `spreading_max_hops` (default 3), com decay multiplicativo por hop e floor para evitar runaway. Combina com ACT-R via z-score normalizado por query (`α·semantic + β·activation`).

Cada nota é um `.md` com frontmatter YAML carregando metadata cognitiva (`type`, `created`, `last_access`, `access_count`, `strength`, `links`, `tags`, `sm2`, `emotional_weight`, `source`).

## Stack

- **Python ≥ 3.11** (`tomllib`, `math`, `uuid`, `enum` stdlib)
- **MCP** (`mcp>=1.0`) — servidor stdio para clientes MCP-compatíveis (Claude Code, etc.)
- **SQLite + sqlite-vec** — FTS5 + índice vetorial em um único arquivo
- **sentence-transformers** — `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, pt-BR)
- **Pydantic v2** — schema strict do frontmatter
- **Click 8** — CLI

Sem dependências de cloud, banco externo ou UI. Tudo local, em arquivos.

## Quickstart

```bash
# Instalação
cd tools/brainiac
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Inicia MCP server (para Claude Code)
.venv/bin/brainiac mcp

# Ou use a CLI diretamente
.venv/bin/brainiac stats
```

Aponte o brainiac para o root das suas memórias com a variável `BRAINIAC_ROOT` ou rode os comandos a partir do diretório que contém `shortMemory/`, `longMemory/`, `semanticMemory/`, `memoryTransfer/`.

## Comandos CLI (9)

```
brainiac mcp                  # inicia servidor MCP (stdio) para Claude Code
brainiac reindex              # reconstrói index.sqlite varrendo .md
brainiac stats                # contadores por tipo, total, links, arquivadas, top-5 activation
brainiac decay [--dry-run]    # roda Ebbinghaus; arquiva notas abaixo do threshold
brainiac consolidate [--auto] # promove working → semantic/episodic (3 paths)
brainiac review [--limit N]   # sessão interativa SM-2 (grade 0-5)
brainiac classify <path>      # sugere tipo para nota legada
brainiac inspect <id>         # 3 eixos cognitivos + últimos 10 acessos
brainiac state <id>           # estado atual + probabilidades de transição
brainiac sensory list         # lista rascunhos sensory ativos
```

## MCP Tools (17)

**Capture & retrieval**
- `add_note` — cria nota (aceita `emotional_weight` e `study=true`)
- `recall` — top-k semântico + spreading N-hop + activation boost
- `get_note` — lê + incrementa access_count
- `link` — adiciona aresta explícita src → dst
- `list_recent` — N mais recentes por `last_access`

**Lifecycle**
- `consolidate_check` — lista candidatos working → long_term (3 paths)
- `forget` — arquiva agora (reversível)
- `transition_note` — Markov transition entre estados
- `note_state` — estado atual + probabilidades calibradas

**Sensory buffer**
- `capture_sensory` — rascunho transiente (TTL 5min)
- `list_sensory` — rascunhos ativos
- `commit_sensory` — promove rascunho para nota real

**Spaced repetition (SM-2)**
- `review_queue` — fila ordenada por urgência
- `grade_review` — aplica grade 0-5
- `start_review` — inscreve nota existente em SM-2

**Inspeção**
- `working_status` — ocupação da shortMemory + candidatos
- `inspect_note` — snapshot retention + activation + sm2 + acessos

## Skills Claude Code

- `brainiac-capture` — salva nova nota (classificador de tipo + emotional_weight opcional)
- `brainiac-recall` — busca e sintetiza
- `brainiac-housekeep` — ciclo semanal decay + consolidate
- `brainiac-review` — sessão SM-2 interativa

## Configuração opcional

`brainiac.toml` na raiz do brainiac (todos os campos opcionais; defaults seguros):

```toml
# Working memory
working_memory_limit = 9              # default; reduz para forçar disciplina
classifier_threshold = 0.3            # confiança mínima do classifier

# ACT-R activation (Phase 5)
actr_decay = 0.5
actr_recall_hit_weight = 0.3
actr_link_in_weight = 0.5

# Spreading activation (Phase 6)
spreading_max_hops = 3
spreading_decay = 0.5
spreading_epsilon = 0.01
spreading_floor = 0.05

# Probabilistic consolidation (Phase 7)
consolidation_learning_rate = 0.5     # α na fórmula P = 1 - exp(-α·R·E·n)
consolidation_probability_threshold = 0.6

# Sensory buffer TTL (Phase 8)
sensory_ttl_minutes = 5
```

## Exemplos de uso

### Captura com peso emocional

```python
# via MCP tool (do Claude Code)
add_note(
    note_id="2026-05-20-bm25-ranking",
    note_type="semantic",
    title="BM25",
    body="# BM25\n\n- função de ranking probabilística\n- usa idf, tf, doc length",
    tags=["ir", "ranking"],
    emotional_weight=0.8,   # 0.0 baixo → 1.0 crítico (default 0.5)
)
```

### Fluxo sensory → real

```python
# 1. captura crua (TTL 5min)
s = capture_sensory(body="ideia: usar HNSW para nearest neighbor", title="HNSW")
# → {"id": "sensory-20260520-120000-abcd1234", ...}

# 2. lista ativos
list_sensory()  # exclui expirados

# 3. promove para nota real (deleta do buffer)
commit_sensory(
    sensory_id=s["id"],
    note_type="working",
    final_id="2026-05-20-hnsw-idea",
)
```

### Inspecionar estado + transições

```bash
.venv/bin/brainiac state 2026-05-20-bm25-ranking
# id: 2026-05-20-bm25-ranking
# current_state: working
#
# Transition probabilities:
#   → long_term: 0.714  (P_cons = 1 - exp(-α·R·E·n))
```

### Transição manual

```python
transition_note(note_id="2026-05-20-bm25-ranking", target_state="long_term")
# {"id": "2026-05-20-bm25-ranking", "new_state": "long_term"}

# Markov enforced:
transition_note(note_id="2026-05-20-foo", target_state="archived")
# do estado 'working' → ValueError: invalid transition: working → archived
```

## Roadmap — 8 fases entregues

| Fase | Entrega |
|------|---------|
| 0 — Foundation | MCP server + SQLite + capture/recall via FTS5 |
| 1 — Recall associativo | Embeddings 384-dim + grafo 1-hop |
| 2 — Consolidação + Decay | Ebbinghaus + promoção working → long (booleana) |
| 3 — SM-2 Spaced Repetition | Revisão ativa com grade 0-5 |
| 4 — Working memory + tipos | Limite hard + classificador heurístico |
| 5 — ACT-R Activation | `accesses` table, log-decay, recall_hit/link_in events |
| 6 — Spreading Activation | N-hop traversal, decay por hop, floor + epsilon |
| 7 — Consolidação Probabilística | `emotional_weight` + `novelty` + 3º caminho de promoção |
| 8 — Atkinson-Shiffrin States | `sensory_buffer` + 4 estados + Markov enforcement + transition probabilities |

Algoritmos referência:
- **Ebbinghaus forgetting curve** — `R = e^(-t/S)`, com `S` aumentando a cada acesso
- **ACT-R activation** — `A(t) = ln Σᵢ tᵢ^(-d)` sobre histórico de acessos (Anderson 1996)
- **Spreading activation** — propagação por arestas no grafo com decay multiplicativo (Collins & Loftus 1975)
- **SuperMemo-2** — algoritmo de Piotr Wozniak para revisão espaçada
- **Atkinson-Shiffrin model** — multi-store model com 4 estados de memória

## Desenvolvimento

```bash
cd tools/brainiac
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Suite completa (exclui test_embeddings.py que carrega modelo — slow)
.venv/bin/pytest --ignore=tests/core/test_embeddings.py

# Cobertura
.venv/bin/pytest --cov=brainiac --cov-report=term-missing --ignore=tests/core/test_embeddings.py

# Sub-suite específica
.venv/bin/pytest tests/core/test_states.py -v --no-cov
```

**State atual:** 340 testes verdes. Cobertura ≥ 95% nos módulos novos (`novelty`, `sensory`, `states`).

## Licença

[MIT](LICENSE) © Ueslei Nascimento
