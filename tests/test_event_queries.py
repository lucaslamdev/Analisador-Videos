from analisador_videos.config import settings
from analisador_videos.db import database
from analisador_videos.db.database import init_engine
from analisador_videos.db.init_db import create_tables
from analisador_videos.db.models import Batch, Event, Video
from analisador_videos.web.event_queries import (
    DEFAULT_EVENTS_PAGE_SIZE,
    build_events_query_string,
    count_events_by_class_label,
    count_filtered_events,
    distinct_event_class_names,
    normalize_events_pagination,
)


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    init_engine()
    create_tables()


def _make_event(video_id: int, class_name: str, start: float) -> Event:
    return Event(
        video_id=video_id,
        class_name=class_name,
        start_time_sec=start,
        end_time_sec=start + 1,
        start_time_raw_sec=start,
        merged_track_ids="[]",
        avg_confidence=0.9,
    )


def test_distinct_event_class_names(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        v = Video(filename="a.mp4", path="a", sha256="1", status="done")
        db.add(v)
        db.commit()
        db.refresh(v)
        db.add_all(
            [
                _make_event(v.id, "car", 0),
                _make_event(v.id, "person", 2),
                _make_event(v.id, "car", 4),
            ]
        )
        db.commit()

        assert distinct_event_class_names(db) == ["car", "person"]


def test_count_events_by_class_label(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        batch = Batch(slug="lote1-01-01-2026", sequence_num=1)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        v1 = Video(
            filename="a.mp4",
            path="a",
            sha256="1",
            batch_id=batch.id,
            status="done",
        )
        v2 = Video(
            filename="b.mp4",
            path="b",
            sha256="2",
            batch_id=batch.id,
            status="done",
        )
        db.add_all([v1, v2])
        db.commit()
        db.refresh(v1)
        db.refresh(v2)
        db.add_all(
            [
                _make_event(v1.id, "person", 0),
                _make_event(v1.id, "person", 2),
                _make_event(v1.id, "car", 4),
                _make_event(v2.id, "car", 0),
            ]
        )
        db.commit()

        counts = count_events_by_class_label(db, video_ids=[v1.id, v2.id])
        assert counts == {"Pessoa": 2, "Carro": 2}

        assert count_events_by_class_label(db, video_ids=[]) == {}

        other = Video(filename="c.mp4", path="c", sha256="3", status="done")
        db.add(other)
        db.commit()
        db.refresh(other)
        assert count_events_by_class_label(db, video_ids=[other.id]) == {}


def test_count_filtered_events_with_filters(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.SessionLocal() as db:
        batch = Batch(slug="lote1-01-01-2026", sequence_num=1)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        v1 = Video(
            filename="a.mp4",
            path="a",
            sha256="1",
            batch_id=batch.id,
            status="done",
        )
        v2 = Video(filename="b.mp4", path="b", sha256="2", status="done")
        db.add_all([v1, v2])
        db.commit()
        db.refresh(v1)
        db.refresh(v2)
        db.add_all(
            [
                _make_event(v1.id, "person", 0),
                _make_event(v1.id, "car", 2),
                _make_event(v2.id, "person", 0),
            ]
        )
        db.commit()

        assert (
            count_filtered_events(
                db,
                batch_slugs=["lote1-01-01-2026"],
                video_ids=[],
                class_names=[],
            )
            == 2
        )
        assert (
            count_filtered_events(
                db,
                batch_slugs=[],
                video_ids=[v1.id],
                class_names=["person"],
            )
            == 1
        )
        assert (
            count_filtered_events(
                db,
                batch_slugs=["inexistente"],
                video_ids=[],
                class_names=[],
            )
            == 0
        )


def test_normalize_events_pagination_clamps_page(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    p = normalize_events_pagination(99, 10, 25, returned_count=5)
    assert p.page == 3
    assert p.offset == 20
    assert p.total_pages == 3
    assert p.has_prev is True
    assert p.has_next is False
    assert p.range_start == 21
    assert p.range_end == 25

    empty = normalize_events_pagination(5, DEFAULT_EVENTS_PAGE_SIZE, 0)
    assert empty.page == 1
    assert empty.total_pages == 1
    assert empty.range_start == 0
    assert empty.range_end == 0


def test_build_events_query_string_preserves_filters():
    qs = build_events_query_string(
        page=2,
        page_size=30,
        video_ids=[1, 2],
        batch_slugs=["lote-a"],
        class_names=["person"],
    )
    assert "page=2" in qs
    assert "page_size=30" in qs
    assert "video_id=1" in qs
    assert "video_id=2" in qs
    assert "batch=lote-a" in qs
    assert "class=person" in qs

    default_qs = build_events_query_string(
        page=1,
        page_size=DEFAULT_EVENTS_PAGE_SIZE,
        video_ids=[7],
        batch_slugs=[],
        class_names=[],
    )
    assert "page=" not in default_qs
    assert "page_size=" not in default_qs
    assert default_qs == "video_id=7"
