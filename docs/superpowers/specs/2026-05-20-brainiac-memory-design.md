# Brainiac — Sistema de Memória Cognitiva

**Data**: 2026-05-20
**Status**: Design aprovado
**Idioma**: pt-BR (conteúdo e código de usuário); identificadores e símbolos em inglês

---

## 1. Visão geral

Brainiac é um "segundo cérebro" pessoal em arquivos Markdown que **replica mecânicas centrais da memória humana**: consolidação short→long, curva de esquecimento (Ebbinghaus), recall associativo via embeddings + grafo, revisão espaçada (SM-2), distinção episódico/semântico, e limite de working memory.

### 1.1 Objetivos

- Servir como assistente pessoal de conhecimento: o usuário registra ideias/aprendizados; o Claude, em sessões futuras, recupera contextualmente via MCP.
- Replicar quatro mecânicas cognitivas com algoritmos canônicos: Ebbinghaus, SM-2, embeddings + grafo de coativação, working memory com capacidade limitada.
- Funcionar 100% offline: sentence-transformers local, SQLite + sqlite-vec, sem chave de API.
- Manter `.md` como fonte de verdade; índice é cache reconstruível.

### 1.2 Não-objetivos

- Não há captura silenciosa de conversas — toda escrita é iniciada pelo usuário.
- Não há ingestão de fontes externas (PDFs, web) na primeira versão.
- Não há sincronização multi-dispositivo nem colaboração.
- Não há UI gráfica; interação é via Claude (MCP) ou CLI direto.

### 1.3 Stakeholder

Usuário único (Ueslei Nascimento). Projeto pessoal, sem SLA ou compromissos externos.

---

## 2. Arquitetura

### 2.1 Estrutura de pastas

```
brainiac/
├── shortMemory/                  # Working memory (limite default 9 itens)
├── longMemory/
│   └── episodic/                 # "Aconteceu comigo" — com timestamp + contexto
├── semanticMemory/               # Fatos/conceitos descontextualizados
├── memoryTransfer/               # Internals do sistema
│   ├── index.sqlite              # Cache: metadata + FTS5 + vetores + grafo
│   ├── archive/<ano>/            # Notas decaídas (não deletadas)
│   └── logs/events.jsonl         # Trilha de auditoria
├── tools/brainiac/               # Package Python
│   ├── pyproject.toml
│   ├── brainiac/
│   │   ├── cli.py
│   │   ├── mcp_server.py
│   │   └── core/
│   │       ├── note.py           # parse/write frontmatter
│   │       ├── index.py          # SQLite + FTS5 + sqlite-vec
│   │       ├── embeddings.py     # sentence-transformers wrapper
│   │       ├── graph.py          # links explícitos + implícitos
│   │       ├── decay.py          # Ebbinghaus
│   │       ├── consolidate.py    # promoção short→long
│   │       └── sm2.py            # SuperMemo-2
│   └── tests/
├── .claude/
│   └── skills/
│       ├── brainiac-capture/     # criar nota bem-formada
│       ├── brainiac-recall/      # buscar + sintetizar
│       ├── brainiac-review/      # sessão SM-2
│       └── brainiac-housekeep/   # decay + consolidate
└── docs/superpowers/
    ├── specs/                    # este documento
    └── plans/                    # implementation plans por fase
```

### 2.2 Camadas

```
Skills (.claude/skills/brainiac-*)        — UX, orquestram workflows
    ↓ chamam via MCP
MCP Server (mcp_server.py)                — fronteira pública
    ↓ usa
Core (core/*.py)                          — algoritmos puros, testáveis
    ↓ persiste
.md (verdade) + index.sqlite (cache)      — storage
```

**Princípio invariante**: o filesystem `.md` é a fonte de verdade. `brainiac reindex` reconstrói `index.sqlite` integralmente a partir dos `.md`. Edição direta dos `.md` no editor é primeira-classe.

### 2.3 Decisões arquiteturais explícitas

- **`sqlite-vec` em vez de Chroma/Qdrant**: zero infra, single-file, mesma DB do FTS5. Para uso pessoal vence ambos em simplicidade.
- **MCP como integração principal**: tools nativas no Claude Code, sem precisar ensinar comandos Bash.
- **`memoryTransfer/` é sistema, não conteúdo**: abriga índice, archive e logs. Notas "esquecidas" vão pro archive em vez de serem deletadas — fiel ao cérebro humano que raramente apaga, só torna inacessível.
- **`semanticMemory/` mantém nome do README**: cobre o componente semântico (fatos sobre o mundo + generalizações pessoais sintetizadas). Não há `longMemory/semantic/` para evitar duplicação conceitual.
- **`type` no frontmatter, não na pasta**: pasta é consequência do tipo. Promoção de nota é `mv` + atualização do campo, sem perda de identidade.

---

## 3. Formato da nota

Cada nota é um Markdown com frontmatter YAML carregando toda a metadata cognitiva.

```markdown
---
id: 2026-05-20-conceito-x
type: semantic              # episodic | semantic | working
created: 2026-05-20T10:30:00Z
last_access: 2026-05-20T10:30:00Z
access_count: 1
strength: 1.0               # Ebbinghaus (0..1); decai com tempo, sobe com acesso
links: []                   # links explícitos: [outro-id, ...]
tags: [tag1, tag2]
sm2:                        # opcional; presente se inscrita em revisão espaçada
  ease: 2.5
  interval: 1
  next_review: 2026-05-21
source: manual              # manual | conversation | import
---

# Título curto e descritivo

- bullets densos
- fatos tokenizados (sem prosa redundante)
- referências cruzadas via [[outro-id]]
```

### 3.1 Schema (Pydantic)

```python
class SM2(BaseModel):
    ease: float = 2.5
    interval: int = 1
    next_review: date

class NoteFrontmatter(BaseModel):
    id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
    type: Literal["episodic", "semantic", "working"]
    created: datetime
    last_access: datetime
    access_count: int = Field(ge=0)
    strength: float = Field(ge=0.0, le=1.0)
    links: list[str] = []
    tags: list[str] = []
    sm2: SM2 | None = None
    source: Literal["manual", "conversation", "import"] = "manual"
```

### 3.2 Convenções de corpo

- Bullets densos > prosa. Tokens economizados ajudam recall semântico e contexto futuro.
- Cross-refs com `[[id]]` — parser converte em links explícitos no índice.
- Sem comentários redundantes. Identificadores autoexplicativos.

### 3.3 Relação `links` do frontmatter ↔ tabela `links`

- O campo `links: []` no frontmatter é o registro **canônico** dos links explícitos de saída (`src → dst`) declarados pelo usuário.
- A tabela `links` no SQLite é **derivada**: durante `reindex`, ela é populada com (a) tudo do frontmatter como `kind='explicit'` e (b) referências `[[id]]` parseadas do corpo, também como `kind='explicit'`.
- Links `kind='implicit'` são calculados em runtime na Fase 1 (não persistidos no frontmatter — evita ruído nos `.md`).
- Edição manual do frontmatter é a forma autoritativa de adicionar/remover link explícito; `mcp.link()` apenas conveniência que edita o frontmatter e reindexa.

---

## 4. Stack técnica

### 4.1 Dependências

```toml
[project]
name = "brainiac"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0",
    "pydantic>=2",
    "python-frontmatter>=1.1",
    "sentence-transformers>=2.7",
    "sqlite-vec>=0.1",
    "click>=8",
]
[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "ruff", "mypy"]
```

Modelo de embeddings: **`paraphrase-multilingual-MiniLM-L12-v2`** (384 dim, ~120MB, suporta pt-BR adequadamente).

### 4.2 Schema SQLite (`memoryTransfer/index.sqlite`)

```sql
-- path armazenado relativo ao root do repo (ex: "semanticMemory/2026-05-20-foo.md")
-- garante portabilidade do índice
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('episodic','semantic','working')),
    created TEXT NOT NULL,
    last_access TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    strength REAL NOT NULL DEFAULT 1.0,
    tags TEXT,                    -- JSON
    sm2_json TEXT,                -- JSON nullable
    body_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE notes_fts USING fts5(
    id UNINDEXED, title, body,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE notes_vec USING vec0(
    id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);

CREATE TABLE links (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('explicit','implicit')),
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src, dst, kind)
);

CREATE INDEX idx_notes_type ON notes(type);
CREATE INDEX idx_notes_last_access ON notes(last_access);
CREATE INDEX idx_links_src ON links(src);
```

Eventos auditados em `memoryTransfer/logs/events.jsonl` (append-only): `{ts, note_id, action, detail}` onde `action ∈ {created, accessed, promoted, decayed, archived, reviewed, linked}`.

### 4.3 MCP tools (escopo completo, por fase)

| Tool | Fase | Descrição |
|---|---|---|
| `add_note` | 0 | Cria `.md` com frontmatter default; indexa |
| `recall` | 0→1 | Busca top-k (FTS5 na 0; vetorial+grafo na 1) |
| `get_note` | 0 | Lê nota; incrementa `access_count`/`last_access` |
| `link` | 0 | Adiciona link explícito A→B |
| `list_recent` | 0 | Últimas N notas |
| `consolidate_check` | 2 | Sugere candidatos short→long |
| `forget` | 2 | Arquiva nota |
| `review_queue` | 3 | Notas SM-2 vencidas hoje |
| `grade_review` | 3 | Atualiza SM-2 com nota 0-5 |
| `working_status` | 4 | Estado do limite de working memory |

### 4.4 CLI

```
brainiac reindex             # reconstrói index.sqlite dos .md
brainiac decay               # passo de decay
brainiac consolidate         # promove candidatos
brainiac classify <path>     # sugere tipo p/ nota legada
brainiac stats               # contadores
brainiac mcp                 # inicia servidor MCP (stdio)
```

---

## 5. Roadmap de 5 fases

### Fase 0 — Foundation (1-2 semanas)

**Objetivo**: salvar e buscar notas via Claude, com metadata cognitiva já em vigor (sem dinâmica temporal).

**Entregáveis**:
- `pyproject.toml`, estrutura `tools/brainiac/`, baseline de testes
- `core/note.py`: read/write `.md` com Pydantic validation
- `core/index.py`: SQLite com `notes` + `notes_fts`; `index_note`, `reindex_all`
- `mcp_server.py`: `add_note`, `recall` (FTS5), `get_note`, `link`, `list_recent`
- `cli.py`: `reindex`, `stats`, `mcp`
- Skill `brainiac-capture`: pergunta tipo, gera id (`YYYY-MM-DD-slug`), popula frontmatter
- Skill `brainiac-recall`: busca + leitura

**Algoritmos**: nenhum cognitivo — é infraestrutura. Rigor está no schema Pydantic e na função `reindex_all` ser idempotente.

**Critério de pronto (DoD)**:
- [ ] `brainiac mcp` inicia; Claude Code conecta via configuração MCP local
- [ ] `/brainiac-capture` salva nota; arquivo aparece na pasta correta com frontmatter válido
- [ ] `/brainiac-recall "termo"` recupera a nota
- [ ] `brainiac reindex` reconstrói índice corretamente após edição manual de `.md`
- [ ] Cobertura de testes ≥ 80% em `note.py` e `index.py`

---

### Fase 1 — Recall associativo (1-2 semanas)

**Objetivo**: busca para de depender de palavras exatas; entender conceitos; trazer vizinhos no grafo.

**Entregáveis**:
- `core/embeddings.py`: wrapper sentence-transformers; carga lazy; cache em memória
- `notes_vec` populada via `sqlite-vec`; embedding regenerado se `body_hash` mudou
- `core/graph.py`:
  - Links explícitos: declarados via `link()` ou parseados de `[[id]]` no corpo
  - Links implícitos: pares com cosine similarity ≥ `0.75` (configurável), calculados em runtime durante `recall`
- `recall()` reescrita:
  1. top-k=5 por cosine similarity
  2. expansão 1-hop no grafo (explícito + implícito) com peso decaído (vizinho = 0.5 × score original)
  3. dedup + ordenação por score combinado
- Skill `brainiac-recall` atualizada: badge indicando *por que* cada nota apareceu (semantic / explicit / implicit / both)
- FTS5 mantido como fallback se modelo falhar ao carregar

**Algoritmos**:
- **Cosine similarity** em vetores 384-dim
- **BFS 1-hop** com decay de peso

**DoD**:
- [ ] Busca por "criação distribuída de chaves" recupera nota titulada "DKG protocol" sem overlap lexical
- [ ] Resultado mostra badges de origem
- [ ] Geração de embedding < 200ms por nota em CPU
- [ ] `recall` retorna em < 500ms para corpus de até 1000 notas

---

### Fase 2 — Consolidação + Decay (1 semana)

**Objetivo**: notas que importam sobem; notas que não importam saem do caminho (sem serem deletadas).

**Entregáveis**:
- `core/decay.py`:
  - `S = S0 × (1 + α × access_count)` (stability cresce com acessos; `S0=24h`, `α=0.5` defaults)
  - `R(Δt) = exp(-Δt_horas / S)` (probabilidade de retenção)
  - Update: `strength_new = R(Δt_desde_last_access)`
  - Threshold: `strength < 0.2` → mover para `memoryTransfer/archive/<ano>/`; remover do índice ativo
- `core/consolidate.py`:
  - Critério: `type='working'` E `access_count ≥ 3` em janela de 7 dias E pelo menos 1 link recebido → candidata
  - Promoção: move arquivo de `shortMemory/` para `semanticMemory/` ou `longMemory/episodic/` (pergunta ao usuário se ambíguo)
  - Reset: `strength = 1.0`, `type` atualizado, evento `promoted` registrado
- MCP tools: `consolidate_check`, `forget`
- Skill `brainiac-housekeep`: executa decay+consolidate semanalmente; mostra relatório

**Algoritmos**:
- **Ebbinghaus refinado** (parâmetros tunáveis via config)
- **Critério de promoção**: combinação linear de access_count, idade, fan-in de links

**DoD**:
- [ ] Nota acessada 3x em uma semana com pelo menos 1 link recebido aparece em `consolidate_check`
- [ ] Nota não acessada por 30 dias com `access_count=1` é arquivada na próxima execução de `decay`
- [ ] Notas arquivadas não aparecem em `recall` por default; flag `--include-archived` permite incluir
- [ ] Relatório de `brainiac-housekeep` é legível e acionável

---

### Fase 3 — SM-2 Spaced Repetition (1 semana)

**Objetivo**: notas marcadas para estudo entram em ciclo de revisão ativa com intervalos crescentes.

**Entregáveis**:
- `core/sm2.py`: algoritmo SuperMemo-2 puro (input: estado atual + grade 0-5; output: novo estado)
- Capture com `study: true` adiciona bloco `sm2` inicial ao frontmatter
- MCP tools: `review_queue`, `grade_review(id, grade)`
- Skill `brainiac-review`: sessão interativa; Claude apresenta nota; usuário responde mentalmente; dá grade; sistema atualiza

**Algoritmo** (SM-2 canônico):
```
ease' = max(1.3, ease + 0.1 - (5 - q) × (0.08 + (5 - q) × 0.02))
if q < 3: interval' = 1
elif primeira revisão: interval' = 1
elif segunda revisão: interval' = 6
else: interval' = round(interval × ease')
next_review = today + interval' dias
```

**DoD**:
- [ ] Posso marcar nota como "estudar" via capture ou MCP
- [ ] `/brainiac-review` apresenta fila ordenada por urgência
- [ ] Grade 0-2 reagenda para amanhã; grade 5 expande corretamente o intervalo
- [ ] Acessos durante review também atualizam `access_count`/`strength` (consolidação se alimenta da repetição)

---

### Fase 4 — Working memory + tipos estritos (1 semana)

**Objetivo**: disciplina cognitiva forçada — sistema recusa violar limites do modelo.

**Entregáveis**:
- Limite configurável de `shortMemory/` (default 9 itens ativos; configurável em `brainiac.toml`)
- `add_note(type='working')` quando cheia → erro estruturado: `{error, suggestion: [candidatos a promover/descartar]}`
- MCP tool `working_status`: ocupação + candidatos óbvios
- Skill `brainiac-capture` valida tipo:
  - Features léxicas (verbos no passado + 1ª pessoa → `episodic`; definições abstratas → `semantic`)
  - Score de similaridade com clusters de exemplos rotulados
  - Em ambiguidade, pergunta ao usuário
- Script `brainiac classify <path>`: sugere tipo para notas pré-existentes/legadas

**Algoritmos**:
- **Classificador heurístico** (regras + embeddings)

**DoD**:
- [ ] `shortMemory/` nunca excede limite; tentativa retorna erro útil
- [ ] Capture pergunta tipo apenas quando ambíguo
- [ ] `brainiac classify` acerta ≥ 85% em sample manual de 20 notas

---

### 5.1 Cronograma sumarizado

| Fase | Foco | Esforço estimado | Valor entregue |
|---|---|---|---|
| 0 | Foundation | 1-2 sem | Salvar + buscar |
| 1 | Recall associativo | 1-2 sem | Buscar por conceito |
| 2 | Consolidação + Decay | 1 sem | Auto-organização temporal |
| 3 | SM-2 | 1 sem | Retenção ativa |
| 4 | Working memory + tipos | 1 sem | Disciplina cognitiva |
| **Total** | | **~5-7 semanas** | Sistema completo |

Cada fase termina com sistema funcionante. Parar em qualquer ponto deixa algo útil — o "abandono parcial" não quebra o que foi entregue.

---

## 6. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Modelo de embeddings pesa demais no setup (~120MB + cold start) | Média | Médio | Lazy load no primeiro `recall`; FTS5 como fallback se carga falhar |
| Índice SQLite e `.md` saem de sincronia (edição manual + bug) | Média | Médio | `brainiac reindex` idempotente; `body_hash` detecta drift; comando `brainiac doctor` (futuro) reporta inconsistências |
| Curva de Ebbinghaus arquiva notas importantes precocemente | Média | Alto | Threshold conservador (0.2); archive não é delete; `link` recebido protege; usuário ajusta `α` via config |
| MCP server não conecta no Claude Code (config errada) | Alta inicialmente | Baixo | README com config exemplo; `brainiac mcp --test` valida handshake |
| sqlite-vec não disponível no SO/arch local | Baixa | Médio | Pin de versão testada; fallback: armazenar embedding como BLOB e fazer cosine em Python (lento, mas funcional para <10k notas) |
| SM-2 ease factor cai abaixo do mínimo e nota nunca mais "estabiliza" | Baixa | Baixo | Floor de 1.3 já no algoritmo; tool `reset_sm2(id)` para casos extremos |
| Classificador episódico/semântico erra muito (Fase 4) | Média | Baixo | Pergunta ao usuário em ambiguidade; threshold de confiança configurável |

---

## 7. Estratégia de testes

- **Framework**: pytest + pytest-cov; alvo ≥ 80% por módulo do core
- **Tipos**:
  - Unit: `note`, `sm2`, `decay`, `graph` (puros, sem I/O)
  - Integration: `index` + MCP tools (com SQLite tmp + fixtures de `.md`)
  - Property-based (hypothesis, opcional): invariantes do SM-2 (ease ≥ 1.3, intervalo monotônico em grades altas)
- **Fixtures**: `tmp_brain/` com 10-20 notas exemplares (mix de tipos), `conftest.py` provê factory `make_note(...)` e `fresh_index()`
- **Smoke E2E por fase**: ao final de cada fase, um teste percorre o fluxo principal end-to-end (criar → indexar → recall → assert resultados)
- **Sem mocks de embeddings**: usa modelo real em testes de integração (custo aceitável: cold start ~3s uma vez por sessão de testes)

---

## 8. Out of scope (esta versão)

- Captura silenciosa de conversas
- Ingestão de PDFs/web/transcrições
- UI gráfica (web/desktop)
- Sincronização multi-dispositivo
- Múltiplos usuários
- Memória procedural (skills/habits) e autobiográfica (life timeline)
- Modelagem de emoção/saliência (amígdala-like weighting)
- Pattern separation/completion (hippocampus-like)

Esses itens podem virar fases futuras (5+) depois das 5 fases atuais entregues e validadas em uso real.

---

## 9. Próximos passos

1. Revisão deste spec pelo usuário
2. Geração de implementation plan **da Fase 0** via skill `superpowers:writing-plans`
3. Execução da Fase 0 com checkpoints de revisão
4. Repetir 2-3 para cada fase subsequente
