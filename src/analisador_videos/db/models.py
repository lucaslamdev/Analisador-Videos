from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id"), nullable=True
    )
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    videos: Mapped[list["Video"]] = relationship(back_populates="batch")
    jobs: Mapped[list["Job"]] = relationship(back_populates="batch")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps_source: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    batch: Mapped["Batch | None"] = relationship(back_populates="videos")
    jobs: Mapped[list["Job"]] = relationship(back_populates="video")
    tracks: Mapped[list["Track"]] = relationship(back_populates="video")
    events: Mapped[list["Event"]] = relationship(back_populates="video")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="video")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    frames_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch: Mapped["Batch | None"] = relationship(back_populates="jobs")
    video: Mapped["Video"] = relationship(back_populates="jobs")


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_name: Mapped[str] = mapped_column(String(64), nullable=False)
    start_frame: Mapped[int] = mapped_column(Integer, nullable=False)
    end_frame: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="tracks")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    class_name: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    start_time_raw_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_time_raw_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    detection_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    merged_track_ids: Mapped[str] = mapped_column(Text, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clip_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clip_annotated_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clip_annotated_sensitive_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_start_snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_start_thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_end_snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_end_thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="events")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    class_filter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)

    video: Mapped["Video"] = relationship(back_populates="artifacts")
