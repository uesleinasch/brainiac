---
name: brainiac-recall
description: Busca no brainiac por uma query e sintetiza uma resposta contextual com as notas relevantes. Use quando o usuário pergunta sobre algo que ele provavelmente já registrou, ou pede explicitamente "veja no brainiac", "lembre o que sabemos sobre X".
---

# Brainiac Recall

Orquestra busca + leitura das notas mais relevantes via MCP tools `recall` + `get_note`.

## Quando usar

- Usuário pergunta sobre tópico que ele provavelmente já anotou
- Usuário pede: "veja no brainiac", "o que sabemos sobre X", "lembra aquilo de..."
- Antes de explicar conceito que pode ter sido registrado anteriormente — vale checar

## Passos

1. **Chamar `recall(query, k=5)`** com a query em pt-BR (FTS5 funciona com pt-BR direto). Receba lista de notas com `id`, `title`, `snippet`, `path`.

2. **Avaliar os snippets**: se algum parece claramente relevante, leia integralmente via `get_note(note_id)`. Isso também incrementa `access_count` (sinal de relevância pra fase 2).

3. **Sintetizar resposta**:
   - Use o conhecimento da(s) nota(s) como contexto autoritativo
   - Cite cada nota usada por `id` (ex: "conforme anotado em `2026-05-20-bm25-ranking`...")
   - Se houver gaps na informação, diga claramente — não invente

4. **Sugerir nota nova** se a resposta levou a um insight que vale a pena persistir (handoff implícito pra `brainiac-capture`).

## Quando não usar

- Pergunta sobre algo claramente fora do escopo das notas do usuário (ex: "qual a capital da França" — não invocar)
- Conversa puramente operacional (rodar comando, debugar erro local)

## Exemplo

Usuário: "lembra como funciona aquele algoritmo de ranking que vimos?"

Você:
1. `recall("algoritmo de ranking", k=5)` → retorna `[{id: "2026-05-20-bm25-ranking", snippet: "função de ranking probabilística..."}]`
2. `get_note("2026-05-20-bm25-ranking")` → corpo completo
3. Resposta: "Você anotou sobre BM25 em `2026-05-20-bm25-ranking`. É uma função de ranking probabilística que considera frequência do termo, tamanho do doc e IDF. Foi mencionada como default scoring do FTS5 do SQLite. Quer expandir algum ponto?"
