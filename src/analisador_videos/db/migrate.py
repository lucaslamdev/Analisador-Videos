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
    add_column("events", "end_time_raw_sec", "end_time_raw_sec REAL")
    add_column("events", "interval_start_snapshot_path", "interval_start_snapshot_path TEXT")
    add_column("events", "interval_start_thumbnail_path", "interval_start_thumbnail_path TEXT")
    add_column("events", "interval_end_snapshot_path", "interval_end_snapshot_path TEXT")
    add_column("events", "interval_end_thumbnail_path", "interval_end_thumbnail_path TEXT")
    add_column("events", "clip_annotated_path", "clip_annotated_path TEXT")
    add_column("events", "clip_annotated_sensitive_path", "clip_annotated_sensitive_path TEXT")
    add_column("jobs", "parent_job_id", "parent_job_id TEXT")
    add_column("jobs", "analysis_version", "analysis_version INTEGER DEFAULT 1")
    add_column("batches", "parent_batch_id", "parent_batch_id INTEGER")
    add_column("batches", "analysis_version", "analysis_version INTEGER DEFAULT 1")

    def ensure_index(name: str, table: str, columns: str) -> None:
        with eng.begin() as conn:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})"))

    ensure_index("ix_events_video_id", "events", "video_id")
    ensure_index("ix_events_class_name", "events", "class_name")
    ensure_index("ix_events_start_time_sec", "events", "start_time_sec")
    ensure_index("ix_events_video_id_start_time_sec", "events", "video_id, start_time_sec")
    ensure_index("ix_jobs_batch_id", "jobs", "batch_id")
    ensure_index("ix_jobs_status", "jobs", "status")
    ensure_index("ix_jobs_video_id", "jobs", "video_id")
    ensure_index("ix_jobs_batch_id_created_at", "jobs", "batch_id, created_at")
