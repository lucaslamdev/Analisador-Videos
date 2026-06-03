from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from analisador_videos.config import settings
from analisador_videos.db.models import Base

engine = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine() -> None:
    global engine, SessionLocal
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.sqlite_url,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
