---
name: brainiac-capture
description: Salva uma nova nota no brainiac. Use quando o usuário diz "anota isso", "guarda essa ideia", "salva no brainiac", ou pede explicitamente para registrar conhecimento. Determina tipo (episódico / semântico / working), gera id YYYY-MM-DD-slug, popula frontmatter completo.
---

# Brainiac Capture

Orquestra a criação de uma nota bem-formada via MCP tool `add_note`.

## Quando usar

- Usuário pede explicitamente: "salva isso", "anota", "guarda no brainiac"
- Usuário compartilha um aprendizado/conceito/decisão que tem valor de longo prazo
- Ao final de uma exploração técnica que vale persistir

## Passos

1. **Determinar tipo** da nota:
   - `episodic` — narrativa pessoal com timestamp/contexto ("hoje eu fiz X", "decidimos Y na reunião")
   - `semantic` — conceito/fato descontextualizado ("Kubernetes scheduler funciona assim", "BM25 é uma função de ranking")
   - `working` — ideia ainda crua, a ser refinada/promovida depois (rascunho)
   Se ambíguo, pergunte ao usuário.

2. **Gerar `note_id`**: formato `YYYY-MM-DD-slug` onde `slug` é kebab-case ≤ 40 chars, descritivo (não genérico como "note" ou "ideia").

3. **Escrever body tokenizado** (regra do README): bullets densos > prosa. Sem prefácios ("Esta nota fala sobre..."). Direto ao ponto. Use `[[outro-id]]` para cross-refs.

4. **Tags**: 1-3 tags em kebab-case que ajudariam buscar isso depois.

5. **Chamar `add_note`** via MCP com `note_id`, `note_type`, `title`, `body`, `tags`.

6. **Confirmar ao usuário**: arquivo salvo em `<pasta>/<id>.md`.

## Exemplo

Usuário: "anota que `bm25` é uma função de ranking que considera frequência do termo e tamanho do doc"

Você:
- Tipo: `semantic` (conceito impessoal)
- ID: `2026-05-20-bm25-ranking`
- Body: `# BM25\n\n- função de ranking probabilística para busca textual\n- inputs: frequência do termo, tamanho do documento, idf\n- usada em [[fts5-sqlite]] como default scoring`
- Tags: `["information-retrieval", "ranking"]`
- Chamar `add_note(...)`
- Confirmar: "Salvo em semanticMemory/2026-05-20-bm25-ranking.md"
