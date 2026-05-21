# Contribuindo com o Brainiac

Obrigado por considerar contribuir! Este documento descreve o processo para reportar bugs, sugerir features, e enviar pull requests.

Ao participar deste projeto você concorda em seguir o [Código de Conduta](CODE_OF_CONDUCT.md).

---

## Sumário

- [Como reportar bugs](#como-reportar-bugs)
- [Como sugerir features](#como-sugerir-features)
- [Setup do ambiente de desenvolvimento](#setup-do-ambiente-de-desenvolvimento)
- [Fluxo de trabalho](#fluxo-de-trabalho)
- [Padrões de código](#padrões-de-código)
- [Padrão de commits](#padrão-de-commits)
- [Processo de pull request](#processo-de-pull-request)
- [Escopo do projeto](#escopo-do-projeto)

---

## Como reportar bugs

1. Verifique se [já existe uma issue aberta](../../issues) com o mesmo problema.
2. Reproduza o bug na versão mais recente de `main`.
3. Abra uma nova issue usando o template **🐛 Bug report**. Inclua:
   - Output completo / traceback Python
   - Versão do brainiac (`pip show brainiac | grep Version` ou SHA do commit)
   - Versão do Python e sistema operacional
   - `brainiac.toml` se você customizou defaults

## Como sugerir features

Antes de abrir uma issue de feature, **veja o [escopo do projeto](#escopo-do-projeto)**. Ideias fora do escopo (UI web, sync cloud, app mobile) serão recusadas com gratidão mas firmeza.

Para features dentro do escopo, use o template **✨ Feature request** e descreva:
- O problema concreto que você quer resolver (não a solução)
- Alternativas que você já considerou
- Referências (papers, projetos similares)

## Setup do ambiente de desenvolvimento

```bash
git clone https://github.com/uesleinasch/brainiac.git
cd brainiac/tools/brainiac
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Verificar:

```bash
.venv/bin/pytest --ignore=tests/core/test_embeddings.py --no-cov
# Deve mostrar: 340+ passed
```

`test_embeddings.py` é excluído porque carrega `paraphrase-multilingual-MiniLM-L12-v2` (~430 MB, ~3 s). Para rodar incluindo:

```bash
.venv/bin/pytest                # primeira vez: ~30 s (download do modelo)
```

## Fluxo de trabalho

1. **Fork** o repositório e clone seu fork.
2. **Crie uma branch** descritiva a partir de `main`:
   ```bash
   git checkout -b feat/short-description
   # ou
   git checkout -b fix/bug-description
   ```
3. **Desenvolva seguindo TDD** (veja abaixo).
4. **Faça commits atômicos** com mensagens no padrão Conventional Commits.
5. **Push** para o seu fork e abra um pull request contra `main`.

## Padrões de código

### TDD obrigatório para `core/`

Toda mudança em `tools/brainiac/brainiac/core/` deve seguir o ciclo:

1. **RED** — escreva um teste que falha que descreva o comportamento desejado.
2. **GREEN** — implemente o mínimo para fazer o teste passar.
3. **REFACTOR** — limpe o código se necessário, mantendo os testes verdes.
4. **Commit** com `feat(scope):` ou `fix(scope):`.

Existem 340+ testes hoje. Veja `tests/core/test_states.py` ou `tests/core/test_novelty.py` como exemplos canônicos.

### Cobertura mínima

- **≥ 80%** por módulo do `core/`
- **≥ 95%** para módulos puros (sem I/O)
- Use `# pragma: no cover` somente em branches genuinamente defensivos (validações redundantes protegidas por CHECK constraint).

Verifique:

```bash
.venv/bin/pytest --cov=brainiac.core.<module> --cov-report=term-missing \
  --ignore=tests/core/test_embeddings.py
```

### Estilo

- **Lint:** `ruff check brainiac tests`
- **Asserções concretas**, nunca tautológicas:
  - ✅ `assert ease == pytest.approx(2.18)`
  - ❌ `assert ease < 2.5`
- **Sem comentários óbvios.** Docstrings apenas onde o *porquê* não é trivial (ex: fórmula SM-2).
- **Lazy imports** dentro de funções MCP/CLI para evitar ciclos e custo de cold start.

### Idiomas

- **Código, comentários, docstrings, commit messages, este arquivo:** inglês (commit subject line pode ser pt-BR quando contém terminologia interna do projeto).
- **README, mensagens de erro voltadas ao usuário, descrições de MCP tools, skills:** português brasileiro.

### Dependências

Não adicione novas deps pip sem justificativa explícita no PR. Todo o brainiac (8 phases) foi entregue com apenas:

`mcp`, `pydantic`, `python-frontmatter`, `click`, `sentence-transformers`, `sqlite-vec`, `numpy` + stdlib (`math`, `uuid`, `enum`, `datetime`, `sqlite3`, `tomllib`).

### Schema migrations

Mudanças no schema do `index.sqlite` devem ser **idempotentes** em `connect()` (use `try / except sqlite3.OperationalError: pass`). Veja como Phases 7 e 8 adicionaram colunas.

## Padrão de commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[body]

[footer]
```

**Types comuns:**
- `feat:` — nova funcionalidade
- `fix:` — correção de bug
- `docs:` — apenas documentação
- `test:` — apenas testes (ou refatoração de teste existente)
- `refactor:` — mudança interna sem alterar comportamento
- `chore:` — build, CI, deps, config
- `perf:` — melhoria de performance

**Scopes comuns:** `core`, `cli`, `mcp`, `index`, `decay`, `consolidate`, `sm2`, `states`, `sensory`, `novelty`, `scripts`, `readme`.

Exemplos:

```
feat(states): adiciona transição sensory → working com Markov enforcement
fix(decay): corrige off-by-one na janela de archive
docs(readme): adiciona seção de troubleshooting
test(novelty): cobre branch de corpus vazio
chore(ci): habilita Python 3.12 na matrix
```

Um PR pode (e deve, quando faz sentido) conter múltiplos commits — cada um atômico, cada um green.

## Processo de pull request

1. **Garanta que a suite passa** localmente antes de pushar.
2. **Abra o PR contra `main`** usando o template.
3. **CI deve passar:** `tests`, `lint`, `install-script` precisam estar verdes.
4. **Revise você mesmo** o diff antes de pedir revisão humana — diffs grandes podem incluir mudanças não intencionais.
5. **Aguarde review.** Manutenedores tentam responder em até 7 dias.
6. **Endereçe feedback** com novos commits (não force-push até o PR estar aprovado). Após aprovação, é OK fazer squash.
7. **Merge** é feito pelo mantenedor (merge linear, sem merge commits).

### O que vai te fazer apanhar review

- Asserções tautológicas (`assert value > 0`) ao invés de pin de valor.
- Faltar testes para novo comportamento.
- Comentários óbvios ("# increment counter" antes de `counter += 1`).
- Esconder novas deps em `requirements.txt` sem mencionar no PR.
- Schema change não idempotente.
- Bullets de README inflados com filler ("Esta seção descreve...", "Em resumo...").

## Escopo do projeto

**Dentro do escopo:**
- Algoritmos cognitivos (decay, activation, consolidation, recall)
- Otimização da pipeline MCP / SQLite / embeddings
- Novos MCP tools que estendam o modelo de memória
- Skills para clientes MCP (Claude Code, etc.)
- CLI ergonomics
- Performance / cobertura / qualidade de teste
- Documentação técnica e de uso

**Fora do escopo:**
- UI web ou desktop
- Sync em nuvem (brainiac é local-first por design)
- App mobile
- Suporte a outros LLMs como backend (brainiac é client-agnostic via MCP — outros clientes podem se conectar, mas a *infra* é a do projeto)
- Plugins que tragam dependências pesadas (DBs externos, frameworks ML grandes)

Quando em dúvida, abra uma issue **antes** de implementar.

---

## Reconhecimento

Contribuições significativas serão listadas no `CHANGELOG.md` e (eventualmente) em uma seção `CONTRIBUTORS.md`.

Obrigado por melhorar o brainiac.
