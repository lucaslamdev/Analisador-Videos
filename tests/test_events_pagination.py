from fastapi.testclient import TestClient

from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Event, Video
from analisador_videos.main import app


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()


def _make_event(video_id: int, start: float) -> Event:
    return Event(
        video_id=video_id,
        class_name="person",
        start_time_sec=start,
        end_time_sec=start + 1,
        start_time_raw_sec=start,
        merged_track_ids="[]",
        avg_confidence=0.9,
    )


def test_events_page_pagination_web(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        video = Video(filename="a.mp4", path="a", sha256="1", status="done")
        db.add(video)
        db.commit()
        db.refresh(video)
        db.add_all([_make_event(video.id, float(i)) for i in range(5)])
        db.commit()
        vid = video.id

    with TestClient(app) as client:
        page1 = client.get(f"/events?video_id={vid}&page=1&page_size=2")
        page2 = client.get(f"/events?video_id={vid}&page=2&page_size=2")
        tools = client.get(f"/events?video_id={vid}&page=2&page_size=2")

    assert page1.status_code == 200
    assert page2.status_code == 200
    assert "5 evento(s) no total" in page1.text
    assert "exibindo 1–2" in page1.text
    assert "exibindo 3–4" in page2.text
    assert "Página 1 de 3" in page1.text
    assert "Página 2 de 3" in page2.text
    assert "Próxima" in page1.text
    assert "page=2" in page1.text
    assert "Anterior" in page2.text
    assert "Próxima" in page2.text
    assert "Ferramentas do vídeo selecionado" in tools.text
