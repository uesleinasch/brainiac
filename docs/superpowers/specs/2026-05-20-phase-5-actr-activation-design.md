# Fase 5 — ACT-R Activation (eixo cognitivo paralelo)

> **Status:** spec aprovada via brainstorming em 2026-05-20.
> **Próximo passo:** plano de implementação via `superpowers:writing-plans`.

## 1. Objetivo

Introduzir um **terceiro eixo de medição cognitiva por nota: `activation A(t)`**, baseado no modelo ACT-R (Anderson, 1996), em paralelo aos eixos `retention` (Ebbinghaus, Phase 2) e `sm2` (SuperMemo-2, Phase 3). O brainiac passa a tratar cada nota como um **traço de memória com múltiplas propriedades observáveis simultaneamente**, em vez de uma força única.

## 2. Contexto e motivação

### 2.1 Limites do modelo atual

Phases 0-4 entregaram um sistema cognitivamente sólido mas com uma simplificação importante: a "força" de uma nota é representada por dois números desconexos — `access_count` (contador linear) e `strength` (retention Ebbinghaus). Ambos colapsam toda a história de uso da nota em escalares minimalistas.

Isso significa que o sistema **não distingue**:
- Nota acessada 5x em 1 dia vs. 5x ao longo de 5 dias espaçados (mesmo `access_count`)
- Nota fortemente ativada por priming (citação cruzada, hit em busca) vs. nota dormente
- Nota que está "fading away" mas ainda detectável vs. nota arquivada

A literatura de ciência cognitiva mapeia esses casos para sinais distintos. ACT-R em particular fornece uma fórmula que captura **frequência × recência com spacing effect** numa única expressão analítica.

### 2.2 Princípio de design: múltiplos eixos > escalar único

Cada eixo responde uma pergunta diferente sobre a nota:

| Eixo | Pergunta | Onde é usado |
|------|----------|--------------|
| `retention` (Ebbinghaus) | "Vou esquecer logo?" | Gate de archive |
| `activation` (ACT-R) — **NOVO** | "Esse traço está sendo usado?" | Ranking de recall, gating de consolidação, introspecção |
| `sm2` | "Quando devo revisar ativamente?" | Fila de revisão |

Os 3 eixos nunca se sobrescrevem. Cada um é independente, calculável, auditável.

### 2.3 Por que ACT-R (e não outra formulação)

A fórmula canônica do ACT-R Declarative Memory:

```
A(t) = ln( Σᵢ wᵢ · (t − tᵢ)⁻ᵈ )
```

Onde `tᵢ` são os timestamps de cada acesso, `wᵢ` são pesos por tipo de acesso, e `d ≈ 0.5` é o decaimento. Propriedades chave:

- **Spacing effect natural**: dois acessos espaçados contribuem mais ao logaritmo que dois acessos juntos, sem regra especial.
- **Frequência saturada**: o `ln` modera o ganho — a 50ª revisão vale menos que a 5ª (ajusta automaticamente o retorno decrescente).
- **Pesos por canal**: revisão deliberada (peso 1.0) ≠ priming por busca (peso 0.3) — modelagem natural da intensidade de cada tipo de ativação.
- **Decomposição em audit trail**: cada term `(t−tᵢ)⁻ᵈ` é inspecionável — sabemos exatamente qual acesso passado está sustentando a ativação atual.

Alternativas consideradas e rejeitadas: power-law puro (`A = N⁻ᵏ`) não captura recência; exponential moving average não tem spacing effect; modelos baseados em LLM são pesados demais e quebram o princípio "tudo local, sem GPU".

## 3. Algoritmo

### 3.1 Fórmula

```
A(t) = ln( Σᵢ wᵢ · (Δtᵢ)⁻ᵈ )

onde:
  Δtᵢ = (t − tᵢ) em horas (mesma unidade do Ebbinghaus para coerência)
  d   = 0.5 (padrão ACT-R, configurável)
  wᵢ  = weight do evento i, dependendo da source
```

**Domínio:** `Δt > 0`. Eventos com `Δt = 0` (mesmo segundo) recebem epsilon (`max(Δt, 1e-3)`) para evitar divisão por zero. Realisticamente, dois events em mesmo segundo são raros e não atrapalham a semântica.

**Range:** `A(t) ∈ (−∞, +∞)`. Valores típicos esperados:
- Nota sem acessos: `−∞` (convenção: sinaliza "no trace yet")
- Nota acessada 1x há 1h: `A = ln(1.0 · 1⁻⁰·⁵) = ln(1) = 0`
- Nota acessada 5x espaçada nos últimos 7 dias: `A ≈ 1.5–2.5`
- Nota acessada 50x ao longo de meses: `A ≈ 3–5`

Não vamos normalizar para `[0, 1]` — perde-se nuance. Quando o recall ranking combinar com semantic score, normalização é por z-score local na query, não global.

### 3.2 Pesos por tipo de evento

| Source | Weight | Justificativa |
|--------|--------|---------------|
| `get` | 1.0 | Leitura deliberada da nota — sinal cognitivo mais forte |
| `review` | 1.0 | Revisão SM-2 — reforço ativo equivalente a leitura |
| `link_in` | 0.5 | Nota foi citada por outra (`[[id]]`) — co-ativação por contexto |
| `recall_hit` | 0.3 | Apareceu em resposta de busca — priming, sem garantia de leitura |

Pesos são defaults; configuráveis via `brainiac.toml` para experimentação.

### 3.3 Constante de decay `d`

Default: `d = 0.5` (literatura ACT-R). Configurável via `brainiac.toml`. Valores menores (e.g., 0.3) tornam a ativação mais "persistente" — memórias antigas continuam contribuindo. Valores maiores (e.g., 0.7) tornam o sistema mais "presentista" — só recência importa.

## 4. Arquitetura

### 4.1 Mapa de arquivos novos

```
tools/brainiac/
├── brainiac/
│   └── core/
│       └── activation.py          # NOVO — pure (actr_activation) + I/O
├── tests/core/
│   └── test_activation.py         # NOVO
```

### 4.2 Modificações em arquivos existentes

```
brainiac/core/
├── config.py        # +3 fields (actr_decay, actr_recall_hit_weight, actr_link_in_weight)
├── index.py         # connect() ganha migration; get_note + recall + add_link registram access
├── decay.py         # archive event log agora inclui activation no detail
├── consolidate.py   # consolidation_candidates ganha condição opcional via activation
└── sm2.py           # grade_review registra access source='review'
brainiac/
├── mcp_server.py    # nova tool: inspect_note
└── cli.py           # novo comando: brainiac inspect <note_id>
.claude/skills/
└── brainiac-recall/SKILL.md  # MODIFY: pode mostrar badge ativação alta
```

### 4.3 Schema SQLite

Migração idempotente em `connect()` (mesmo padrão da Phase 2 que adicionou `archived`):

```sql
CREATE TABLE IF NOT EXISTS accesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('get', 'review', 'recall_hit', 'link_in')),
    weight REAL NOT NULL DEFAULT 1.0,
    FOREIGN KEY (note_id) REFERENCES notes(id)
);
CREATE INDEX IF NOT EXISTS idx_accesses_note_ts ON accesses(note_id, ts);
```

**Decisões de schema:**

- **`id INTEGER PRIMARY KEY AUTOINCREMENT`** — não usa UUID; sequência simples suficiente para append-only.
- **`ts` como TEXT ISO-8601 UTC** — consistente com como `created`/`last_access` já são armazenados na tabela `notes`.
- **CHECK constraint em `source`** — rejeita sources não-mapeadas no nível do banco. Adicionar nova source (e.g., `import` em uma fase futura) requer migration explícita.
- **`weight REAL DEFAULT 1.0`** — embora os defaults venham de Config, persistir o weight efetivo facilita auditoria histórica caso a Config mude.
- **`FOREIGN KEY` sem CASCADE** — quando uma nota é arquivada (mas não deletada do FS/DB), seus accesses ficam intactos. Se um dia uma nota for fisicamente removida da tabela `notes`, os accesses ficam órfãos — aceitável pois a tabela `notes` não tem DELETE no caminho normal do sistema.
- **Index em `(note_id, ts)`** — todas as queries de leitura filtram por `note_id`. Index composto otimiza tanto `WHERE note_id = ?` quanto `WHERE note_id = ? ORDER BY ts DESC`.
- **Sem coluna `archived` em `accesses`** — derive via JOIN com `notes` quando preciso. Manter accesses "tipo-puro" (apenas registro de evento), separando da política de arquivamento.

### 4.4 Schema Config

`brainiac/core/config.py` ganha 3 fields:

```python
@dataclass(frozen=True)
class Config:
    working_memory_limit: int = 9
    classifier_threshold: float = 0.3
    # ACT-R activation (Phase 5)
    actr_decay: float = 0.5
    actr_recall_hit_weight: float = 0.3
    actr_link_in_weight: float = 0.5
```

`brainiac.toml` (todos opcionais):

```toml
actr_decay = 0.5
actr_recall_hit_weight = 0.3
actr_link_in_weight = 0.5
```

Validação de tipos e rejeição de chaves desconhecidas continua via `load_config()` existente. Migrações de Config são pequenas e isoladas; não há quebra de retro-compat.

## 5. Módulo `core/activation.py`

### 5.1 API pública

```python
from datetime import datetime
import sqlite3
from brainiac.core.config import Config


# ---------- Pure ----------

def actr_activation(
    events: list[tuple[datetime, float]],
    now: datetime,
    d: float = 0.5,
) -> float:
    """A(t) = ln(Σ wᵢ · (Δtᵢ)⁻ᵈ).

    events: [(ts, weight), ...] in any order
    Returns:
        ln(soma) se houver events; float('-inf') se empty.
    Edge cases:
        Δt = 0 (event 'agora') é tratado como Δt = 1e-3 para evitar divisão por zero.
    """


# ---------- I/O ----------

def record_access(
    conn: sqlite3.Connection,
    note_id: str,
    source: str,
    *,
    now: datetime | None = None,
    weight: float | None = None,
    config: Config | None = None,
) -> None:
    """INSERT into accesses. weight default derivado de source via config."""


def activation(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> float:
    """A(t) atual para uma nota. Lê toda a história de accesses."""


def activation_batch(
    conn: sqlite3.Connection,
    note_ids: list[str],
    *,
    now: datetime | None = None,
    config: Config | None = None,
) -> dict[str, float]:
    """Single query batch — A(t) para muitas notas de uma vez.

    Notas sem accesses retornam float('-inf') no dict.
    """


def access_history(
    conn: sqlite3.Connection,
    note_id: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Últimos N events de uma nota, ordenados por ts DESC.

    Returns: [{ts, source, weight}, ...]
    """
```

### 5.2 Resolução de weight por source

```python
_SOURCE_DEFAULT_WEIGHTS = {
    "get": 1.0,
    "review": 1.0,
    "recall_hit": None,   # → config.actr_recall_hit_weight
    "link_in": None,      # → config.actr_link_in_weight
}

def _resolve_weight(source: str, config: Config, explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    default = _SOURCE_DEFAULT_WEIGHTS.get(source)
    if default is not None:
        return default
    if source == "recall_hit":
        return config.actr_recall_hit_weight
    if source == "link_in":
        return config.actr_link_in_weight
    raise ValueError(f"Unknown access source: {source}")
```

### 5.3 SQL de `activation_batch`

```sql
SELECT note_id, ts, weight
FROM accesses
WHERE note_id IN (?, ?, ...)
ORDER BY note_id, ts
```

Python agrega por `note_id` em um único pass. Não usar `AVG`/`SUM` no SQL porque a fórmula tem termos `(now - ts)⁻ᵈ` que dependem de `now` — mais simples calcular em Python.

## 6. Integrações com módulos existentes

### 6.1 `core/index.py`

**`get_note(conn, root, note_id)`** — após bump existente de `access_count`:
```python
record_access(conn, note_id, "get")
```

**`recall(conn, query, k=5, include_archived=False)`** — modificações em ordem específica:

1. **Scoring semântico + grafo (existente)** — produz `scored` candidates.
2. **Reorder via activation, ANTES de registrar hits** (evita circularidade — a query atual usa o estado anterior; o novo hit afeta queries futuras):
   ```python
   ALPHA, BETA = 0.7, 0.3  # configuráveis em fase futura
   acts = activation_batch(conn, [h["id"] for h in scored])
   # z-score normalize activations across this query's candidates
   vals = [v for v in acts.values() if v != float('-inf')]
   mean = statistics.mean(vals) if vals else 0
   stdev = statistics.stdev(vals) if len(vals) > 1 else 1
   for h in scored:
       a = acts.get(h["id"], float('-inf'))
       a_norm = 0 if a == float('-inf') else (a - mean) / (stdev or 1)
       h["score"] = ALPHA * h["score"] + BETA * a_norm
   # ordenar por score final
   results = sorted(scored.values(), key=lambda r: r["score"], reverse=True)[:k]
   ```
3. **Registrar recall_hit para top-K final, APÓS reorder:**
   ```python
   for hit in results:
       record_access(conn, hit["id"], "recall_hit")
   ```
4. Retrocompat: notas sem accesses não são penalizadas (a_norm = 0 quando -inf, preservando score semântico puro).

**Importante:** somente os top-K finais (resultados retornados ao caller) recebem `recall_hit`. Os candidates intermediários expandidos por grafo mas que não chegaram ao top-K **não** são registrados — caso contrário, cada `recall` registraria dezenas de events e o sinal de "essa nota apareceu na busca" perderia significado.

**`add_link(conn, root, src, dst)`** — após inserir o link:
```python
record_access(conn, dst, "link_in")
```

### 6.2 `core/sm2.py::grade_review(...)`

Após `index_note(conn, fm, body, rel)` e antes de `log_event(...)`:
```python
record_access(conn, note_id, "review")
```

### 6.3 `core/decay.py::run_decay(...)`

Não muda gate de archive (`retention < 0.2` continua). Apenas enriquece o log de cada archive:

```python
# Dentro do loop, para cada nota arquivada
act = activation(conn, note_id)
log_event(root, note_id, "archived",
          f"retention={new_s:.2f} activation={act:.2f}")
```

Isso dá ao usuário visibilidade futura: "essa nota foi arquivada com retention baixo mas ainda tinha ativação alta — talvez archive policy precise refinamento na Phase 6+".

### 6.4 `core/consolidate.py::consolidation_candidates(...)`

Adiciona uma 4ª condição via OR:

```python
# Pseudocode da nova query
SELECT n.id, n.path, n.access_count, n.last_access, COUNT(l.src) as fan_in
FROM notes n
LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
WHERE n.type = 'working'
  AND n.archived = 0
  AND n.last_access >= ?
GROUP BY n.id
HAVING (n.access_count >= 3 AND fan_in >= 1)
    OR <activation_above_threshold>  -- nova condição
```

Como `activation` não é uma coluna, a query SQL fica em duas fases:
1. SELECT candidates por critério atual (Phase 2)
2. SELECT working notes com `fan_in >= 1` mas `access_count = 2` (borderline)
3. Para o conjunto borderline, `activation_batch` → filtra os que têm `A(t) > threshold` (e.g., > 1.5)
4. Union dos dois conjuntos

Threshold `1.5` é heurística inicial; expor via Config (`actr_consolidate_threshold`) numa fase futura se necessário.

### 6.5 MCP layer (`mcp_server.py`)

**Nova tool:** `tool_inspect_note(note_id: str) -> dict`:

```python
def tool_inspect_note(note_id: str) -> dict:
    """Snapshot completo dos 3 eixos cognitivos + audit trail de access."""
    from brainiac.core.activation import activation, access_history
    from brainiac.core.decay import updated_strength
    root = find_root()
    conn = connect(index_db_path(root))
    row = conn.execute(
        "SELECT type, access_count, strength, last_access, sm2_json, archived "
        "FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Note not found: {note_id}")
    return {
        "id": note_id,
        "type": row[0],
        "access_count": row[1],
        "strength": row[2],
        "last_access": row[3],
        "sm2": json.loads(row[4]) if row[4] else None,
        "archived": bool(row[5]),
        # NOVO — eixo ACT-R
        "activation": activation(conn, note_id),
        "recent_accesses": access_history(conn, note_id, limit=10),
    }
```

Registrar em `_list_tools()` (vira "Tools (12)") e `_DISPATCH`.

### 6.6 CLI

**Novo comando:** `brainiac inspect <note_id>`:

```
$ brainiac inspect 2026-05-20-bm25
id: 2026-05-20-bm25
type: semantic
archived: false

Eixos cognitivos:
  retention:  0.42 (Ebbinghaus, decaying)
  activation: 1.83 (ACT-R, healthy)
  sm2:        ease=2.6 interval=6 reps=2 next=2026-05-26

access_count: 7
last_access: 2026-05-19T14:32:00Z

Últimos 10 acessos:
  2026-05-19 14:32  get
  2026-05-18 09:10  review
  2026-05-17 16:20  recall_hit (w=0.3)
  ...
```

**`brainiac stats`** ganha duas linhas no final:
```
events recorded: 142
top 5 by activation:
  2026-05-15-bm25: 2.8
  2026-05-12-dkg: 2.1
  ...
```

### 6.7 Skill `brainiac-recall`

Atualização no SKILL.md: quando uma nota retornada pelo `recall` tem `activation > 1.5` (computável via `tool_inspect_note(id)`), apresentar com badge **🔥 ativação alta** para sinalizar ao usuário "essa nota tá em uso ativo, faz sentido revisitar". Não chamar `inspect_note` automaticamente em todos os results (custo) — apenas quando o usuário pede contexto.

## 7. Testes

### 7.1 `tests/core/test_activation.py`

**Pure function `actr_activation`** (~10 testes):
- `test_empty_events_returns_negative_infinity`
- `test_single_event_one_hour_ago_returns_zero` (ln(1) = 0)
- `test_single_event_more_recent_returns_positive`
- `test_two_events_spaced_higher_than_two_grouped` (**spacing effect**)
- `test_weight_scales_contribution` (peso 0.5 vs 1.0)
- `test_decay_constant_changes_persistence` (d=0.3 vs d=0.7)
- `test_event_at_now_uses_epsilon_no_division_error`
- `test_very_old_events_dont_underflow` (1 ano atrás)
- `test_many_events_sum_correctly` (50 events)
- `test_negative_delta_t_is_clamped_to_epsilon` (event "no futuro" via clock skew)

**I/O `record_access`** (~4 testes):
- `test_record_access_inserts_row_with_default_weight`
- `test_record_access_respects_explicit_weight`
- `test_record_access_uses_config_weight_for_recall_hit`
- `test_record_access_rejects_invalid_source` (CHECK constraint)

**I/O `activation`** (~5 testes):
- `test_activation_zero_events_returns_neg_infinity`
- `test_activation_reads_full_history`
- `test_activation_uses_config_decay`
- `test_activation_now_injectable_for_determinism`
- `test_activation_consistent_with_pure_function`

**I/O `activation_batch`** (~4 testes):
- `test_batch_single_query_for_many_notes`
- `test_batch_handles_notes_without_events`
- `test_batch_results_match_individual_calls`
- `test_batch_empty_input_returns_empty_dict`

**I/O `access_history`** (~3 testes):
- `test_access_history_ordered_by_ts_desc`
- `test_access_history_respects_limit`
- `test_access_history_returns_required_fields`

### 7.2 Integrações

**`tests/core/test_index.py`** (~5 novos):
- `test_get_note_records_access_source_get`
- `test_recall_records_access_source_recall_hit_for_each_hit`
- `test_recall_does_not_record_for_graph_expanded_neighbors` (apenas top-K diretos)
- `test_recall_ranking_includes_activation` (2 notas igualmente semânticas, a com mais accesses ranqueia primeiro)
- `test_add_link_records_access_source_link_in_on_destination`

**`tests/core/test_sm2.py`** (1 novo):
- `test_grade_review_records_access_source_review`

**`tests/core/test_consolidate.py`** (1 novo):
- `test_candidates_includes_borderline_note_with_high_activation`

**`tests/test_mcp_server.py`** (~3 novos):
- `test_tool_inspect_note_returns_all_three_axes`
- `test_tool_inspect_note_includes_recent_accesses`
- `test_tool_inspect_note_raises_for_unknown_note`

**`tests/test_cli.py`** (~2 novos):
- `test_inspect_command_outputs_three_axes`
- `test_stats_command_shows_top_activations`

### 7.3 Smoke E2E (DoD)

**`tests/test_smoke_e2e.py`** (3 novos):
- `test_spacing_effect_demonstrable`:
  - Nota A: 3 acessos hoje em intervalos de 1h
  - Nota B: 3 acessos espaçados (hoje, ontem, anteontem)
  - Assert: `activation(B) > activation(A)` mesmo com mesmo `access_count`

- `test_recall_ranks_by_combined_activation_and_semantic`:
  - 2 notas igualmente similares à query (semantic score equivalente)
  - Uma tem 5 accesses recentes, outra tem 0
  - Assert: a mais ativada vem primeiro no top-K

- `test_inspect_shows_audit_trail`:
  - Cria nota, faz 3 accesses de sources diferentes
  - `tool_inspect_note(id)["recent_accesses"]` retorna os 3 com source/weight corretos

### 7.4 Cobertura alvo

| Módulo | Alvo |
|--------|------|
| `core/activation.py` | ≥ 95% (módulo novo e pequeno) |
| `core/config.py` | ≥ 95% (só adicionou fields) |
| `core/index.py` | manter ≥ 90% (já está em 95%) |
| `core/sm2.py` | manter ≥ 95% |
| `core/consolidate.py` | manter ≥ 95% |

## 8. Definition of Done

Phase 5 está pronta quando:

- [ ] **Spacing effect demonstrável**: teste smoke valida que A(t) é maior para acessos espaçados que para acessos agrupados (mesmo `access_count`)
- [ ] **Recall ranking responde a activation**: notas mais ativadas sobem no top-K mesmo com semantic score igual
- [ ] **Auditoria por nota**: `brainiac inspect <id>` mostra os 3 eixos + últimos 10 events com source/weight
- [ ] **4 sources gravadas**: `get` (de `get_note`), `review` (de `grade_review`), `recall_hit` (de `recall` top-K final), `link_in` (de `add_link`) — confirmado via `accesses` table
- [ ] **Config opcional**: novos campos em `brainiac.toml` são opcionais; sem o arquivo, defaults aplicam
- [ ] **Schema migration idempotente**: rodar `connect()` em DB já populado funciona sem erro
- [ ] **Cobertura `activation.py` ≥ 95%**
- [ ] **Suite completa verde** (atualmente 204; espera-se ~225 após Phase 5)
- [ ] **Sem regressões** nos testes existentes das Phases 0-4

## 9. Out of scope (explícito)

Para evitar scope creep, **não** entram nesta fase:

- **Pruning de events antigos** (limpar `accesses` com `ts < cutoff`) — adiciona política de garbage collection sem ganho claro a curto prazo. Decisão para Phase 6+ se a tabela crescer demais.
- **Normalização global de activation** (calibrar A(t) para [0,1]) — perde nuance. Z-score local por query é suficiente para recall ranking.
- **Spreading activation iterativa** (aⱼ(t+1) = Σ wᵢⱼ·aᵢ(t)·e^(−d·dist)) — fica para Phase 6. Esta fase entrega o fundamento (activation por nota); propagação multi-hop é um sistema separado que consome esse fundamento.
- **Consolidação probabilística completa** (P = 1 − e^(−α·R·E·n) com peso emocional E e novidade n) — fica para Phase 7. Esta fase apenas adiciona activation como gatilho extra de consolidação, sem mudar a probabilidade boolean para contínua.
- **Atkinson-Shiffrin estados** (cadeia Markov entre MCP/MLP/MTC com probabilidades de transição) — fica para Phase 8.
- **Decay temporal de shortMemory segundo-a-segundo** (modelar t½≈10s do HTML reference) — fora de escopo cognitivo realista para o uso do brainiac. Acessos a notas working já são raros o suficiente que decay em segundos não fornece sinal útil.
- **Migração de notas legadas com história sintética** — não há notas reais ainda no brainiac. Quando existirem, a primeira leitura registra um `get`, e a partir daí o sistema acumula naturalmente.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Tabela `accesses` cresce demais (≥1M rows) | Baixa em uso pessoal; Alta se brainiac for usado por anos sem pruning | Médio (SQLite degrada) | Index em `(note_id, ts)` mitiga query cost. Pruning fica para Phase 6 se necessário. |
| Z-score normalization quebra com k=1 (stdev=0) | Média | Baixo | Fallback `stdev or 1` no código. Coberto por teste. |
| Pesos defaults ruins (recall_hit muito alto inflaciona activation) | Média inicialmente | Baixo | Exposto em Config. Calibração via dogfooding pode ajustar. |
| `recall` registra recall_hit em loop circular (recall → log → recall) | Baixa | Baixo | Recall registra apenas top-K final, não os candidates intermediários expandidos por grafo. |
| Activation pure function tem instabilidade numérica para events muito antigos (subflow) | Baixa | Baixo | `(Δtᵢ)⁻⁰·⁵` para Δt=1 ano = ~3e-2 — bem dentro do range double. Teste explícito cobre este caso. |
| Quebra de retro-compat com notas sem accesses | Alta inicialmente | Baixo | `activation = -inf` é tratado em recall como "sem contribuição" (a_norm = 0). Nenhum comportamento existente quebra; apenas perde ranking boost. |
| Schema migration falha em DB já populado | Baixa | Médio | `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` — operações idempotentes nativas do SQLite. Coberto pelo padrão da Phase 2. |

## 11. Próximos passos pós-Phase 5

Esta fase é a base para 3 fases futuras possíveis:

- **Phase 6 — Spreading activation iterativa**: `recall` propaga ativação em N hops com decay por distância. Consome `activation` como ponto de partida.
- **Phase 7 — Consolidação probabilística**: introduz peso emocional `E` (saliência via embedding distance ao centroide do corpus) e novidade `n` (distância ao vizinho mais próximo). `P(consolidar) = 1 − e^(−α·R·E·n)`. Consome `activation` como `R`.
- **Phase 8 — Atkinson-Shiffrin states**: cadeia Markov explícita entre `sensory → working → long-term` com probabilidades de transição. Activation alta aumenta P(consolidar); retention baixa aumenta P(forget).

Cada fase futura é independente — a Phase 5 entrega valor autônomo (recall melhor, introspecção rica, audit trail), e pode ficar como entrega final caso as Phases 6-8 não sejam priorizadas.

---

**Spec aprovada para implementação.** Próximo: gerar plano detalhado via `superpowers:writing-plans`.
