# Analisador de Vídeos

Sistema de análise inteligente de vídeos MP4 com detecção YOLO11n, tracking ByteTrack, evidências visuais e relatórios forenses.

## Pré-requisitos

- Python 3.12+
- [FFmpeg](https://ffmpeg.org/) no `PATH`
- Opcional: GPU NVIDIA + CUDA para inferência mais rápida

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
```

## Executar

```bash
uvicorn analisador_videos.main:app --reload --app-dir src
```

Abra http://127.0.0.1:8000

## Uso

1. **Upload:** envie MP4 pela página inicial.
2. **Pasta:** coloque vídeos em `incoming/` e clique em *Processar pasta*.
3. **API:** `POST /process` (multipart ou JSON `{"source":"folder"}`).
4. **Status:** `GET /status/{job_id}`.
5. **Eventos:** galeria em `/events` com filtros e supercut por classe.

## Duas máquinas (perfis)

| Perfil | Arquivo exemplo | Jobs | Detecção | Estimativa 72×1h |
|--------|-----------------|------|----------|------------------|
| Intel CPU | `.env.cpu-intel.example` | 2 paralelos | Frame cache FFmpeg + loop YOLO | ~2–3 dias |
| RTX 4060 | `.env.gpu-rtx4060.example` | 1 | `stream=True` + `vid_stride` | ~10–18 h |

```bash
cp .env.cpu-intel.example .env   # ou .env.gpu-rtx4060.example na máquina com GPU
```

`GET /health` retorna `backend`, `device_name` e `max_concurrent_jobs` ativos.

## Lotes

Processar `incoming/` cria um lote `lote{N}-DD-MM-YYYY`. Ver `/lotes/{slug}`, relatório HTML e `GET /lotes/{slug}/supercuts.zip`.

## Configuração (`.env`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `EVENT_MERGE_GAP_SEC` | 3 | Merge de tracks (s) |
| `SAMPLE_FPS` | 1 | 1 frame/s real (CPU e GPU) |
| `CLIP_PADDING_SEC` | 2 | Padding dos clipes |
| `DEVICE` | auto | `auto`, `cpu`, `cuda` |
| `GENERATE_REPORTS_ON_COMPLETE` | false | PDF/CSV/JSON sob demanda |
| `MAX_CONCURRENT_JOBS_CPU` | 2 | Fila no Intel |
| `MAX_CONCURRENT_JOBS_GPU` | 1 | Fila na RTX 4060 |

## Testes

```bash
python -m pytest tests/ -v
```

## Estrutura

- `src/analisador_videos/` — código da aplicação
- `data/` — vídeos, clipes, snapshots, relatórios (gerado em runtime)
- `incoming/` — entrada para lote
- `docs/superpowers/` — spec e plano de implementação
