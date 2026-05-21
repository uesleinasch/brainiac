# Fase 7 — Consolidação Probabilística

> **Status:** spec criada em 2026-05-20 como parte do batch Phases 6-8.
> **Next:** plano em `docs/superpowers/plans/2026-05-20-phase-7-probabilistic-consolidation.md`.

## 1. Objetivo

Adicionar um **critério probabilístico** de consolidação `P(consolidar) = 1 − e^(−α·R·E·n)` que coexiste com os critérios booleanos das Phases 2 (`access_count≥3 + fan_in≥1`) e 5 (`access_count=2 + activation≥1.5`). Captura o componente subjetivo da consolidação humana: **memórias emocionalmente marcantes** (E alto) e **memórias completamente novas** (n alto) se fixam mais facilmente, mesmo sem repetição farta.

## 2. Contexto

### 2.1 O que existe hoje

`consolidation_candidates(conn, now, window_days)` retorna notas working candidatas a promoção via:
- **Phase 2 (primary)**: `access_count ≥ 3` AND `fan_in ≥ 1` AND `last_access < window_days`
- **Phase 5 (borderline)**: `access_count = 2` AND `fan_in ≥ 1` AND `activation ≥ 1.5`

Ambos são **booleanos com thresholds fixos**. Decisão binária: passa ou não passa.

### 2.2 Limites do modelo atual

Cenário: usuário anota algo de altíssima importância emocional (decisão de vida, descoberta científica). Acessa apenas 1 vez para gravar. Sem links recebidos. **O sistema atual nunca promove**, mesmo que cognitivamente seja a memória mais importante de todas no brainiac.

Outro cenário: usuário anota algo completamente novo no corpus (zero overlap semântico com qualquer outra nota). Em humanos, novidade é forte sinal de consolidação (efeito von Restorff). Atualmente brainiac não diferencia "nota nova" de "nota redundante" para fins de promoção.

### 2.3 Princípio de design

Não substituir os critérios existentes — **adicionar um terceiro caminho** probabilístico. `P ≥ threshold` → candidato. Os 3 caminhos disjuntos formam um union que captura mais variedade de razões legítimas para promover.

A probabilidade é **calibrada explicitamente** via 4 parâmetros (R, E, n, α), permitindo ajuste fino sem trocar o modelo.

## 3. Algoritmo

### 3.1 Fórmula

```
P(consolidar) = 1 − e^(−α · R · E · n)

onde:
  R = access_count (uso direto, sem normalização — ACT-R activation NÃO substitui aqui)
  E = emotional_weight ∈ [0, 1] (frontmatter, default 0.5)
  n = novelty_score ∈ [0, 1] (1 - max(cosine_sim com top-3 vizinhos do corpus); default 0.5 se body não embedded)
  α = consolidation_learning_rate (Config, default 0.5)
```

**Range:** `P ∈ [0, 1)`. P = 0 só se algum de R, E, n é zero. P → 1 conforme produto cresce.

**Exemplos numéricos:**

| R | E | n | α | P |
|---|---|---|---|---|
| 1 | 0.5 | 0.5 | 0.5 | 1 - e^(-0.0625) ≈ 0.061 |
| 1 | 0.9 | 0.9 | 0.5 | 1 - e^(-0.405) ≈ 0.333 |
| 5 | 0.5 | 0.5 | 0.5 | 1 - e^(-0.625) ≈ 0.465 |
| 5 | 0.9 | 0.9 | 0.5 | 1 - e^(-2.025) ≈ 0.868 |
| 10 | 1.0 | 1.0 | 0.5 | 1 - e^(-5.0) ≈ 0.993 |

Com `consolidation_probability_threshold = 0.6` (default):
- 5 acessos + média (E=n=0.5) → 0.465 → não promove
- 5 acessos + alta saliência+novidade → 0.868 → promove
- 1 acesso + altíssima saliência+novidade → 0.333 → não promove (precisa de pelo menos uns 3 acessos mesmo em casos extremos)

### 3.2 Componentes

#### R (repetições) — `access_count`

Coluna existente em `notes`. Sem alteração.

**Decisão consciente:** uso `access_count` em vez de ACT-R activation (Phase 5). Por quê? Porque ACT-R já é gate da Phase 5 (`access_count=2 + activation≥1.5`). Aqui queremos um sinal independente, complementar.

#### E (saliência emocional) — `emotional_weight`

**Nova coluna** em `notes`: `emotional_weight REAL DEFAULT 0.5`.

**Origem do valor:**
- Campo opcional no frontmatter da nota: `emotional_weight: 0.9`
- Se ausente → default 0.5 (neutro)
- Validação Pydantic: `Field(ge=0.0, le=1.0)`

**Skill `brainiac-capture` atualizada:** pergunta opcional "essa nota é particularmente importante para você?" → se sim, pergunta um número de 0-1 ou usa preset (`baixo=0.3`, `médio=0.5`, `alto=0.8`, `crítico=1.0`).

**Por que explícito e não derivado?** Tentei pensar em heurística (e.g., sentimentos extremos no texto via lex). Mas:
1. Pt-BR análise de sentimentos sem LLM é frágil
2. Saliência é subjetiva — só o usuário sabe o que importa
3. Frontmatter explícito é audit-friendly e configurável post-hoc (usuário pode editar)

#### n (novidade) — `novelty_score`

**Nova coluna** em `notes`: `novelty_score REAL` (nullable, lazy-computed).

**Cálculo:**
```python
def compute_novelty(conn, note_id):
    """1 - max(cosine_similarity) com top-3 vizinhos no corpus existente.

    n=1.0 → nota é totalmente nova (zero overlap)
    n=0.0 → nota é redundante (idêntica a algo existente)
    """
    embedding = get_embedding(conn, note_id)  # do notes_vec
    if embedding is None:
        return 0.5  # default neutro se não tem embedding ainda

    distances = top_k_distances(conn, embedding, exclude_id=note_id, k=3)
    if not distances:
        return 1.0  # corpus vazio = tudo é novo

    # cosine_sim = 1 - cosine_distance, queremos max sim
    max_sim = 1.0 - min(distances)
    return max(0.0, min(1.0, 1.0 - max_sim))
```

**Quando computar:** lazy — primeira vez que `consolidation_candidates` quer o valor de uma nota com `novelty_score IS NULL`, computa e cacheia. Re-computa quando `body_hash` muda (detect via reindex).

**Sem cache invalidation explícita:** se usuário muda o body, `index_note` zera `novelty_score` na hora. Próxima leitura recomputa.

#### α (learning rate)

Config field `consolidation_learning_rate` em `brainiac.toml`. Default 0.5. Ajustável.

Valores menores (0.1) tornam o sistema conservador (precisa de R, E, n altos). Valores maiores (1.0) facilitam promoção.

### 3.3 Threshold

`consolidation_probability_threshold` default 0.6. Notas com `P ≥ threshold` entram em candidates.

## 4. Arquitetura

### 4.1 Mapa de arquivos

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── consolidate.py        # MODIFY: 3o caminho probabilístico
│   │   ├── config.py             # MODIFY: +2 fields
│   │   ├── models.py             # MODIFY: NoteFrontmatter.emotional_weight (opcional)
│   │   ├── index.py              # MODIFY: connect() migration; index_note() persiste emotional_weight
│   │   └── novelty.py            # CREATE: compute_novelty() + cache_novelty()
│   └── mcp_server.py             # MODIFY: tool_add_note aceita emotional_weight
└── tests/
    ├── core/
    │   ├── test_novelty.py       # CREATE
    │   ├── test_consolidate.py   # MODIFY: testes do 3o caminho
    │   ├── test_models.py        # MODIFY: emotional_weight no NoteFrontmatter
    │   ├── test_config.py        # MODIFY: 2 fields novos
    │   └── test_index_vec.py     # MODIFY: schema migration + novelty cache
    └── test_smoke_e2e.py         # MODIFY: 3 DoD tests

.claude/skills/brainiac-capture/SKILL.md  # MODIFY: passo opcional emotional_weight
```

### 4.2 Schema migration

Em `connect()`:

```python
# Phase 7 migrations
try:
    conn.execute("ALTER TABLE notes ADD COLUMN emotional_weight REAL NOT NULL DEFAULT 0.5")
    conn.commit()
except sqlite3.OperationalError:
    pass
try:
    conn.execute("ALTER TABLE notes ADD COLUMN novelty_score REAL")  # nullable
    conn.commit()
except sqlite3.OperationalError:
    pass
```

### 4.3 Config

```python
@dataclass(frozen=True)
class Config:
    # ... existing ...
    # Probabilistic consolidation (Phase 7)
    consolidation_learning_rate: float = 0.5
    consolidation_probability_threshold: float = 0.6
```

### 4.4 NoteFrontmatter

```python
class NoteFrontmatter(BaseModel):
    # ... existing fields ...
    emotional_weight: float = Field(default=0.5, ge=0.0, le=1.0)
```

## 5. Módulo `core/novelty.py`

```python
def compute_novelty(conn, note_id) -> float:
    """1 - max(cosine_sim com top-3 vizinhos). Returns float in [0, 1]."""

def cache_novelty(conn, note_id, value) -> None:
    """UPDATE notes SET novelty_score = ? WHERE id = ?"""

def get_or_compute_novelty(conn, note_id) -> float:
    """Lê de cache; se NULL, computa e cacheia."""
```

## 6. Integração com `consolidate.py`

`consolidation_candidates` ganha 3o caminho:

```python
# Phase 7: probabilistic path
prob_rows = conn.execute("""
    SELECT n.id, n.path, n.access_count, n.last_access,
           n.emotional_weight, COUNT(l.src) as fan_in
    FROM notes n
    LEFT JOIN links l ON l.dst = n.id AND l.kind = 'explicit'
    WHERE n.type = 'working'
      AND n.archived = 0
      AND n.last_access >= ?
    GROUP BY n.id
""", (cutoff,)).fetchall()

for r in prob_rows:
    nid = r[0]
    if nid in seen:
        continue
    R = r[2]  # access_count
    E = r[4]  # emotional_weight
    n_score = get_or_compute_novelty(conn, nid)
    α = config.consolidation_learning_rate
    p = 1 - math.exp(-α * R * E * n_score)
    if p >= config.consolidation_probability_threshold:
        out.append({
            "id": nid, "path": r[1], "access_count": R,
            "last_access": r[3], "fan_in": r[5],
            "suggested_type": "semantic",
            "consolidation_probability": p,
        })
```

## 7. Skill `brainiac-capture` update

Passo opcional após Step 5 (study):

```markdown
6. **Decidir saliência emocional (opcional)**:
   - Se a nota tem peso emocional/importância acima do normal, pergunte:
     "Essa nota é especialmente importante para você? (sim/não/crítico)"
   - Mapeie: não → 0.5 (default), sim → 0.8, crítico → 1.0
   - Para captures rotineiras, NÃO pergunte — apenas use default 0.5
   - Inclua `emotional_weight=0.8` (ou outro valor) no `add_note` call
```

## 8. Testes (resumo)

### 8.1 `tests/core/test_novelty.py` (~10)

- `test_compute_novelty_empty_corpus_returns_one`
- `test_compute_novelty_identical_note_returns_zero`
- `test_compute_novelty_partially_similar_returns_intermediate`
- `test_compute_novelty_excludes_self`
- `test_cache_novelty_updates_column`
- `test_get_or_compute_returns_cached_if_present`
- `test_get_or_compute_computes_and_caches_if_null`
- `test_compute_novelty_no_embedding_returns_default`
- `test_compute_novelty_invalidated_on_body_change` (after re-index_note)
- `test_get_or_compute_does_not_recompute_unchanged`

### 8.2 `tests/core/test_consolidate.py` modificações (~3)

- `test_consolidation_candidates_includes_high_probability_note`: R=5 + E=0.9 + n=0.9 → P≈0.87 ≥ 0.6 → candidato
- `test_consolidation_candidates_excludes_low_probability_note`: R=1 + E=0.5 + n=0.5 → P≈0.06 < 0.6 → não candidato
- `test_consolidation_includes_consolidation_probability_in_result`: candidatos via probabilistic path têm campo `consolidation_probability`

### 8.3 Smoke E2E DoD (3 testes)

- `test_high_emotional_weight_promotes_low_access_note`: 1 acesso + E=1.0 + n=1.0 → P≈0.39 (não promove com threshold=0.6); 3 acessos + E=1.0 + n=1.0 → P≈0.78 (promove). Demonstra que emotional weight amplifica.
- `test_novel_note_promotes_faster_than_redundant`: 2 notas com mesmo access_count, uma novidade alta outra baixa → novel ranqueia P maior
- `test_consolidate_check_returns_probability_field`: MCP tool retorna probabilidade

## 9. Definition of Done

- [ ] Schema migration idempotente adiciona `emotional_weight` + `novelty_score`
- [ ] `compute_novelty` retorna valor sane em corpus vazio, idêntico, parcialmente similar
- [ ] Novelty é cacheada, recomputada após body change
- [ ] `consolidation_candidates` retorna notas via probabilistic path
- [ ] Result inclui `consolidation_probability` quando vem do probabilistic path
- [ ] Skill `brainiac-capture` documenta passo opcional emotional_weight
- [ ] Cobertura `novelty.py` ≥ 95%
- [ ] Suite verde
- [ ] Sem regressões Phases 0-6

## 10. Out of scope

- **Saliência via sentiment analysis**: deferred — usuário-explicit é audit-friendly e suficiente
- **Novelty recomputada a cada query**: muito caro; cache + invalidação por body_hash basta
- **Promoção automática**: candidates ainda exigem confirmação do usuário (consistente com Phases 2/5)
- **Multi-tier emotional weight** (alegria/medo/etc.): scalar único é suficiente; multi-dim deferred

## 11. Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Usuário esquece de marcar emotional_weight, sistema nunca promove | Alta inicialmente | Médio | Default 0.5 dá "alguma chance"; skill capture pergunta quando faz sentido |
| Novelty score lento de computar (cosine sim com corpus inteiro) | Média | Médio | Cached + invalidado por body_hash; vec0 index já é fast |
| Threshold 0.6 é arbitrário | Alta | Baixo | Configurável; calibração via dogfooding pós-uso |
| Probabilidade não-monotônica em casos edge | Baixa | Baixo | Fórmula é estritamente monotônica em cada componente; testes cobrem |
