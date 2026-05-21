# Fase 6 — Spreading Activation Iterative

> **Status:** spec criada em 2026-05-20 como parte do batch Phases 6-8.
> **Next:** plano em `docs/superpowers/plans/2026-05-20-phase-6-spreading-activation.md`.

## 1. Objetivo

Substituir a expansão 1-hop estática do `recall()` (Phase 1) por um algoritmo iterativo de N-hops baseado na fórmula `aⱼ(t+1) = aⱼ(t) + Σᵢ aᵢ(t) · wᵢⱼ · γ`. Notas distantes 2-3 hops da seed podem emergir como relevantes via **co-ativação**: múltiplos caminhos pequenos somam mais que um caminho direto fraco. Captura o comportamento cognitivo de spreading activation descrito em §`semanticMemory` do `human_memory_math_models.html`.

## 2. Contexto

### 2.1 O que existe hoje

`recall()` (Phase 1 + Phase 5):
1. Top-K seeds via cosine similarity (Phase 1)
2. 1-hop expansion: cada seed propaga `seed_score × NEIGHBOR_DECAY × weight` aos vizinhos (Phase 1)
3. Re-rank combinando semantic + activation z-score (Phase 5)

O passo (2) é **um único passo** de propagação. Notas a 2 hops da seed nunca aparecem, mesmo se houver evidência forte por múltiplos caminhos.

### 2.2 Limites do modelo atual

Cenário: query "DKG protocol" retorna nota A. A linka para B (peso 1.0); B linka para C (peso 1.0); C contém informação altamente relevante mas não foi semanticamente próxima da query. C nunca aparece no recall atual — está a 2 hops.

Fenômeno cognitivo perdido: **spreading activation**. Em humanos, ativar um conceito acende seus vizinhos, depois os vizinhos dos vizinhos, com decay por distância. Notas com múltiplas pontes para a seed (alta convergência) ganham ativação significativa.

### 2.3 Princípio de design

Substituir 1-hop por N-hop iterativo. Mesma fonte de dados (tabela `links`), mesmo input (seeds do recall semântico + activation), output **estritamente superior** (1-hop é caso especial de N-hop com max_hops=1).

## 3. Algoritmo

### 3.1 Fórmula

Para cada iteração `t`:

```
aⱼ(t+1) = aⱼ(t) + γ · Σᵢ aᵢ(t) · wᵢⱼ

onde:
  γ = spreading_decay ∈ (0, 1) — atenuação por hop (default 0.5)
  wᵢⱼ = peso da aresta i→j (já existe em links.weight)
  aᵢ(t) = ativação do nó i no step t
```

**Inicialização (t=0):**
- Para seeds do recall semântico: `aᵢ(0) = score_combinado(semantic, activation)` (já calculado pelo Phase 5)
- Para nós não-seed: `aⱼ(0) = 0`

**Convergência:**
- Para quando `max(|aⱼ(t+1) − aⱼ(t)|) < spreading_epsilon` (default 0.01)
- OU `t == spreading_max_hops` (default 3)

**Output:**
- `final_score(j) = aⱼ(final)`
- Filtrar nós com `final_score < spreading_floor` (default 0.05)
- Ordenar desc, retornar top-K

### 3.2 Por que somatório acumulativo (não substituição)

Alternativa rejeitada: `aⱼ(t+1) = γ · Σᵢ aᵢ(t) · wᵢⱼ` (sem somar `aⱼ(t)`).

Problema: nós seed perderiam sua ativação inicial após o primeiro step — começariam alta, depois recuariam para o que vier dos vizinhos. Não captura "permanência" do conceito ativado.

Versão acumulativa: a ativação cresce, captura convergência (múltiplos caminhos somam), e converge para um ponto fixo onde `γ < 1` garante atenuação total ao longo dos hops.

### 3.3 Tipos de aresta

Reusa a tabela `links` existente com `kind ∈ {explicit, implicit}` (Phase 1):

- **Explicit**: link declarado via `[[id]]` no body ou `add_link()` MCP. `weight = 1.0` default.
- **Implicit**: pares com cosine similarity ≥ 0.75 computados em runtime via `graph.py`. `weight = similarity_score`.

Ambos contribuem igualmente para a propagação. Não há tratamento especial.

### 3.4 Custo computacional

Para N notas com média K links por nota e H hops:
- Por hop: O(N · K) operações (cada nó propaga para seus vizinhos)
- Total: O(H · N · K)

Para brainiac (N < 10k esperado, K < 20, H = 3): ~600k ops por recall, ~50ms em SQLite + Python. Aceitável.

Sem persistência — cada query computa do zero. Cache não compensa porque accesses mudam continuamente.

## 4. Arquitetura

### 4.1 Mapa de arquivos

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── spreading.py          # CREATE: spread_activation() (pure + I/O leve)
│   │   ├── config.py             # MODIFY: +4 fields (spreading_max_hops, spreading_decay, spreading_epsilon, spreading_floor)
│   │   └── index.py              # MODIFY: recall() substitui 1-hop por spread_activation()
│   ├── mcp_server.py             # MODIFY: nenhum — recall já é exposto
│   └── cli.py                    # nenhum
└── tests/
    ├── core/
    │   ├── test_spreading.py     # CREATE: unit tests + integration
    │   └── test_index_vec.py     # MODIFY: ajustar test de recall 1-hop existente
    └── test_smoke_e2e.py         # MODIFY: DoD Phase 6
```

### 4.2 Schema

Sem mudanças. Reusa `links(src, dst, kind, weight)` e `accesses` (para activation seeds via Phase 5).

### 4.3 Config

`brainiac/core/config.py` ganha 4 fields:

```python
@dataclass(frozen=True)
class Config:
    # ... existing fields ...
    # Spreading activation (Phase 6)
    spreading_max_hops: int = 3
    spreading_decay: float = 0.5
    spreading_epsilon: float = 0.01
    spreading_floor: float = 0.05
```

`brainiac.toml`:
```toml
spreading_max_hops = 3
spreading_decay = 0.5
spreading_epsilon = 0.01
spreading_floor = 0.05
```

## 5. Módulo `core/spreading.py`

### 5.1 API

```python
# Pure
def spread_activation(
    seeds: dict[str, float],            # initial activation: note_id → score
    edges: dict[str, list[tuple[str, float]]],   # adjacency: note_id → [(neighbor, weight), ...]
    *,
    max_hops: int = 3,
    decay: float = 0.5,
    epsilon: float = 0.01,
    floor: float = 0.05,
) -> dict[str, float]:
    """Iterate spreading activation until convergence or max_hops.

    Returns {note_id: final_activation} filtered by floor.
    """

# I/O helper
def load_edges(
    conn: sqlite3.Connection,
    note_ids: list[str] | None = None,
    include_implicit: bool = True,
) -> dict[str, list[tuple[str, float]]]:
    """Load adjacency list from links table. Optionally restricted to subset."""
```

### 5.2 Pseudocode

```python
def spread_activation(seeds, edges, *, max_hops, decay, epsilon, floor):
    a = dict(seeds)  # copia, não mutate input
    for hop in range(max_hops):
        delta = {}
        for src, score in a.items():
            for dst, weight in edges.get(src, []):
                contribution = decay * score * weight
                delta[dst] = delta.get(dst, 0.0) + contribution
        if not delta:
            break
        max_change = 0.0
        for dst, contrib in delta.items():
            a[dst] = a.get(dst, 0.0) + contrib
            max_change = max(max_change, abs(contrib))
        if max_change < epsilon:
            break
    return {nid: score for nid, score in a.items() if score >= floor}
```

### 5.3 Integração no `recall()`

Em `index.py::recall()`, substituir o trecho 1-hop atual:

**Antes:**
```python
# Phase 1: 1-hop expansion
for s in seeds:
    seed_score = float(s["score"])
    for dst, meta in neighbors_of(conn, s["id"]).items():
        neighbor_score = seed_score * NEIGHBOR_DECAY * float(meta["weight"])
        # ... merge into scored ...
```

**Depois:**
```python
# Phase 6: N-hop spreading activation
from brainiac.core.spreading import load_edges, spread_activation
seed_dict = {s["id"]: float(s["score"]) for s in seeds}
candidate_ids = list(seed_dict.keys())
edges = load_edges(conn, note_ids=None)  # full graph
final_scores = spread_activation(
    seed_dict, edges,
    max_hops=config.spreading_max_hops,
    decay=config.spreading_decay,
    epsilon=config.spreading_epsilon,
    floor=config.spreading_floor,
)
# Build scored dict from final_scores (lookup path/type/title via DB)
for nid, score in final_scores.items():
    # ... build entry, set origin based on whether it was a seed or expanded ...
```

O re-rank Phase 5 (combinação com activation z-score) continua aplicado **depois** do spreading.

## 6. Testes

### 6.1 `tests/core/test_spreading.py`

**Pure function tests (~12):**
- `test_spread_no_edges_returns_seeds_unchanged`
- `test_spread_single_hop_matches_phase1_behavior` (com max_hops=1)
- `test_spread_two_hops_reaches_grandchildren`
- `test_spread_convergence_stops_early_when_delta_small`
- `test_spread_max_hops_caps_iterations`
- `test_spread_floor_excludes_low_activation_nodes`
- `test_spread_co_activation_two_paths_sum`
- `test_spread_decay_attenuates_per_hop`
- `test_spread_empty_seeds_returns_empty`
- `test_spread_self_loop_handled` (nó com aresta para si mesmo)
- `test_spread_disconnected_graph_seeds_only`
- `test_spread_high_decay_localizes_activation` (decay≈1 → atinge tudo; decay≈0 → fica nos seeds)

**I/O helper tests (~3):**
- `test_load_edges_returns_full_graph`
- `test_load_edges_includes_both_explicit_and_implicit`
- `test_load_edges_handles_empty_db`

### 6.2 `tests/core/test_index_vec.py` (modificar)

Ajustar testes existentes de recall 1-hop para refletir comportamento N-hop. Alguns testes que assumem "vizinhos a 2 hops não aparecem" precisam ser revistos.

### 6.3 Smoke E2E DoD (3 testes em `test_smoke_e2e.py`):

- `test_spreading_reaches_distant_relevant_note`: cria grafo A→B→C, query semanticamente próxima de A; assert C aparece no top-K (com max_hops≥2)
- `test_co_activation_promotes_convergent_node`: 3 seeds → todos linkam para D; D recebe activation somada e supera os seeds em score final
- `test_spreading_respects_floor_filter`: nó muito distante (5 hops) não passa o floor, fica de fora

## 7. Definition of Done

- [ ] `spread_activation` puro implementado com convergência e floor
- [ ] `recall()` usa N-hop em vez de 1-hop
- [ ] Co-ativação demonstrável: 2 paths somam (`test_co_activation_promotes_convergent_node`)
- [ ] Spreading respeita epsilon e max_hops (terminação garantida)
- [ ] Spreading respeita floor (filtra ruído)
- [ ] Cobertura `spreading.py` ≥ 95%
- [ ] Suite completa verde (esperado ~270 após Phase 6)
- [ ] Sem regressões Phases 0-5

## 8. Out of scope

- **Caching de edges**: re-loaded por query. Pode-se cachear depois se profiling indicar.
- **Spreading bidirecional**: atualmente propaga apenas no sentido `src → dst` das arestas. Bidirecional dobraria custo. Decisão para fase futura se necessário.
- **Edge weights aprendidas**: pesos vêm da Phase 1 (cosine similarity para implicit, 1.0 para explicit). Phase 6 não treina pesos.
- **Visualização do grafo**: utilitário tipo `brainiac graph <id>` é deferido.

## 9. Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Spread explode em grafo denso (todos ativados) | Média | Médio | `spreading_floor=0.05` + max_hops=3 + decay=0.5 limitam |
| Performance ruim com 10k+ notas | Baixa | Médio | `load_edges` é uma query SQL; em-memória dict é fast |
| 1-hop tests existentes quebram silenciosamente | Alta | Baixo | Adaptar testes na Task de integração |
| Co-activation amplifica notas irrelevantes | Média | Baixo | `floor` filtra; tuning pós-uso |
