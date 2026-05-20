---
name: brainiac-housekeep
description: Executa decay + consolidação da memória do brainiac. Use quando o usuário pede manutenção semanal, "fazer housekeeping", "limpar memória", ou "ver o que pode ser promovido/arquivado". Mostra relatório legível e permite agir sobre os resultados.
---

# Brainiac Housekeep

Ciclo semanal de manutenção cognitiva: decay de notas fracas + promoção de working notes candidatas.

## Quando usar

- Usuário pede "housekeeping", "manutenção semanal", "ver memória", "limpar brainiac"
- Início de semana ou após período de uso intenso
- Antes de uma sessão de revisão (para garantir índice limpo)

## Passos

### Fase 1 — Decay

1. **Chamar `tool_decay` via CLI** (usando `brainiac decay --dry-run` primeiro):
   - Verificar quantas notas seriam arquivadas
   - Se o número for surpreendente (>10), pausar e mostrar quais são
   - Confirmar com usuário se deve prosseguir
   - Rodar `brainiac decay` (sem `--dry-run`)

2. **Reportar resultado**:
   ```
   Decay: X notas verificadas, Y atualizadas, Z arquivadas
   Arquivadas: [lista dos ids se Z > 0]
   ```

### Fase 2 — Consolidação

3. **Chamar `consolidate_check()`** via MCP:
   - `consolidate_check()` → lista de candidatos

4. **Se não houver candidatos**: informar e encerrar.

5. **Para cada candidato**, mostrar:
   ```
   📝 {id}
   - Tipo atual: working
   - Acessos: {access_count}
   - Links recebidos: {fan_in}
   - Sugestão: promover para {suggested_type}
   ```

6. **Perguntar ao usuário** para cada candidato:
   - "Promover para semantic? (s/n/episodic)"
   - Se `s` ou `semantic`: chamar `promote_note` via `brainiac consolidate --auto` ou direto no CLI
   - Se `episodic`: promover para episodic
   - Se `n` ou enter: pular

7. **Reportar resultado**:
   ```
   Consolidação: X candidatos, Y promovidos
   ```

### Fase 3 — Relatório final

8. **Chamar `brainiac stats`** (via CLI) para mostrar estado atual da memória.

9. **Sugerir próxima ação** se houver:
   - Notas promovidas sem links → sugerir `/brainiac-capture` para linkagem
   - Muitas notas working sem links → lembrar de criar cross-referências

## Exemplo

```
Usuário: "faz o housekeeping do brainiac"

Você:
→ brainiac decay --dry-run
  [dry-run] decay — checked: 47, updated: 47, archived: 3

"3 notas seriam arquivadas. Prosseguir?"

→ [confirmação] → brainiac decay
  decay — checked: 47, updated: 47, archived: 3

→ consolidate_check()
  2 candidatos: 2026-05-15-ideia-auth, 2026-05-12-refactor-db

"2026-05-15-ideia-auth: 5 acessos, 2 links → promover para semantic? (s/n)"
→ s → brainiac consolidate --auto (ou promote_note direto)

→ brainiac stats
  total notes: 44, semantic: 28, episodic: 12, working: 4, archived: 3

"Housekeeping completo. 3 arquivadas, 1 promovida. Memória ativa: 44 notas."
```

## Não usar quando

- Usuário quer apenas buscar algo (use `/brainiac-recall`)
- Usuário quer criar uma nota (use `/brainiac-capture`)
- Sessão em andamento com muitas notas working recentes — melhor esperar

## Observações

- `decay` é seguro: arquivamento é reversível (notas em `memoryTransfer/archive/`)
- `consolidate` move arquivos — verificar que o destino faz sentido antes de confirmar
- Eventos são registrados em `memoryTransfer/logs/events.jsonl`
