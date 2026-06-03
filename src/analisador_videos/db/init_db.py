from analisador_videos.db.database import engine, init_engine
from analisador_videos.db.migrate import run_migrations
from analisador_videos.db.models import Base


def create_tables() -> None:
    if engine is None:
        init_engine()
    from analisador_videos.db import database

    assert database.engine is not None
    Base.metadata.create_all(bind=database.engine)
    run_migrations()
