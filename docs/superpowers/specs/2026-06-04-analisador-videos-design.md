# Design: Sistema de Análise Inteligente de Vídeos (MVP)

**Data:** 2026-06-04  
**Status:** Aprovado em brainstorming  
**Base:** `01_PRODUCT_REQUIREMENTS.md`, `02_TECHNICAL_ARCHITECTURE.md`, `03_IMPLEMENTATION_ROADMAP.md`

---

## 1. Objetivo

Aplicação local para processar vídeos MP4, detectar objetos (YOLO11n + ByteTrack), agrupar eventos com merge híbrido, gerar evidências visuais (snapshots, clipes, supercuts), persistir em SQLite e expor interface web com relatórios forenses (JSON, CSV, PDF).

**Público-alvo:** investigadores, monitoramento, auditoria, segurança patrimonial, análise forense, logística.

---

## 2. Decisões de produto (fechadas)

| Tema | Decisão |
|------|---------|
| Definição de evento | Híbrido: track ByteTrack + merge se reaparecer dentro de `EVENT_MERGE_GAP_SEC` (padrão 3s) com heurística espacial |
| Supercut | A: cronológico completo (automático pós-processamento) + B: por classe sob demanda (UI/API) |
| Entrada de vídeo | Upload web + pasta `VIDEOS_INPUT_DIR` para lote |
| Jobs | Assíncrono padrão (`job_id` + progresso); `?sync=true` para testes/vídeos curtos |
| Interface web | Galeria de eventos, filtros (classe, vídeo, intervalo), detalhe com player, jobs, supercuts |
| Amostragem | `SAMPLE_FPS` configurável (padrão ~2 fps) |
| Clipes | `CLIP_PADDING_SEC` configurável (padrão 2s) |
| Dispositivo IA | `DEVICE=auto\|cpu\|cuda` (padrão auto) |
| Relatórios | Resumo por vídeo + evidências (paths/thumbnails) + metadados forenses (hash, params, modelo) |

**Classes MVP (YOLO):** `person`, `car`, `motorcycle`, `truck`, `bus`, `bicycle`, `backpack`.

---

## 3. Arquitetura

### Abordagem escolhida

**Monólito FastAPI** com worker interno (fila de jobs em SQLite + `asyncio`/thread pool para OpenCV/YOLO/FFmpeg). Evolução futura: processo worker separado sem mudar schema.

### Módulos

| Módulo | Responsabilidade |
|--------|------------------|
| `config` | Variáveis `.env` e defaults |
| `ingest` | Upload, scan de pasta, validação MP4, SHA-256 |
| `pipeline` | Amostragem → YOLO11n → ByteTrack → merge de eventos |
| `media` | Snapshots, clipes (padding), supercuts A/B via FFmpeg |
| `storage` | SQLite: vídeos, tracks, events, jobs, artifacts |
| `reports` | Export JSON, CSV, PDF (A+B+C) |
| `web` | Jinja2 + Bootstrap: dashboard, jobs, galeria, filtros |

### Diagrama

```
┌─────────────┐     upload / folder      ┌──────────────────┐
│  Web (J2)   │ ───────────────────────► │  FastAPI         │
└─────────────┘                          │  routes + jobs   │
       ▲                                 └────────┬─────────┘
       │                                          │
       │  galeria / status                        ▼
       │                                 ┌──────────────────┐
       └─────────────────────────────────│  Pipeline        │
                                         │  sample→yolo→   │
                                         │  track→merge→   │
                                         │  media→reports  │
                                         └────────┬─────────┘
                                                  ▼
                                         ┌──────────────────┐
                                         │  SQLite + data/  │
                                         └──────────────────┘
```

### Stack

- Python 3.12+, FastAPI, OpenCV, FFmpeg, YOLO11n, ByteTrack, SQLite, Jinja2, Bootstrap

### Merge híbrido (MVP)

1. Cada track ByteTrack gera candidato a evento (`class_name`, intervalo temporal, confiança).
2. Ordenar tracks por `start_time_sec`.
3. Se `class_name` igual, gap entre fim do track A e início do B ≤ `EVENT_MERGE_GAP_SEC`, e distância entre centro da bbox final de A e inicial de B ≤ limiar (15% da diagonal do frame no MVP), fundir em um evento com `merged_track_ids: [id_a, id_b, ...]`.

---

## 4. Configuração (`.env`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `EVENT_MERGE_GAP_SEC` | `3` | Janela para reagrupar tracks |
| `SAMPLE_FPS` | `2` | Frames analisados por segundo |
| `CLIP_PADDING_SEC` | `2` | Contexto antes/depois do clipe |
| `DEVICE` | `auto` | `auto`, `cpu`, `cuda` |
| `VIDEOS_INPUT_DIR` | `./incoming` | Pasta para lote |
| `DATA_DIR` | `./data` | Raiz de mídia e DB |
| `CONFIDENCE_THRESHOLD` | `0.5` | Mínimo YOLO |
| `PDF_MAX_THUMBNAILS` | `20` | Limite de thumbs no PDF |

---

## 5. Modelo de dados

### `videos`

- `id`, `filename`, `path`, `sha256`, `duration_sec`, `fps_source`, `width`, `height`, `processed_at`, `status` (`pending` \| `processing` \| `done` \| `failed`)

### `jobs`

- `id` (UUID), `video_id`, `status` (`queued` \| `running` \| `done` \| `failed`), `progress_pct`, `stage` (`ingest` \| `detect` \| `merge` \| `media` \| `reports`), `error_message`, `params_json`, `created_at`, `finished_at`

### `tracks` (pré-merge)

- `id`, `video_id`, `track_id`, `class_name`, `start_frame`, `end_frame`, `start_time_sec`, `end_time_sec`, `avg_confidence`, `bbox_json`

### `events` (pós-merge)

- `id`, `video_id`, `class_name`, `start_time_sec`, `end_time_sec` (com padding nos clipes), `start_time_raw_sec`, `merged_track_ids` (JSON), `avg_confidence`, `snapshot_path`, `clip_path`, `thumbnail_path`

### `artifacts`

- `id`, `video_id`, `type` (`supercut_full` \| `supercut_class` \| `report_json` \| `report_csv` \| `report_pdf`), `class_filter`, `path`

### Layout em disco

```
data/
  videos/
  snapshots/
  clips/
  supercuts/
  reports/
  db.sqlite
```

---

## 6. APIs

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Dashboard |
| POST | `/process` | Upload multipart ou JSON `source: folder` / `paths` |
| POST | `/process?sync=true` | Processamento síncrono |
| GET | `/status/{job_id}` | Progresso e stage |
| GET | `/videos` | Lista de vídeos |
| GET | `/events` | Filtros: `video_id`, `class`, `from`, `to`, paginação |
| GET | `/events/{id}` | Detalhe do evento |
| POST | `/videos/{id}/supercut` | Body opcional `{"class":"person"}` para supercut B |
| GET | `/videos/{id}/reports` | Lista de relatórios |
| GET | `/videos/{id}/reports/{format}` | Download `json` \| `csv` \| `pdf` |

**Assíncrono:** resposta `202` com `job_id` e `video_id`.  
**Reprocessamento:** query `force=true` para ignorar deduplicação por SHA256 (opcional MVP).

---

## 7. Pipeline e progresso

| Stage | % aprox. | Ações |
|-------|----------|--------|
| ingest | 0–10 | Hash, metadados, registrar vídeo |
| detect | 10–60 | Amostragem `SAMPLE_FPS`, YOLO, ByteTrack, gravar tracks |
| merge | 60–70 | Aplicar merge híbrido, gravar events |
| media | 70–90 | Snapshots, clipes (`CLIP_PADDING_SEC`), supercut full (A) |
| reports | 90–100 | JSON, CSV, PDF; registrar artifacts |

Supercut por classe (B): apenas em `POST /videos/{id}/supercut` — remonta clipes existentes.

---

## 8. Interface web (MVP)

- Upload e trigger de pasta/lote
- Lista de jobs com barra de progresso e stage
- Galeria de eventos: thumbnail, classe, timestamp, vídeo origem
- Página de detalhe: snapshot com bbox, player do clipe, tracks fundidos
- Filtros: classe, vídeo, intervalo de tempo
- Botões: baixar relatórios; gerar supercut completo / por classe

---

## 9. Relatórios (A + B + C)

### JSON

Schema versionado: vídeo, `params` usados no job, lista de `events`, `artifacts`, metadados de modelo (nome/versão YOLO).

### CSV

Uma linha por evento: `event_id`, `class_name`, `start_time_sec`, `end_time_sec`, `avg_confidence`, `merged_track_ids`, paths de snapshot/clip.

### PDF

1. **Forense (C):** hash SHA256, datas, resolução, duração, parâmetros (`SAMPLE_FPS`, `EVENT_MERGE_GAP_SEC`, `CLIP_PADDING_SEC`, `DEVICE`), versão do modelo.
2. **Resumo (A):** totais por classe, contagem de eventos, duração processada.
3. **Evidências (B):** até `PDF_MAX_THUMBNAILS` thumbnails com id/classe/horário e referência aos clipes.

---

## 10. Erros e edge cases

| Situação | Comportamento |
|----------|----------------|
| Não-MP4 / corrompido | Job `failed` com mensagem |
| FFmpeg ausente | Falha no startup |
| `DEVICE=cuda` sem GPU | Erro explícito; `auto` usa CPU |
| Zero detecções | `done`, relatórios vazios válidos |
| Mesmo SHA256 | Retornar vídeo existente salvo `force=true` |
| Disco cheio | `failed` em `media` |

Logs por `job_id` (INFO/ERROR).

---

## 11. Testes smoke (MVP)

- Fixture MP4 curto: ≥1 evento esperado
- Merge: dois tracks próximos → 1 evento
- `?sync=true`: job `done`
- Supercut B: arquivo filtrado distinto do full
- PDF: contém hash, params e thumbnail se houver eventos

---

## 12. Roadmap de implementação

| Fase | Entrega |
|------|---------|
| 1 | FastAPI, config, schema SQLite, `data/` |
| 2 | Ingest, pipeline detect/track/merge, jobs assíncronos |
| 3 | Snapshots, clipes com padding |
| 4 | Persistência integrada (events com pipeline) |
| 5 | UI: jobs, galeria, filtros, detalhe |
| 6 | Relatórios JSON, CSV, PDF |
| 7 | Supercut A automático + B sob demanda |

---

## 13. Fora do escopo (MVP)

- Autenticação multiusuário
- Classes customizadas / fine-tuning
- Celery, Redis, deploy cloud
- SPA React
- Detecção de `suitcase`, `cellphone`, `animal` (roadmap futuro do PRD)

---

## 14. Critérios de aceite

- Processar MP4 via upload e pasta
- Detectar pessoas, veículos e mochilas (classes listadas)
- Eventos com merge híbrido configurável
- Snapshots, clipes com padding, supercut full + por classe
- Interface web com galeria e filtros
- Relatórios PDF, CSV e JSON com resumo, evidências e metadados forenses
- Jobs assíncronos com progresso; modo sync para testes
