<!-- Obrigado pelo PR! Preencha as seções abaixo. Itens marcados ✏️ devem ser editados; checkboxes devem ser marcados conforme você confirma cada ponto. -->

## Resumo

<!-- ✏️ 1-3 bullets: o QUE muda e o PORQUÊ. -->

-
-

## Tipo de mudança

<!-- ✏️ Marque com [x] o que se aplica. -->

- [ ] 🐛 Bug fix (mudança que corrige um problema sem quebrar comportamento existente)
- [ ] ✨ Feature (mudança que adiciona funcionalidade)
- [ ] 💥 Breaking change (mudança que altera API/comportamento existente)
- [ ] 📖 Docs (apenas documentação)
- [ ] 🧪 Tests (apenas testes)
- [ ] ♻️ Refactor (mudança interna sem alterar comportamento observável)
- [ ] 🔧 Chore (build, CI, deps, config)

## Issue relacionada

<!-- ✏️ Closes #123 / Refs #456. Remova se não houver issue. -->

Closes #

## Como testar

<!-- ✏️ Passos verificáveis para o reviewer reproduzir o cenário. -->

```bash
# exemplo
cd tools/brainiac
.venv/bin/pytest tests/core/test_foo.py -v --no-cov
```

## Checklist

- [ ] Os testes foram escritos **antes** da implementação (TDD: RED → GREEN)
- [ ] Suite completa passa: `pytest --ignore=tests/core/test_embeddings.py --no-cov`
- [ ] Cobertura ≥ 80% no(s) módulo(s) afetado(s) do `core/`
- [ ] Asserções concretas (pin de valor com `pytest.approx`), não tautológicas
- [ ] Nenhuma nova dep pip adicionada (ou justificada na descrição acima)
- [ ] Commit messages seguem `feat(scope):` / `fix(scope):` / etc.
- [ ] README/CHANGELOG atualizados se a mudança afeta a interface do usuário (CLI, MCP tool, config)
- [ ] Para schema changes: migration idempotente em `connect()`

## Notas para o reviewer

<!-- ✏️ Pontos sutis, trade-offs, decisões que merecem atenção. Remova se trivial. -->
