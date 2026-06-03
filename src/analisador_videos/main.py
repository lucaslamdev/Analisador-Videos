from contextlib import asynccontextmanager

from fastapi import FastAPI

from analisador_videos.config import settings
from analisador_videos.db.init_db import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "videos").mkdir(exist_ok=True)
    (settings.data_dir / "snapshots").mkdir(exist_ok=True)
    (settings.data_dir / "clips").mkdir(exist_ok=True)
    (settings.data_dir / "supercuts").mkdir(exist_ok=True)
    (settings.data_dir / "reports").mkdir(exist_ok=True)
    create_tables()
    yield


app = FastAPI(title="Analisador de Vídeos", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
