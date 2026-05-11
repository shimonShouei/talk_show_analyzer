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


class Person(Base):
    """Canonical identity (host, guest, or other speaker)."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )  # "host" | "guest" | "caller" | "unknown"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    speaker_identities: Mapped[List["SpeakerIdentity"]] = relationship(
        "SpeakerIdentity", back_populates="person", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_person_name_en", "name_en"),
    )

    def __repr__(self) -> str:
        return f"<Person {self.name_en} ({self.role})>"


class SpeakerIdentity(Base):
    """Resolved (Episode, diarization-cluster) → Person mapping."""

    __tablename__ = "speaker_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    speaker_label: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # GLOBAL_00 etc.
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )  # host | guest | caller | unknown
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unresolved"
    )  # llm | llm_confident | unresolved
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    episode: Mapped["Episode"] = relationship("Episode")
    person: Mapped["Person | None"] = relationship("Person", back_populates="speaker_identities")

    __table_args__ = (
        Index("idx_speaker_identity_episode", "episode_id"),
        Index("idx_speaker_identity_label", "episode_id", "speaker_label"),
    )

    def __repr__(self) -> str:
        person_str = self.person.name_en if self.person else "Unknown"
        return f"<SpeakerIdentity ep={self.episode_id} {self.speaker_label}->{person_str} conf={self.confidence:.2f}>"


class MergedTopic(Base):
    """A topic merged across the show by the Thematic Intelligence pipeline."""

    __tablename__ = "merged_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    topic_id: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "t0"
    merged_title_he: Mapped[str] = mapped_column(String(500), nullable=False)
    merged_title_en: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    thematic_flow_he: Mapped[str] = mapped_column(Text, nullable=False, default="")
    time_spans: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chunk_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Relationships
    episode: Mapped["Episode"] = relationship("Episode")
    entities: Mapped[List["TopicEntity"]] = relationship(
        "TopicEntity", back_populates="merged_topic", cascade="all, delete-orphan"
    )
    hate_speech_incidents: Mapped[List["HateSpeechIncidentORM"]] = relationship(
        "HateSpeechIncidentORM",
        back_populates="merged_topic",
        cascade="all, delete-orphan",
    )
    speaker_insights: Mapped[List["SpeakerInsightORM"]] = relationship(
        "SpeakerInsightORM",
        back_populates="merged_topic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_merged_topic_episode", "episode_id", "topic_id"),
    )

    def __repr__(self) -> str:
        return f"<MergedTopic ep={self.episode_id} {self.topic_id}: {self.merged_title_en}>"


class TopicEntity(Base):
    """A named entity (organization / location / figure) inside a merged topic."""

    __tablename__ = "topic_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    merged_topic_id: Mapped[int] = mapped_column(
        ForeignKey("merged_topics.id"), nullable=False
    )
    name_he: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # organization|location|figure
    mentioned_by: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    merged_topic: Mapped["MergedTopic"] = relationship(
        "MergedTopic", back_populates="entities"
    )

    __table_args__ = (
        Index("idx_topic_entity_topic", "merged_topic_id"),
        Index("idx_topic_entity_type", "type"),
    )

    def __repr__(self) -> str:
        return f"<TopicEntity {self.type}: {self.name_en or self.name_he}>"


class HateSpeechIncidentORM(Base):
    """A single hate-speech / evaluative-talk incident inside a merged topic."""

    __tablename__ = "hate_speech_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    merged_topic_id: Mapped[int] = mapped_column(
        ForeignKey("merged_topics.id"), nullable=False
    )
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    phrase_he: Mapped[str] = mapped_column(String(500), nullable=False)
    context_he: Mapped[str] = mapped_column(Text, nullable=False)
    rationale_en: Mapped[str] = mapped_column(Text, nullable=False, default="")

    merged_topic: Mapped["MergedTopic"] = relationship(
        "MergedTopic", back_populates="hate_speech_incidents"
    )

    __table_args__ = (
        Index("idx_hate_speech_topic_speaker", "merged_topic_id", "speaker_label"),
        Index("idx_hate_speech_level", "level"),
    )

    def __repr__(self) -> str:
        return f"<HateSpeech {self.level} {self.speaker_label} → {self.target}>"


class SpeakerInsightORM(Base):
    """One speaker's stance + opinion summary on one merged topic."""

    __tablename__ = "speaker_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    merged_topic_id: Mapped[int] = mapped_column(
        ForeignKey("merged_topics.id"), nullable=False
    )
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    stance: Mapped[str] = mapped_column(String(50), nullable=False)  # support|oppose|neutral|ambivalent
    summary_of_opinion_he: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_of_opinion_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_quotes_he: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    merged_topic: Mapped["MergedTopic"] = relationship(
        "MergedTopic", back_populates="speaker_insights"
    )

    __table_args__ = (
        Index("idx_speaker_insight_topic_speaker", "merged_topic_id", "speaker_label"),
        Index("idx_speaker_insight_stance", "stance"),
    )

    def __repr__(self) -> str:
        return (
            f"<SpeakerInsight topic={self.merged_topic_id} "
            f"{self.speaker_label} stance={self.stance}>"
        )


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
    "Person",
    "SpeakerIdentity",
    "MergedTopic",
    "TopicEntity",
    "HateSpeechIncidentORM",
    "SpeakerInsightORM",
]
