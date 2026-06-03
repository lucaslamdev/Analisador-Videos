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

## Configuração (`.env`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `EVENT_MERGE_GAP_SEC` | 3 | Merge de tracks (s) |
| `SAMPLE_FPS` | 2 | Amostragem para YOLO |
| `CLIP_PADDING_SEC` | 2 | Padding dos clipes |
| `DEVICE` | auto | `auto`, `cpu`, `cuda` |

## Testes

```bash
python -m pytest tests/ -v
```

## Estrutura

- `src/analisador_videos/` — código da aplicação
- `data/` — vídeos, clipes, snapshots, relatórios (gerado em runtime)
- `incoming/` — entrada para lote
- `docs/superpowers/` — spec e plano de implementação
