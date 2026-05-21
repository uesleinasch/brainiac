# Política de segurança

## Versões suportadas

Como o brainiac está em estágio inicial (pré-1.0), apenas a versão mais recente em `main` recebe correções de segurança.

| Versão | Suportada |
|--------|-----------|
| `main` | ✅ Sim |
| `< 0.1.0` | ❌ Não |

## Reportando uma vulnerabilidade

**Não abra issues públicas para vulnerabilidades de segurança.**

Use o canal privado do GitHub:

🔒 **[Abrir Security Advisory privado](https://github.com/uesleinasch/brainiac/security/advisories/new)**

Forneça pelo menos:

- Descrição do problema
- Passos para reproduzir (PoC quando possível)
- Versão afetada (commit SHA ou tag)
- Impacto estimado
- Sugestão de correção, se tiver

### O que esperar

| Etapa | Prazo |
|-------|-------|
| Confirmação de recebimento | até 72 h |
| Análise inicial + classificação de severidade | até 7 dias |
| Correção + release | até 30 dias (depende da severidade) |
| Divulgação pública coordenada | após o patch estar disponível |

Caso o problema afete dependências (`mcp`, `pydantic`, `sentence-transformers`, `sqlite-vec`, etc.), encaminharei o reporte ao maintainer apropriado e te manterei informado.

## Superfície de ataque conhecida

O brainiac é um sistema **local-first**: roda no seu computador, lê e escreve arquivos locais, e o índice fica em SQLite local. Não há serviços de rede expostos por padrão.

Vetores potenciais que mantemos em mente:

| Vetor | Mitigação atual |
|-------|-----------------|
| Frontmatter malicioso em `.md` (injeção via Pydantic) | Schema strict + `ConfigDict(extra="forbid")` |
| SQL injection | Todas queries usam parameter binding |
| Code execution via embeddings cache | `sentence-transformers` carrega modelo, não código arbitrário |
| MCP tool invocation maliciosa | Tools são funções Python puras com inputs tipados via Pydantic |
| Path traversal (note_id arbitrário) | `paths.py` resolve sempre dentro do brainiac root |

Se encontrar um vetor novo, reporte privadamente como descrito acima.

## Boas práticas para usuários

- Não exponha o MCP server (stdio) via rede sem autenticação adicional.
- Mantenha o brainiac atualizado: `bash ~/.local/share/brainiac/scripts/update.sh`.
- Revise notas Markdown obtidas de terceiros antes de importar (o parser do `python-frontmatter` é robusto, mas vale o cuidado).
- O `index.sqlite` em `memoryTransfer/` contém o conteúdo das notas em texto plano (FTS5 + embeddings). Trate o arquivo com a mesma sensibilidade das notas.

## Reconhecimento

Pesquisadores que reportarem vulnerabilidades válidas serão creditados no `CHANGELOG.md` (a menos que solicitem anonimato).

Obrigado por ajudar a manter o brainiac e seus usuários seguros.
