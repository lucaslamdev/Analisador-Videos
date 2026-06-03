from sqlalchemy import inspect, text

from analisador_videos.db.database import engine, init_engine


def run_migrations() -> None:
    if engine is None:
        init_engine()
    from analisador_videos.db import database

    assert database.engine is not None
    eng = database.engine
    insp = inspect(eng)

    if not insp.has_table("videos"):
        return

    if not insp.has_table("batches"):
        from analisador_videos.db.models import Batch

        Batch.__table__.create(eng)

    def add_column(table: str, col: str, ddl: str) -> None:
        cols = {c["name"] for c in insp.get_columns(table)}
        if col not in cols:
            with eng.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    add_column("videos", "batch_id", "batch_id INTEGER")
    add_column("jobs", "batch_id", "batch_id INTEGER")
    add_column("jobs", "frames_done", "frames_done INTEGER")
    add_column("jobs", "frames_total", "frames_total INTEGER")
    add_column("events", "bbox_json", "bbox_json TEXT")
    add_column("events", "detection_time_sec", "detection_time_sec REAL")
