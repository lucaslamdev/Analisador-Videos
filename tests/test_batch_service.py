from datetime import datetime
from unittest.mock import patch

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.ingest.batch_service import next_batch_slug


@patch("analisador_videos.ingest.batch_service.datetime")
def test_next_batch_slug_sequential(mock_dt, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    mock_dt.now.return_value = datetime(2026, 6, 3, 12, 0, 0)
    init_engine()
    create_tables()
    with database.SessionLocal() as db:
        _, s1 = next_batch_slug(db)
        _, s2 = next_batch_slug(db)
    assert s1 == "lote1-03-06-2026"
    assert s2 == "lote2-03-06-2026"
    assert s1 != s2
