# Roadmap MVP — Analisador de Vídeos

Plano em PRs pequenos para evoluir o MVP sem grandes refactors.

## Concluído recentemente

- [x] Reprocessar job individual (`POST /jobs/{id}/reprocess`, modo sensível)
- [x] Lote `incoming/` enfileira jobs em background (UI não bloqueia)
- [x] PDF compacto (PR #2)

## Fase 1 — Operação em lote (prioridade alta)

| Issue | Descrição | PR sugerido |
|-------|-----------|-------------|
| [#3](https://github.com/lucaslamdev/Analisador-Videos/issues/3) | Fila de lote com progresso na página do lote (polling/SSE) | `feat/batch-queue-ui` |
| [#5](https://github.com/lucaslamdev/Analisador-Videos/issues/5) | PDF compacto como padrão na exportação do lote | `feat/batch-pdf-compact-default` |
| [#4](https://github.com/lucaslamdev/Analisador-Videos/issues/4) | Reprocessar job avulso fora do lote (UI `keep_batch=0`) | `feat/reprocess-standalone-ui` |

## Fase 2 — Detecção e qualidade

| Issue | Descrição | PR sugerido |
|-------|-----------|-------------|
| [#6](https://github.com/lucaslamdev/Analisador-Videos/issues/6) | Limiares configuráveis por job na UI (não só sensível on/off) | `feat/detection-tuning-ui` |
| # | Pré-visualização de amostra de frames antes do lote inteiro | `feat/sample-preview` |
| # | Métricas de confiança média por vídeo no relatório do lote | `feat/batch-confidence-stats` |

## Fase 3 — Infra e disco

| Issue | Descrição | PR sugerido |
|-------|-----------|-------------|
| # | Limpeza automática de cache/temp após job concluído | `feat/job-temp-cleanup` |
| [#7](https://github.com/lucaslamdev/Analisador-Videos/issues/7) | Estimativa de disco na UI antes de processar pasta | `feat/disk-estimate-ui` |
| # | Retenção configurável de clipes/snapshots antigos | `feat/media-retention` |

## Fase 4 — Relatórios e exportação

| Issue | Descrição | PR sugerido |
|-------|-----------|-------------|
| # | ZIP do lote incluir PDFs compactos por padrão | `feat/batch-zip-compact` |
| # | Filtro de eventos no relatório HTML/PDF | `feat/report-event-filters` |
| # | Supercut do lote com seleção por classe | `feat/batch-supercut-class` |

## API útil

```http
POST /jobs/{job_id}/reprocess?sensitive=1&keep_batch=1
```

- `sensitive=1`: YOLO com limiares baixos (`annotate_sensitive_*`)
- `keep_batch=0`: job avulso, vídeo sai do lote

## Como contribuir

1. Escolha uma issue da fase atual
2. Branch curta + testes
3. PR com descrição e plano de teste manual
