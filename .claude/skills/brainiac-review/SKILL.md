---
name: brainiac-review
description: Conduz uma sessão de revisão espaçada (SM-2) no brainiac. Use quando o usuário diz "vamos revisar", "tem nota para revisar?", "revisão diária", ou pede explicitamente o ciclo SM-2. Mostra notas vencidas, apresenta a frente (título/contexto), aguarda recall mental, então coleta grade 0-5 e atualiza estado.
---

# Brainiac Review

Sessão interativa de revisão espaçada baseada no algoritmo SuperMemo-2.

## Quando usar

- Usuário pede "revisão", "vamos revisar", "tem o que revisar?"
- Início de dia / fim de tarde — momentos previsíveis de estudo
- Após `brainiac stats` mostrar notas pendentes

## Fluxo

### 1. Buscar fila

Chame `review_queue()` via MCP. Retorna lista ordenada (mais atrasadas primeiro, ties por ease menor).

Se vazia: "Sem notas vencidas hoje. ✓" — encerra.

### 2. Para cada nota

Apresente em duas fases — **frente** primeiro, depois **verso**:

**Frente** (sem revelar o corpo):
```
📝 {id} ({type})
   Overdue: {days_overdue}d · Reps: {reps} · Ease: {ease:.2f}
   Tente recordar o conteúdo desta nota mentalmente.
   Pronto? (enter para ver)
```

Aguarde enter.

**Verso** (corpo completo):
- Chame `get_note(id)` via MCP — retorna body
- Mostre o corpo
- Pergunte: "Quão bem você recordou? [0=esqueci totalmente, 5=lembrei perfeito]"

### 3. Aplicar grade

Chame `grade_review(id, grade)` via MCP. O sistema responde com novo estado:
```
✓ ease={ease:.2f} interval={interval}d próxima={next_review}
```

### 4. Após a fila

Resumo final:
```
Sessão completa.
- Revisadas: X
- Puladas: Y
- Próxima fila: amanhã ({YYYY-MM-DD})
```

## Convenções de grade

| Grade | Significado |
|-------|-------------|
| 0 | Esqueci completamente |
| 1 | Reconheci a resposta ao ver, mas não lembrava |
| 2 | Lembrei parcialmente, com dificuldade |
| 3 | Lembrei com algum esforço (mínimo aprovado) |
| 4 | Lembrei bem, hesitação leve |
| 5 | Lembrei perfeitamente, imediato |

Grades 0-2 reagendam para amanhã (interval=1, reps=0). Grades 3-5 avançam o ciclo.

## Inscrever nota em estudo

Para começar a estudar uma nota existente:
- Chame `start_review(note_id)` via MCP
- A nota entra na fila imediatamente (next_review = hoje)

Para criar uma nova nota já em estudo:
- `add_note(..., study=True)` via MCP

## Não usar quando

- Usuário quer buscar algo → `/brainiac-recall`
- Usuário quer salvar nota → `/brainiac-capture`
- Usuário quer manutenção (decay/promote) → `/brainiac-housekeep`

## Exemplo

```
Usuário: "vamos revisar"

Você → review_queue()
  2 notas vencidas: 2026-05-15-bm25 (5d), 2026-05-19-dkg (1d)

"📝 2026-05-15-bm25 (semantic)
 Overdue: 5d · Reps: 1 · Ease: 2.30
 Tente recordar mentalmente. Pronto?"

→ usuário: "ok"

[mostra corpo via get_note]

"Quão bem você recordou? [0-5]"

→ usuário: "4"
→ grade_review("2026-05-15-bm25", 4)
  ease=2.30 → 2.30 (slight change), interval=2d, next=2026-05-22

"✓ ease=2.30 interval=2d próxima=2026-05-22

📝 2026-05-19-dkg (semantic)
 Overdue: 1d · Reps: 0 · Ease: 2.50
 ..."

[continua até esgotar fila ou usuário dizer parar]

"Sessão completa. Revisadas: 2, puladas: 0."
```

## Observações

- Reviews também bumpam `access_count` e `last_access` — alimentam consolidação automaticamente
- Grade 0-2 não destrói: reset apenas zera `reps` e `interval`; ease ainda diminui gradualmente
- `ease` mínimo é 1.3 — nota nunca fica "presa" abaixo desse floor
- Eventos registrados em `memoryTransfer/logs/events.jsonl` com action=`reviewed`
