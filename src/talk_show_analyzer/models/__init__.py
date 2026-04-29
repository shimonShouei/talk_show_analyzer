"""SQLAlchemy ORM models for talk show analysis."""

from datetime import datetime
from typing import List

from sqlalchemy import (
    String,
    Float,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Station(Base):
    """Radio station metadata."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    stream_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Relationships
    episodes: Mapped[List["Episode"]] = relationship(
        "Episode", back_populates="station", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Station {self.name}>"


class Episode(Base):
    """Recording session (one episode per station per day)."""

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    audio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="he")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending/analyzed/failed

    # Relationships
    station: Mapped["Station"] = relationship(
        "Station", back_populates="episodes"
    )
    segments: Mapped[List["Segment"]] = relationship(
        "Segment", back_populates="episode", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[List["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="episode", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_episode_station_recorded", "station_id", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<Episode station={self.station_id} at {self.recorded_at}>"


class Segment(Base):
    """Content segment within an episode."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    episode: Mapped["Episode"] = relationship("Episode", back_populates="segments")
    topics: Mapped[List["Topic"]] = relationship(
        "Topic", back_populates="segment", cascade="all, delete-orphan"
    )
    sentiments: Mapped[List["SentimentResult"]] = relationship(
        "SentimentResult", back_populates="segment", cascade="all, delete-orphan"
    )
    guest_appearances: Mapped[List["GuestAppearance"]] = relationship(
        "GuestAppearance", back_populates="segment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_segment_episode_type", "episode_id", "type"),
    )

    def __repr__(self) -> str:
        return f"<Segment {self.type} {self.start:.0f}s-{self.end:.0f}s>"


class Topic(Base):
    """Topic extracted from a segment."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"), nullable=False)
    name_he: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    summary_he: Mapped[str] = mapped_column(Text, nullable=False)
    summary_en: Mapped[str] = mapped_column(Text, nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    segment: Mapped["Segment"] = relationship("Segment", back_populates="topics")
    sentiments: Mapped[List["SentimentResult"]] = relationship(
        "SentimentResult", back_populates="topic", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_topic_segment_category", "segment_id", "category"),
    )

    def __repr__(self) -> str:
        return f"<Topic {self.name_en}>"


class Guest(Base):
    """Guest (person) who appeared in episodes."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    appearances: Mapped[List["GuestAppearance"]] = relationship(
        "GuestAppearance", back_populates="guest", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_guest_name_en", "name_en"),
    )

    def __repr__(self) -> str:
        return f"<Guest {self.name_en}>"


class GuestAppearance(Base):
    """Guest appearance in a segment (many-to-many)."""

    __tablename__ = "guest_appearances"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"), nullable=False)
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    guest: Mapped["Guest"] = relationship("Guest", back_populates="appearances")
    segment: Mapped["Segment"] = relationship("Segment", back_populates="guest_appearances")

    __table_args__ = (
        Index("idx_guest_appearance_segment", "segment_id", "guest_id"),
    )

    def __repr__(self) -> str:
        return f"<GuestAppearance guest={self.guest_id} in segment={self.segment_id}>"


class SentimentResult(Base):
    """Sentiment analysis result for a speaker on a topic."""

    __tablename__ = "sentiment_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    tone: Mapped[str] = mapped_column(String(50), nullable=False)
    quotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Relationships
    segment: Mapped["Segment"] = relationship("Segment", back_populates="sentiments")
    topic: Mapped["Topic"] = relationship("Topic", back_populates="sentiments")

    __table_args__ = (
        Index("idx_sentiment_topic", "topic_id"),
        Index("idx_sentiment_speaker", "speaker_label"),
    )

    def __repr__(self) -> str:
        return f"<Sentiment segment={self.segment_id} topic={self.topic_id} score={self.score:.2f}>"


class PipelineRun(Base):
    """Pipeline execution tracking for checkpointing and recovery."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pending/running/done/failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    episode: Mapped["Episode"] = relationship("Episode", back_populates="pipeline_runs")

    __table_args__ = (
        Index("idx_pipeline_run_episode_step", "episode_id", "step"),
    )

    def __repr__(self) -> str:
        return f"<PipelineRun episode={self.episode_id} step={self.step} status={self.status}>"


__all__ = [
    "Base",
    "Station",
    "Episode",
    "Segment",
    "Topic",
    "Guest",
    "GuestAppearance",
    "SentimentResult",
    "PipelineRun",
]
