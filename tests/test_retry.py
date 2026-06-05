from analisador_videos.jobs.retry import create_retry_job
from analisador_videos.util.errors import format_job_error
import pytest


def test_format_job_error_includes_traceback():
    try:
        raise RuntimeError("falha de teste")
    except RuntimeError as exc:
        msg = format_job_error(exc)
    assert "RuntimeError" in msg
    assert "falha de teste" in msg
    assert "Traceback" in msg


def test_create_retry_job_not_found():
    from analisador_videos.db import database
    from analisador_videos.db.init_db import create_tables

    database.init_engine()
    create_tables()
    assert database.SessionLocal is not None
    with database.SessionLocal() as db:
        with pytest.raises(ValueError, match="não encontrado"):
            create_retry_job(db, "00000000-0000-0000-0000-000000000000")
