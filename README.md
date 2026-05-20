# Brainiac

Um "segundo cérebro" pessoal em arquivos Markdown que replica mecânicas centrais da memória humana: consolidação short→long, curva de esquecimento (Ebbinghaus), recall associativo via embeddings + grafo, revisão espaçada (SuperMemo-2), distinção episódico/semântico e limite de working memory.

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
    └── index.sqlite     # FTS5 + vec0 (embeddings 384-dim)
```

Cada nota é um `.md` com frontmatter YAML carregando metadata cognitiva (`type`, `created`, `last_access`, `access_count`, `strength`, `links`, `tags`, `sm2`).

## Stack

- **Python ≥ 3.11** (`tomllib` stdlib)
- **MCP** (`mcp>=1.0`) — servidor stdio que Claude Code conecta
- **SQLite + sqlite-vec** — índice FTS5 + vetorial em um único arquivo
- **sentence-transformers** — `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, pt-BR)
- **Pydantic v2** — schema strict do frontmatter
- **Click 8** — CLI

Sem dependências de cloud, banco externo ou UI. Tudo local, em arquivos.

## Comandos CLI

```
brainiac mcp          # inicia servidor MCP (stdio) para Claude Code
brainiac reindex      # reconstrói index.sqlite varrendo .md
brainiac stats        # contadores por tipo, total, links, arquivadas
brainiac decay        # roda Ebbinghaus; arquiva notas abaixo do threshold
brainiac consolidate  # promove working → semantic/episodic
brainiac review       # sessão interativa SM-2 (grade 0-5)
brainiac classify <path>  # sugere tipo para nota legada
```

## MCP Tools (11)

`add_note`, `recall`, `get_note`, `link`, `list_recent`, `consolidate_check`, `forget`, `review_queue`, `grade_review`, `start_review`, `working_status`

## Skills Claude Code

- `brainiac-capture` — salva nova nota (com classificador de tipo)
- `brainiac-recall` — busca e sintetiza
- `brainiac-housekeep` — ciclo semanal decay + consolidate
- `brainiac-review` — sessão SM-2 interativa

## Configuração opcional

`brainiac.toml` na raiz do brainiac (todos os campos opcionais; defaults seguros):

```toml
working_memory_limit = 9        # default; reduz para forçar disciplina
classifier_threshold = 0.3      # confiança mínima do classifier
```

## Roadmap de 5 fases — completo

| Fase | Entrega |
|------|---------|
| 0 — Foundation | MCP server + SQLite + capture/recall via FTS5 |
| 1 — Recall associativo | Embeddings 384-dim + grafo 1-hop |
| 2 — Consolidação + Decay | Ebbinghaus + promoção working → long |
| 3 — SM-2 Spaced Repetition | Revisão ativa com grade 0-5 |
| 4 — Working memory + tipos | Limite hard + classificador heurístico |

Algoritmos referência: spec em [`docs/superpowers/specs/2026-05-20-brainiac-memory-design.md`](docs/superpowers/specs/2026-05-20-brainiac-memory-design.md); planos por fase em `docs/superpowers/plans/`.

## Desenvolvimento

```bash
cd tools/brainiac
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest --ignore=tests/core/test_embeddings.py
```

Cobertura ≥ 80% por módulo do core (`note`, `index`, `decay`, `consolidate`, `sm2`, `classifier`, `working_memory`, `config`).

## Licença

[MIT](LICENSE) © Ueslei Nascimento
