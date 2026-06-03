from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from analisador_videos.api import events, process, status, videos
from analisador_videos.config import settings
from analisador_videos.db.init_db import create_tables
from analisador_videos.web.router import router as web_router

STATIC_DIR = Path(__file__).parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.videos_input_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("videos", "snapshots", "clips", "supercuts", "reports"):
        (settings.data_dir / sub).mkdir(exist_ok=True)
    (settings.data_dir / "snapshots" / "thumbs").mkdir(exist_ok=True)
    create_tables()
    yield


app = FastAPI(title="Analisador de Vídeos", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(web_router)
app.include_router(process.router)
app.include_router(status.router)
app.include_router(events.router)
app.include_router(videos.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/media/{media_path:path}")
def serve_media(media_path: str):
    candidate = Path(media_path)
    if not candidate.is_file():
        candidate = Path.cwd() / media_path
    if not candidate.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    from fastapi.responses import FileResponse

    return FileResponse(candidate)
