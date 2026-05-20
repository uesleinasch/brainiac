---
name: brainiac-recall
description: Busca no brainiac por uma query e sintetiza uma resposta contextual com as notas relevantes. Use quando o usuário pergunta sobre algo que ele provavelmente já registrou, ou pede explicitamente "veja no brainiac", "lembre o que sabemos sobre X".
---

# Brainiac Recall

Orquestra busca semântica + expansão no grafo + leitura das notas mais relevantes via MCP tools `recall` + `get_note`.

## Quando usar

- Usuário pergunta sobre tópico que ele provavelmente já anotou
- Usuário pede: "veja no brainiac", "o que sabemos sobre X", "lembra aquilo de..."
- Antes de explicar conceito que pode ter sido registrado anteriormente — vale checar

## Passos

1. **Chamar `recall(query, k=5)`** com a query em pt-BR. Receba lista de notas com `id`, `title`, `path`, `score`, `origin`.

2. **Interpretar `origin`**:
   - `semantic` — a nota veio diretamente do top-k por similaridade semântica
   - `explicit` — chegou pela expansão via link declarado pelo usuário
   - `implicit` — chegou pela expansão via similaridade ≥ 0.75 com alguma seed
   - `both` — apareceu por mais de uma rota (sinal forte de relevância)
   - `fts` — modelo de embeddings indisponível; fallback BM25 (sem badge associativo)

3. **Priorizar** notas com `origin ∈ {semantic, both}`; tratar `explicit`/`implicit` como contexto adjacente útil.

4. **Ler integralmente** via `get_note(note_id)` apenas as notas que parecem realmente relevantes ao snippet/título. `get_note` incrementa `access_count`.

5. **Sintetizar resposta**:
   - Cite cada nota usada por `id` (ex: "conforme anotado em `2026-05-20-bm25-ranking`...")
   - Mencione a origem quando relevante ("essa nota apareceu por similaridade implícita com X")
   - Se houver gaps, diga claramente — não invente

6. **Sugerir nota nova** se a resposta levou a um insight que vale persistir (handoff implícito para `brainiac-capture`).

## Sinalização de ativação (Phase 5)

Para cada resultado de recall, você pode chamar `inspect_note(id)` via MCP para enriquecer a apresentação. Se `activation > 1.5`, adicione o badge **🔥 ativação alta** ao mostrar a nota — indica que o traço de memória está em uso ativo e vale a pena ser revisitado.

Use com moderação: só chame `inspect_note` quando o usuário pedir mais contexto ou quando o resultado for ambíguo. Em recall simples, o output puro do `recall()` é suficiente.

## Quando não usar

- Pergunta sobre algo fora do escopo das notas do usuário ("qual a capital da França")
- Conversa puramente operacional (rodar comando, debugar erro local)

## Exemplo

Usuário: "lembra como funciona aquele algoritmo de ranking que vimos?"

Você:
1. `recall("algoritmo de ranking", k=5)` → `[{id: "2026-05-20-bm25-ranking", origin: "semantic", score: 0.62}, {id: "2026-05-20-tf-idf", origin: "implicit", score: 0.21}]`
2. `get_note("2026-05-20-bm25-ranking")` — leitura integral
3. Resposta: "Você anotou BM25 em `2026-05-20-bm25-ranking` (match semântico direto). A nota `2026-05-20-tf-idf` apareceu por similaridade implícita — pode ser contexto útil. BM25 é função de ranking probabilística que considera TF, comprimento do doc e IDF; é o default scoring do FTS5 do SQLite."
