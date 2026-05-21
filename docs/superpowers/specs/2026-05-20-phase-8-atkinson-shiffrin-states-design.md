# Fase 8 — Atkinson-Shiffrin States

> **Status:** spec criada em 2026-05-20 como parte do batch Phases 6-8.
> **Next:** plano em `docs/superpowers/plans/2026-05-20-phase-8-atkinson-shiffrin-states.md`.

## 1. Objetivo

Modelar explicitamente o **fluxo cognitivo de uma nota através de 4 estados**: `sensory → working → long_term ↔ archived`, com transições governadas por probabilidades computadas dos sinais já existentes (Phase 2 retention, Phase 5 activation, Phase 7 consolidation probability). Unifica conceitos espalhados ("type", "archived", "candidate") em um modelo de estado coeso, expõe queries tipo "notas em estado X" e probabilidades de transição como audit-friendly metadata.

## 2. Contexto

### 2.1 O que existe hoje

Cada nota tem múltiplas propriedades que implicitamente determinam um estado:
- `type ∈ {episodic, semantic, working}` (Phase 0)
- `archived ∈ {0, 1}` (Phase 2)
- Métricas: `strength`/retention, `activation`, `sm2`, `consolidation_probability` (Phases 2-7)

**Limites:**
- "Estado" da nota está implícito — não tem coluna única que diga "sensory" vs "working" vs "long_term"
- "Sensory memory" (memória sensorial, transiente, < 1 min) **não é modelada** — entra direto em working
- Transições são feitas por funções diferentes (`promote_note`, `archive_note`) sem contrato unificado
- Não há query natural "me dá todas notas em transição de X→Y"

### 2.2 Princípio de design

Tornar **estado** uma propriedade de primeira classe da nota, derivada (mas auditável) das outras propriedades. Adicionar um estado `sensory` transiente — buffer de "rascunhos da sessão atual" antes de virarem working notes oficiais. Unificar transições em uma única função `transition_note(id, target_state)` com Markov chain enforcement.

Cada transição registra um evento em `events.jsonl` para auditoria — virando o equivalente cognitivo de um log de transições de estado.

## 3. Modelo de Estados

### 3.1 Os 4 estados

```
   sensory       working          long_term        archived
   ─────────    ─────────       ─────────────    ─────────
   (transient)  (active draft)  (consolidated)   (forgotten)
       │             │                │                │
       │ P_enc=1.0   │ P_cons         │ P_forget       │ resurrect?
       ▼             ▼                ▼                ▲
       working ────► long_term ◄────► archived ────────┘
                                  retention<0.2
```

| Estado | Significado | Storage | Frontmatter `type` | `archived` |
|--------|-------------|---------|---------------------|-----------|
| `sensory` | Rascunho transiente da sessão atual; TTL 5 min se sem ação | `sensory_buffer` table (não em `notes` ainda) | N/A | N/A |
| `working` | Working memory: nota criada, em uso ativo | `notes` table | `working` | 0 |
| `long_term` | Consolidada em memória de longo prazo | `notes` table | `semantic` ou `episodic` | 0 |
| `archived` | Esquecida (Ebbinghaus < threshold) | `notes` table | qualquer | 1 |

### 3.2 Probabilidades de transição

Para cada transição em uma nota:

**sensory → working** (P_enc, encoding):
- `P_enc = 1.0` se usuário confirma "salvar" o draft
- `P_enc = 0.0` se draft expira sem ação
- Não é probabilidade fluida — é discreta. Modelo é "rascunho ou commit".

**working → long_term** (P_cons, consolidation):
- `P_cons` = fórmula Phase 7: `1 - exp(-α·R·E·n)`
- Sistema sinaliza promoção quando `P ≥ threshold`; usuário confirma.

**long_term → archived** (P_forget, forgetting):
- `P_forget` = `1 - retention(Δt, S)` (curva Ebbinghaus invertida)
- Sistema arquiva automaticamente quando `retention < 0.2` (existe na Phase 2)

**archived → long_term** (P_recall, resurrection):
- `P_recall` = não-zero quando nota arquivada é acessada via `recall(include_archived=True)`
- Manual via `tool_resurrect(id)` que move de archive de volta para `longMemory/`

### 3.3 Estado é DERIVADO, não armazenado redundantemente

Decisão arquitetural: **não criar coluna `state TEXT` separada**. Estado é função de `type` + `archived` (+ sensory_buffer presence). Função `current_state(note_id)` computa em runtime.

Razão: evita inconsistência (estado contradizendo type+archived). Performance é OK — função é O(1).

Sensory é exceção: como não vive em `notes`, precisa de tabela própria.

## 4. Arquitetura

### 4.1 Mapa de arquivos

```
tools/brainiac/
├── brainiac/
│   ├── core/
│   │   ├── states.py             # CREATE: current_state, transition_note, transition_probabilities
│   │   ├── sensory.py            # CREATE: sensory_buffer CRUD + TTL expiration
│   │   ├── index.py              # MODIFY: connect() migration + sensory_buffer table
│   │   └── config.py             # MODIFY: +2 fields (sensory_ttl_minutes)
│   ├── mcp_server.py             # MODIFY: tool_transition_note, tool_capture_sensory, tool_resurrect
│   └── cli.py                    # MODIFY: brainiac state <id> + brainiac sensory list
└── tests/
    ├── core/
    │   ├── test_states.py        # CREATE
    │   ├── test_sensory.py       # CREATE
    │   └── test_index_vec.py     # MODIFY: schema migration
    ├── test_mcp_server.py        # MODIFY
    ├── test_cli.py               # MODIFY
    └── test_smoke_e2e.py         # MODIFY: 4 DoD tests
```

### 4.2 Schema novo

```sql
CREATE TABLE sensory_buffer (
    id TEXT PRIMARY KEY,           -- temp id, e.g. "sensory-2026-05-20-12-30-00-uuid"
    title TEXT,
    body TEXT NOT NULL,
    created TEXT NOT NULL,
    expires_at TEXT NOT NULL,      -- ISO-8601: created + sensory_ttl_minutes
    proposed_type TEXT,             -- optional hint from classifier
    proposed_id TEXT               -- proposed final id when committed
);
CREATE INDEX idx_sensory_expires ON sensory_buffer(expires_at);
```

Sem mudanças em `notes`. Estado de notas persistidas é derivado.

### 4.3 Module `core/states.py`

```python
class NoteState(str, Enum):
    SENSORY = "sensory"
    WORKING = "working"
    LONG_TERM = "long_term"
    ARCHIVED = "archived"


VALID_TRANSITIONS = {
    NoteState.SENSORY: {NoteState.WORKING},
    NoteState.WORKING: {NoteState.LONG_TERM},
    NoteState.LONG_TERM: {NoteState.ARCHIVED},
    NoteState.ARCHIVED: {NoteState.LONG_TERM},
}


def current_state(conn, note_id: str) -> NoteState:
    """Derive state from notes table + sensory_buffer."""

def transition_note(
    conn, root, note_id: str, target: NoteState, *, now=None
) -> NoteState:
    """Move a note to target state. Raises if transition is invalid."""

def transition_probabilities(conn, note_id: str) -> dict:
    """Compute current probabilities for each possible transition.

    Returns: {
        "current_state": "working",
        "transitions": {
            "long_term": {"probability": 0.65, "reason": "P_cons = 1-exp(-α·R·E·n)"},
            "archived": {"probability": 0.05, "reason": "P_forget = 1 - retention"},
        }
    }
    """
```

### 4.4 Module `core/sensory.py`

```python
def add_sensory(conn, body, *, title=None, proposed_type=None, proposed_id=None, ttl_minutes=5) -> str:
    """Insert into sensory_buffer. Returns generated id."""

def list_sensory(conn, now=None, include_expired=False) -> list[dict]:
    """List sensory buffer, filter by expiration if requested."""

def commit_sensory(conn, root, sensory_id, *, note_type, final_id) -> str:
    """Promote sensory → working: create real note, delete from buffer."""

def expire_sensory(conn, now=None) -> int:
    """Delete expired entries. Returns count deleted."""

def get_sensory(conn, sensory_id) -> dict | None:
    """Read one entry."""
```

### 4.5 MCP tools novos

- `tool_capture_sensory(body, title=None, proposed_type=None) -> dict`: rascunho transiente
- `tool_list_sensory() -> list[dict]`: lista buffer ativo
- `tool_commit_sensory(sensory_id, note_type, final_id) -> dict`: promove para working
- `tool_transition_note(note_id, target_state) -> dict`: unifica promote/archive/resurrect
- `tool_note_state(note_id) -> dict`: estado atual + transition_probabilities

Total: 16 → 12 + 5 = 17 tools.

### 4.6 CLI

- `brainiac state <id>` — mostra estado + probabilidades de transição
- `brainiac sensory list` — lista rascunhos transitórios
- `brainiac sensory commit <sensory_id>` — promove rascunho (interativo: pergunta type+final_id)

### 4.7 Config

```python
# Atkinson-Shiffrin states (Phase 8)
sensory_ttl_minutes: int = 5
```

## 5. Testes (resumo)

### 5.1 `tests/core/test_states.py` (~15)

- `test_current_state_working_for_working_type_unarchived`
- `test_current_state_long_term_for_semantic_unarchived`
- `test_current_state_long_term_for_episodic_unarchived`
- `test_current_state_archived_when_archived_flag_set`
- `test_current_state_sensory_when_in_buffer`
- `test_transition_working_to_long_term_succeeds`
- `test_transition_working_to_archived_rejected` (skip intermediate state)
- `test_transition_long_term_to_archived_succeeds`
- `test_transition_archived_to_long_term_succeeds` (resurrect)
- `test_transition_sensory_to_working_succeeds`
- `test_transition_creates_audit_event`
- `test_transition_probabilities_working_note`
- `test_transition_probabilities_long_term_note`
- `test_transition_probabilities_includes_reason`
- `test_transition_invalid_raises`

### 5.2 `tests/core/test_sensory.py` (~10)

- `test_add_sensory_inserts_with_generated_id`
- `test_add_sensory_sets_expires_at_correctly`
- `test_list_sensory_excludes_expired`
- `test_list_sensory_include_expired_flag`
- `test_commit_sensory_creates_real_note`
- `test_commit_sensory_deletes_buffer_entry`
- `test_commit_sensory_raises_for_unknown`
- `test_expire_sensory_deletes_old_entries`
- `test_expire_sensory_keeps_fresh`
- `test_get_sensory_returns_entry`

### 5.3 Smoke E2E DoD (4 testes)

- `test_sensory_to_working_full_cycle`: capture sensory → list → commit → real note exists
- `test_state_machine_enforces_valid_transitions`: try working → archived directly, expect rejection
- `test_state_machine_archived_to_long_term_resurrects`: archive a note, then resurrect via transition_note
- `test_transition_probabilities_reflects_current_metrics`: working note with high R/E/n shows P_cons ≥ 0.6

## 6. Definition of Done

- [ ] `current_state` deriva corretamente para todos os 4 estados
- [ ] `transition_note` aplica enforcement Markov (rejeita pulos)
- [ ] `transition_probabilities` retorna probabilidades calibradas
- [ ] Sensory buffer CRUD funcional (add/list/commit/expire)
- [ ] Schema migration idempotente
- [ ] 5 MCP tools novos funcionais
- [ ] CLI `brainiac state <id>` mostra estado + probabilidades
- [ ] Cobertura `states.py` e `sensory.py` ≥ 95%
- [ ] Suite verde sem regressões

## 7. Out of scope

- **Background expiration job**: sensory TTL é checked-on-read, não há cron. Decisão para fase futura.
- **Estado "encoded" intermediário** (registro sensorial → atenção → working): simplificação aceita. Modelo Atkinson-Shiffrin clássico tem 3 estados (MS/MCP/MLP); brainiac tem 4 com archived adicional, mas omite estágio "atenção".
- **Métricas históricas de tempo em cada estado** ("nota X passou 30 dias em working"): pode ser derivado dos eventos no futuro.
- **Backfill de notas existentes**: notas pre-existentes assumem estado derivado normalmente. Sensory começa vazio.

## 8. Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Tabela `sensory_buffer` vaza (TTL não rodando) | Média | Baixo | `expire_sensory` chamado a cada `list_sensory` |
| Markov enforcement quebra fluxo de promoção existente | Média | Médio | `promote_note` Phase 2 → wrap em `transition_note(target=LONG_TERM)`; testes de regressão garantem |
| State `current_state` retorna valor inconsistente com type+archived | Baixa | Médio | Tests cobrem 4 estados explicitamente; sem coluna duplicada evita drift |
| User confusion: por que 4 estados? | Média | Baixo | CLI mostra estado com explicação; docs atualizadas |
