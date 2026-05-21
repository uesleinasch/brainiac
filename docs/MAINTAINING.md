# Guia de Manutenção

Este documento é para mantenedores do brainiac. Cobre configuração do repositório no GitHub, processo de release e operação contínua.

> Para *contribuir* com código, leia [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Sumário

- [Configuração inicial do repo no GitHub](#configuração-inicial-do-repo-no-github)
- [Branch protection rules para `main`](#branch-protection-rules-para-main)
- [Secrets / variáveis de ambiente](#secrets--variáveis-de-ambiente)
- [Processo de release](#processo-de-release)
- [Triagem de issues](#triagem-de-issues)
- [Revisão de pull requests](#revisão-de-pull-requests)
- [Atualizações de dependências](#atualizações-de-dependências)

---

## Configuração inicial do repo no GitHub

Após `git push origin main` pela primeira vez, configure no painel web do GitHub:

### Settings → General

- ✅ **Default branch:** `main`
- ✅ **Features:** habilitar `Issues`, `Discussions` (opcional), `Projects` (opcional). Desabilitar `Wikis`.
- ✅ **Pull Requests:**
  - ✅ Allow merge commits (somente para merges de mantenedor; o padrão será squash)
  - ✅ Allow squash merging — **default**
  - ❌ Allow rebase merging (mantém histórico limpo via squash)
  - ✅ Always suggest updating pull request branches
  - ✅ Automatically delete head branches (limpa branches após merge)
- ✅ **Archives:** desabilitar "Include Git LFS objects in archives" (não usamos LFS)

### Settings → Code security

- ✅ Habilitar **Dependabot alerts**
- ✅ Habilitar **Dependabot security updates**
- ✅ Habilitar **Secret scanning** (free para repos públicos)
- ✅ Habilitar **Push protection** para secret scanning

### Settings → Branches

Veja [próxima seção](#branch-protection-rules-para-main).

---

## Branch protection rules para `main`

**Settings → Branches → Add branch protection rule**

| Configuração | Valor recomendado | Por quê |
|---|---|---|
| Branch name pattern | `main` | Aplica à branch principal |
| **Require a pull request before merging** | ✅ habilitado | Força fluxo via PR |
| → Require approvals | `1` | Pelo menos 1 review (até em projetos solo, força segunda leitura) |
| → Dismiss stale pull request approvals when new commits are pushed | ✅ | Approve antigo não vale após push |
| → Require review from Code Owners | ✅ | Honra `CODEOWNERS` |
| → Require approval of the most recent reviewable push | ✅ | Re-review após mudanças |
| **Require status checks to pass before merging** | ✅ habilitado | CI obrigatório |
| → Require branches to be up to date before merging | ✅ | Garante que rebase foi feito |
| → Status checks: | `tests (py3.11)`, `tests (py3.12)`, `lint (ruff)`, `install-script syntax` | Lista as jobs do `.github/workflows/ci.yml` |
| **Require conversation resolution before merging** | ✅ | Sem comments soltos |
| **Require signed commits** | opcional | Segurança extra; impõe GPG/SSH signing |
| **Require linear history** | ✅ | Sem merge commits — força squash ou rebase |
| **Require deployments to succeed before merging** | ❌ | Não temos deploy ainda |
| **Lock branch** | ❌ | Não, queremos PRs |
| **Do not allow bypassing the above settings** | ✅ | Inclui o próprio admin (você) |
| **Allow force pushes** | ❌ **NUNCA em `main`** | Reescrever histórico público é destrutivo |
| **Allow deletions** | ❌ | `main` não pode ser deletada |

### Workflow resultante

Após essas regras:
- Nem o admin pode `git push main` direto
- Toda mudança precisa de PR → review → CI verde → squash merge
- Histórico de `main` fica linear e auditável

---

## Secrets / variáveis de ambiente

Atualmente o CI **não precisa de nenhum secret** (testes rodam offline, sem deploy).

Se no futuro adicionarmos:
- Publicação no PyPI → adicionar `PYPI_API_TOKEN` em `Settings → Secrets and variables → Actions`
- Coverage upload (Codecov, Coveralls) → adicionar o token correspondente

---

## Processo de release

Releases seguem [Semantic Versioning](https://semver.org/lang/pt-BR/) e o formato do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

### Pré-release checklist

- [ ] `pytest --ignore=tests/core/test_embeddings.py --no-cov` passa em todas as versões da matrix (CI verde em `main`)
- [ ] `CHANGELOG.md` movido de `[Não lançado]` para nova versão com data
- [ ] Versão atualizada em `tools/brainiac/pyproject.toml`
- [ ] README e docs sem `TODO` ou placeholders
- [ ] Test manual do instalador em VM/container limpo:
  ```bash
  docker run -it --rm ubuntu:24.04 bash
  apt update && apt install -y git python3 python3-venv curl
  curl -fsSL https://raw.githubusercontent.com/uesleinasch/brainiac/main/scripts/install.sh | bash
  ```

### Tag + GitHub release

```bash
# Atualizar pyproject.toml: version = "0.2.0"
# Atualizar CHANGELOG.md: mover [Não lançado] → [0.2.0] — YYYY-MM-DD
git add CHANGELOG.md tools/brainiac/pyproject.toml
git commit -m "chore(release): v0.2.0"

# Criar PR, esperar CI, merge

# Após merge em main:
git pull
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

Criar a release no GitHub:
```bash
gh release create v0.2.0 \
  --title "v0.2.0" \
  --notes-from-tag \
  --verify-tag
```

Ou via Web: **Releases → Draft a new release → Choose v0.2.0 → Generate release notes**.

---

## Triagem de issues

Quando uma issue chega:

1. **Etiqueta** (issue templates já aplicam `bug`, `enhancement`, `question` + `triage`)
2. **Avalie em até 7 dias**:
   - É reproduzível?
   - Está no [escopo](../CONTRIBUTING.md#escopo-do-projeto)?
   - É duplicada?
3. **Resposta inicial** com uma das classificações:
   - `accepted` — vamos resolver, com prioridade implícita
   - `needs-info` — precisa de mais dados (peça reproducer mínimo)
   - `wontfix` — fora do escopo (explique e linkando CONTRIBUTING)
   - `duplicate` — referencie a issue original e feche
4. **Remova a label `triage`** após classificar

### Issues abandonadas

Issues `needs-info` sem resposta por 30 dias podem ser fechadas com label `stale`. Reabra se o reporter responder.

---

## Revisão de pull requests

### Antes de revisar

- CI deve estar verde. Se vermelho, peça pro contribuidor consertar primeiro.
- Confira se o PR template foi preenchido. Se vazio, peça.

### Durante a review

Use os critérios do `CONTRIBUTING.md`:

- TDD foi seguido? (teste antes da implementação no histórico de commits)
- Cobertura está aceitável?
- Asserções concretas?
- Sem deps novas não justificadas?
- Schema changes são idempotentes?
- Docstrings só onde necessário?

Comentários inline são melhores que comentários gerais — facilitam encontrar o contexto.

### Aprovando

- Use **Request changes** apenas para problemas bloqueantes
- Use **Comment** para sugestões
- Use **Approve** quando tudo estiver OK

### Merge

- **Squash and merge** é o padrão (mantém histórico linear)
- Edite a mensagem do squash para refletir o resumo do PR (não a cadeia de commits do contribuidor)
- Delete a branch após merge (configuração automática se habilitada)

---

## Atualizações de dependências

### Manuais

Trimestralmente, verifique upgrades disponíveis:

```bash
cd tools/brainiac
.venv/bin/pip list --outdated
```

Para cada dep não-major, atualize em PR separado e rode a suite. Major bumps precisam de issue de tracking.

### Dependabot

Configurar `.github/dependabot.yml` quando for habilitar updates automáticos. Exemplo mínimo:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/tools/brainiac"
    schedule:
      interval: "monthly"
    open-pull-requests-limit: 5

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
```

---

## Documentos relacionados

- [CONTRIBUTING.md](../CONTRIBUTING.md) — guia de contribuição
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
- [SECURITY.md](../SECURITY.md) — política de segurança
- [CHANGELOG.md](../CHANGELOG.md)
- [.github/CODEOWNERS](../.github/CODEOWNERS)
- [.github/workflows/ci.yml](../.github/workflows/ci.yml)
