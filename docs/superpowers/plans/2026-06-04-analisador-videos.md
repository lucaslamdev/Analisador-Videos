# Analisador de Vídeos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar MVP local que processa MP4, detecta objetos (YOLO11n + ByteTrack), funde eventos híbridos, gera evidências e relatórios forenses, com UI web e jobs assíncronos.

**Architecture:** Monólito FastAPI; pipeline pesado em thread pool; SQLite para vídeos, tracks, events, jobs e artifacts; arquivos em `data/`. Spec: `docs/superpowers/specs/2026-06-04-analisador-videos-design.md`.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2.x (SQLite), Ultralytics YOLO11n, OpenCV, FFmpeg (subprocess), Jinja2, Bootstrap 5, ReportLab (PDF), pytest.

---

## Estrutura de arquivos (alvo)

```
requirements.txt
.env.example
pyproject.toml
src/analisador_videos/
  __init__.py
  main.py                 # app FastAPI, lifespan, monta routers
  config.py               # Settings pydantic-settings
  db/
    database.py           # engine, SessionLocal
    models.py             # Video, Job, Track, Event, Artifact
    init_db.py            # create_all
  ingest/
    service.py            # save upload, scan folder, sha256
  pipeline/
    sampler.py            # frame indices por SAMPLE_FPS
    detector.py           # YOLO + tracking
    merger.py             # merge híbrido
    runner.py             # orquestra estágios + progresso
  jobs/
    service.py            # enqueue, run sync/async
  media/
    snapshots.py
    clips.py
    supercut.py
  reports/
    builder.py            # json, csv, pdf
  api/
    process.py
    status.py
    events.py
    videos.py
  web/
    router.py
    templates/base.html, index.html, events.html, event_detail.html, jobs.html
    static/style.css
tests/
  conftest.py
  test_merger.py
  test_config.py
  test_api_process.py
fixtures/
  README.md               # como gerar vídeo de teste
```

---

### Task 1: Scaffold do projeto e configuração

**Files:**
- Create: `requirements.txt`, `.env.example`, `pyproject.toml`
- Create: `src/analisador_videos/__init__.py`, `src/analisador_videos/config.py`
- Create: `tests/conftest.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from analisador_videos.config import Settings

def test_settings_defaults():
    s = Settings()
    assert s.event_merge_gap_sec == 3.0
    assert s.sample_fps == 2.0
    assert s.clip_padding_sec == 2.0
    assert s.device == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\lucas\Desktop\Analisador-Videos && python -m pytest tests/test_config.py -v`  
Expected: FAIL — `ModuleNotFoundError: analisador_videos`

- [ ] **Step 3: Write minimal implementation**

`requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.12
pydantic-settings>=2.6.0
sqlalchemy>=2.0.36
opencv-python-headless>=4.10.0
ultralytics>=8.3.0
jinja2>=3.1.4
reportlab>=4.2.0
httpx>=0.28.0
pytest>=8.3.0
pytest-asyncio>=0.24.0
```

`pyproject.toml` — incluir `[tool.pytest.ini_options] pythonpath = ["src"]`.

`src/analisador_videos/config.py`:
```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    videos_input_dir: Path = Path("incoming")
    event_merge_gap_sec: float = 3.0
    sample_fps: float = 2.0
    clip_padding_sec: float = 2.0
    device: str = "auto"
    confidence_threshold: float = 0.5
    pdf_max_thumbnails: int = 20
    merge_spatial_ratio: float = 0.15

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite'}"

settings = Settings()
```

`.env.example` — espelhar variáveis do spec seção 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pyproject.toml .env.example src/ tests/
git commit -m "chore: scaffold projeto e Settings"
```

---

### Task 2: Banco de dados e modelos

**Files:**
- Create: `src/analisador_videos/db/database.py`, `models.py`, `init_db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from sqlalchemy import select
from analisador_videos.db.database import SessionLocal, init_engine
from analisador_videos.db.models import Video
from analisador_videos.config import settings

def test_create_video(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    with SessionLocal() as db:
        v = Video(filename="a.mp4", path=str(tmp_path / "a.mp4"), sha256="abc", status="pending")
        db.add(v)
        db.commit()
        found = db.scalar(select(Video).where(Video.sha256 == "abc"))
        assert found is not None
        assert found.filename == "a.mp4"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement models**

`models.py` — tabelas conforme spec: `Video`, `Job`, `Track`, `Event`, `Artifact` com colunas documentadas em `2026-06-04-analisador-videos-design.md` §5.

`database.py` — `init_engine()`, `SessionLocal`, `get_db()` generator para FastAPI.

`init_db.py` — `def create_tables(): Base.metadata.create_all(bind=engine)`.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: modelos SQLAlchemy e SQLite"
```

---

### Task 3: FastAPI mínimo + lifespan

**Files:**
- Create: `src/analisador_videos/main.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from analisador_videos.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from analisador_videos.config import settings
from analisador_videos.db.init_db import create_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "videos").mkdir(exist_ok=True)
    create_tables()
    yield

app = FastAPI(title="Analisador de Vídeos", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit** — `feat: app FastAPI com health e init db`

---

### Task 4: Ingest (upload, pasta, SHA-256)

**Files:**
- Create: `src/analisador_videos/ingest/service.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Test — hash estável**

```python
import hashlib
from pathlib import Path
from analisador_videos.ingest.service import file_sha256

def test_file_sha256(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello")
    assert file_sha256(p) == hashlib.sha256(b"hello").hexdigest()
```

- [ ] **Step 2–3: Implement**

`file_sha256(path)`, `save_upload(file, dest_dir) -> Path`, `scan_folder(input_dir) -> list[Path]`, `probe_video(path) -> dict` (duration, fps, width, height via `cv2.VideoCapture`).

Rejeitar extensão não `.mp4` com `ValueError`.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: ingest com hash e metadados de vídeo`

---

### Task 5: Merge híbrido de eventos

**Files:**
- Create: `src/analisador_videos/pipeline/merger.py`
- Create: `tests/test_merger.py`

- [ ] **Step 1: Test — dois tracks mesma classe, gap 2s, bbox próxima → 1 evento**

```python
from analisador_videos.pipeline.merger import merge_tracks, TrackSegment

def test_merge_adjacent_tracks():
    tracks = [
        TrackSegment(track_id=1, class_name="person", start_time_sec=0.0, end_time_sec=2.0,
                     end_cx=100, end_cy=100, start_cx=90, start_cy=90, avg_confidence=0.9),
        TrackSegment(track_id=2, class_name="person", start_time_sec=4.0, end_time_sec=6.0,
                     end_cx=105, end_cy=102, start_cx=102, start_cy=101, avg_confidence=0.85),
    ]
    events = merge_tracks(tracks, gap_sec=3.0, frame_diag=500.0, spatial_ratio=0.15)
    assert len(events) == 1
    assert events[0].merged_track_ids == [1, 2]
```

Segundo teste: classes diferentes → 2 eventos.

- [ ] **Step 2–3: Implement `merger.py`**

Dataclass `TrackSegment`, `MergedEvent`; ordenar por `start_time_sec`; fundir conforme spec §3 merge híbrido.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: merge híbrido de tracks`

---

### Task 6: Detector YOLO + tracking

**Files:**
- Create: `src/analisador_videos/pipeline/sampler.py`, `detector.py`
- Create: `tests/test_sampler.py`

- [ ] **Step 1: Test sampler (sem GPU)**

```python
from analisador_videos.pipeline.sampler import frame_indices

def test_frame_indices():
    idx = frame_indices(fps_source=30.0, total_frames=300, sample_fps=2.0)
    assert idx[0] == 0
    assert len(idx) == 20  # 10s * 2fps
```

- [ ] **Step 2–3: Implement**

`sampler.frame_indices(...)` — passo `max(1, int(fps_source / sample_fps))`.

`detector.py`:
- `resolve_device(device: str) -> str`
- `MVP_CLASSES = {"person","car","motorcycle","truck","bus","bicycle","backpack"}`
- `run_detection(video_path, settings) -> list[TrackSegment]` usando `YOLO("yolo11n.pt")` com `model.track(..., persist=True, tracker="bytetrack.yaml")`; agregar por `track_id` + classe; ignorar classes fora do set; filtrar `conf < confidence_threshold`.

- [ ] **Step 4: PASS** (sampler); detector validado manualmente com fixture curto (Task 10).

- [ ] **Step 5: Commit** — `feat: amostragem e detector YOLO11n`

---

### Task 7: Pipeline runner e jobs

**Files:**
- Create: `src/analisador_videos/pipeline/runner.py`, `src/analisador_videos/jobs/service.py`
- Modify: `src/analisador_videos/main.py`

- [ ] **Step 1: Test job enqueue (DB)**

```python
def test_enqueue_job(tmp_path, monkeypatch):
    # criar video row, chamar enqueue_job, assert job status queued
```

- [ ] **Step 2–3: Implement**

`runner.process_video(video_id, job_id, db)` — estágios: ingest meta → detect → merge → persist tracks/events → media (Task 8) → reports (Task 9) → supercut full; atualizar `progress_pct` e `stage` após cada bloco.

`jobs/service.py`:
- `enqueue(video_id) -> job_id` (UUID)
- `run_async(job_id)` — `asyncio.create_task` + `asyncio.to_thread(runner.process_video, ...)`
- `run_sync(job_id)` — thread direta

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: runner de pipeline e fila de jobs`

---

### Task 8: Mídia — snapshots, clipes, supercut

**Files:**
- Create: `src/analisador_videos/media/snapshots.py`, `clips.py`, `supercut.py`
- Modify: `pipeline/runner.py` para chamar mídia

- [ ] **Step 1: Test clip times com padding**

```python
from analisador_videos.media.clips import clip_time_range

def test_clip_padding():
    start, end = clip_time_range(10.0, 20.0, padding_sec=2.0, duration_sec=100.0)
    assert start == 8.0
    assert end == 22.0
```

- [ ] **Step 2–3: Implement**

`snapshots.capture(video_path, time_sec, bbox, out_path)` — OpenCV frame + retângulo.

`clips.extract(video_path, start_sec, end_sec, out_path)` — `ffmpeg -ss -to -c copy` (ou reencode se copy falhar).

`supercut.build(clip_paths, out_path, chronological=True)` — concat demuxer `filelist.txt`.

Integrar no runner: por evento gerar snapshot, thumbnail (resize 320px), clipe; ao fim `supercut_full`.

- [ ] **Step 4: Verificar ffmpeg no PATH** — documentar em README raiz (criar `README.md` mínimo com pré-requisitos).

- [ ] **Step 5: Commit** — `feat: snapshots, clipes e supercut`

---

### Task 9: Relatórios JSON, CSV, PDF

**Files:**
- Create: `src/analisador_videos/reports/builder.py`
- Create: `tests/test_reports.py`

- [ ] **Step 1: Test JSON contém chaves forenses**

```python
def test_build_json_includes_params(sample_video_row, sample_events):
    payload = build_json_report(video, events, job_params={"sample_fps": 2})
    assert "sha256" in payload["video"]
    assert "params" in payload
    assert "events" in payload
```

- [ ] **Step 2–3: Implement**

`build_json_report`, `write_csv_report`, `write_pdf_report` (ReportLab: capa metadados, tabela resumo por classe, grid thumbnails até `pdf_max_thumbnails`).

Registrar rows em `artifacts`.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: relatórios JSON CSV PDF`

---

### Task 10: APIs REST

**Files:**
- Create: `src/analisador_videos/api/process.py`, `status.py`, `events.py`, `videos.py`
- Modify: `main.py` — `include_router`

- [ ] **Step 1: Test POST /process sync com mock runner**

```python
def test_process_sync_returns_done(client, monkeypatch):
    monkeypatch.setattr("analisador_videos.jobs.service.run_sync", lambda jid: None)
    # upload tiny mp4 fixture
    r = client.post("/process?sync=true", files={"file": ("t.mp4", b"...", "video/mp4")})
    assert r.status_code in (200, 201)
```

- [ ] **Step 2–3: Implement rotas conforme spec §6**

`POST /process` — multipart file OU JSON `{"source":"folder"}` / `{"paths":[...]}`; dedup SHA256 salvo `force=true`; resposta 202 + `job_id` ou 200 sync.

`GET /status/{job_id}`, `GET /events` (query filters), `GET /events/{id}`, `POST /videos/{id}/supercut`, `GET /videos/{id}/reports/{format}`.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: APIs de processamento, eventos e relatórios`

---

### Task 11: Interface web (Jinja2 + Bootstrap)

**Files:**
- Create: `src/analisador_videos/web/router.py`, templates, `static/style.css`
- Modify: `main.py`

- [ ] **Step 1: Test GET / renderiza**

```python
def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Analisador" in r.text
```

- [ ] **Step 2–3: Templates**

- `index.html` — upload form, link processar pasta, jobs recentes
- `jobs.html` — lista com progresso
- `events.html` — galeria + filtros (class, video_id, from, to)
- `event_detail.html` — snapshot, `<video src=...>`, lista `merged_track_ids`
- Botões: download relatórios, gerar supercut (form POST classe opcional)

Montar `Jinja2Templates(directory=...)` e `APIRouter` sem prefix ou prefix `/`.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** — `feat: interface web MVP`

---

### Task 12: Supercut por classe (B) e polish

**Files:**
- Modify: `media/supercut.py`, `api/videos.py`, `web/templates`

- [ ] **Step 1: Test supercut filtra por classe**

```python
def test_supercut_by_class_filters_clips(tmp_path, db_session):
    # 2 eventos person, 1 car -> supercut person tem 2 clipes
```

- [ ] **Step 2–3: `POST /videos/{id}/supercut` body `{"class":"person"}`** — não reexecuta YOLO; artifact `supercut_class`.

- [ ] **Step 4: Smoke manual**

Run: `uvicorn analisador_videos.main:app --reload --app-dir src`  
Processar vídeo fixture; abrir galeria; baixar PDF; gerar supercut `person`.

- [ ] **Step 5: Commit** — `feat: supercut por classe e ajustes finais`

---

### Task 13: README e verificação final

**Files:**
- Create: `README.md`

- [ ] **Step 1: Documentar**

Pré-requisitos: Python 3.12+, FFmpeg no PATH, opcional CUDA.  
Comandos: `pip install -r requirements.txt`, `cp .env.example .env`, `uvicorn ...`.  
Estrutura `data/` e `incoming/`.

- [ ] **Step 2: Run suite completa**

Run: `python -m pytest tests/ -v`  
Expected: all PASS (pular testes GPU se marcados `@pytest.mark.gpu`).

- [ ] **Step 3: Commit** — `docs: README com setup e uso`

---

## Spec coverage (self-review)

| Requisito spec | Task |
|----------------|------|
| Evento híbrido + `EVENT_MERGE_GAP_SEC` | 5, 6, 7 |
| Supercut A + B | 8, 12 |
| Upload + pasta | 4, 10, 11 |
| Jobs async + sync | 7, 10 |
| UI galeria + filtros | 11 |
| `SAMPLE_FPS`, `CLIP_PADDING_SEC`, `DEVICE` | 1, 6, 8 |
| Relatórios A+B+C | 9 |
| APIs spec §6 | 10 |
| Smoke tests spec §11 | 5, 9, 10, 12 |
| Critérios de aceite §14 | 12, 13 |

**Placeholder scan:** nenhum TBD.

---

## Ordem de execução recomendada

Tasks **1 → 13** sequenciais. Tasks 8–9 podem começar com stubs no runner até estarem prontas, mas commit final do runner só após 8–9 integrados.

---

## Comandos úteis

```bash
# Instalar
pip install -r requirements.txt

# Testes
python -m pytest tests/ -v

# Servidor dev
uvicorn analisador_videos.main:app --reload --app-dir src
```
