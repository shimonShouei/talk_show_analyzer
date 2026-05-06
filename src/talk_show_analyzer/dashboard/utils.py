"""Utility functions for dashboard database queries."""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import streamlit as st
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session, joinedload

from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import (
    Episode,
    Station,
    Segment,
    Topic,
    SentimentResult,
    SpeakerIdentity,
    Person,
)


@st.cache_data(ttl=3600)
def get_stations() -> List[Dict]:
    """Get all stations (cached for 1 hour)."""
    with get_session() as session:
        stations = session.query(Station).all()
        return [{"id": s.id, "name": s.name} for s in stations]


def get_date_range(days: int = 30) -> Tuple[datetime, datetime]:
    """Get date range for filtering."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


@st.cache_data(ttl=300)
def get_episodes(
    station_id: int | None = None,
    status: str | None = None,
    days: int = 30,
) -> List[Dict]:
    """Get episodes with optional filters (cached for 5 minutes)."""
    with get_session() as session:
        query = session.query(Episode).order_by(desc(Episode.recorded_at))

        start_date, end_date = get_date_range(days)
        query = query.filter(
            Episode.recorded_at.between(start_date, end_date)
        )

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        if status:
            query = query.filter(Episode.status == status)

        episodes = query.all()
        return [
            {
                "id": e.id,
                "station": e.station.name if e.station else "Unknown",
                "date": e.recorded_at.strftime("%Y-%m-%d %H:%M"),
                "duration": f"{e.duration / 60:.1f} min",
                "word_count": e.word_count,
                "status": e.status,
            }
            for e in episodes
        ]


@st.cache_data(ttl=600)
def get_episode_details(episode_id: int) -> Dict:
    """Get detailed info for a single episode (cached for 10 minutes)."""
    with get_session() as session:
        episode = session.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            return {}

        segment_count = len(episode.segments)
        topic_count = sum(len(seg.topics) for seg in episode.segments)
        # Count identified speakers for this episode
        speaker_count = (
            session.query(SpeakerIdentity)
            .filter(
                SpeakerIdentity.episode_id == episode_id,
                SpeakerIdentity.person_id.isnot(None),
            )
            .count()
        )

        segment_types = {}
        for seg in episode.segments:
            segment_types[seg.type] = segment_types.get(seg.type, 0) + 1

        return {
            "station": episode.station.name,
            "date": episode.recorded_at.isoformat(),
            "duration": episode.duration,
            "word_count": episode.word_count,
            "status": episode.status,
            "segment_count": segment_count,
            "topic_count": topic_count,
            "speaker_count": speaker_count,
            "segment_types": segment_types,
        }


@st.cache_data(ttl=300)
def get_top_guests(station_id: int | None = None, days: int = 30, limit: int = 10) -> List[Dict]:
    """Get most frequently identified speakers across episodes (cached for 5 minutes)."""
    with get_session() as session:
        query = (
            session.query(
                Person.id,
                Person.name_en,
                Person.name_he,
                Person.role,
                func.count(SpeakerIdentity.id).label("appearances"),
            )
            .join(SpeakerIdentity, Person.id == SpeakerIdentity.person_id)
            .join(Episode, SpeakerIdentity.episode_id == Episode.id)
        )

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        query = query.group_by(Person.id).order_by(desc("appearances")).limit(limit)

        persons = query.all()
        return [
            {
                "name": p.name_en,
                "name_he": p.name_he,
                "role": p.role,
                "appearances": p.appearances,
            }
            for p in persons
        ]


@st.cache_data(ttl=300)
def get_topic_trends(station_id: int | None = None, days: int = 30) -> List[Dict]:
    """Get trending topics over time (cached for 5 minutes)."""
    with get_session() as session:
        query = (
            session.query(
                Topic.name_en,
                Topic.name_he,
                Topic.category,
                func.count(Topic.id).label("count"),
                func.avg(SentimentResult.score).label("avg_sentiment"),
            )
            .outerjoin(SentimentResult, Topic.id == SentimentResult.topic_id)
            .join(Segment, Topic.segment_id == Segment.id)
            .join(Episode, Segment.episode_id == Episode.id)
        )

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        query = query.group_by(Topic.id).order_by(desc("count")).limit(20)

        topics = query.all()
        return [
            {
                "topic": t.name_en,
                "topic_he": t.name_he,
                "category": t.category,
                "count": t.count,
                "avg_sentiment": t.avg_sentiment or 0.0,
            }
            for t in topics
        ]


@st.cache_data(ttl=300)
def get_sentiment_stats(station_id: int | None = None, days: int = 30) -> Dict:
    """Get overall sentiment statistics (cached for 5 minutes)."""
    with get_session() as session:
        query = session.query(
            func.avg(SentimentResult.score).label("avg_sentiment"),
            func.min(SentimentResult.score).label("min_sentiment"),
            func.max(SentimentResult.score).label("max_sentiment"),
            func.count(SentimentResult.id).label("total_sentiment_results"),
        ).join(Segment, SentimentResult.segment_id == Segment.id)
        query = query.join(Episode, Segment.episode_id == Episode.id)

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        result = query.first()

        return {
            "avg": result.avg_sentiment or 0.0,
            "min": result.min_sentiment or -1.0,
            "max": result.max_sentiment or 1.0,
            "total": result.total_sentiment_results or 0,
        }


@st.cache_data(ttl=300)
def get_sentiment_by_tone(station_id: int | None = None, days: int = 30) -> List[Dict]:
    """Get sentiment results grouped by tone (cached for 5 minutes)."""
    with get_session() as session:
        query = (
            session.query(
                SentimentResult.tone,
                func.count(SentimentResult.id).label("count"),
                func.avg(SentimentResult.score).label("avg_score"),
            )
            .join(Segment, SentimentResult.segment_id == Segment.id)
            .join(Episode, Segment.episode_id == Episode.id)
        )

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        query = query.group_by(SentimentResult.tone).order_by(desc("count"))

        results = query.all()
        return [
            {
                "tone": r.tone,
                "count": r.count,
                "avg_score": r.avg_score or 0.0,
            }
            for r in results
        ]


@st.cache_data(ttl=300)
def get_episode_conversation(episode_id: int) -> Dict:
    """
    Return transcript lines for an episode with speaker labels resolved to real names.

    Uses speaker_identities to map SPEAKER_NN -> Person name. Falls back to the
    raw diarization label when a speaker was not identified.
    """
    with get_session() as session:
        episode = (
            session.query(Episode)
            .filter(Episode.id == episode_id)
            .first()
        )
        if not episode:
            return {"episode": None, "lines": [], "speakers": {}}

        # Build label -> display name map from speaker_identities
        identities = (
            session.query(SpeakerIdentity)
            .filter(SpeakerIdentity.episode_id == episode_id)
            .all()
        )
        label_to_name: dict[str, str] = {}
        label_to_role: dict[str, str] = {}
        for si in identities:
            display = si.person.name_en if si.person else None
            label_to_name[si.speaker_label] = display or si.speaker_label
            label_to_role[si.speaker_label] = si.role

        # Build segment time ranges for type lookup
        segments = (
            session.query(Segment)
            .filter(Segment.episode_id == episode_id)
            .order_by(Segment.start)
            .all()
        )
        # List of (start, end, type) for quick lookup
        seg_ranges = [(s.start, s.end, s.type) for s in segments]

        def segment_type_at(t: float) -> str:
            for start, end, stype in seg_ranges:
                if start <= t < end:
                    return stype
            return "unknown"

        # Parse raw_text back into lines — stored as space-joined but we have
        # speaker segments in DB via segments table. We use the raw_text which
        # was stored at episode level. Since the full TranscriptionResult is not
        # in the DB (only raw_text blob), we reconstruct from the episode raw_text
        # split approach won't give speakers. Instead expose the DB segment summaries
        # as the structured conversation (actual per-speaker turns are not stored).
        #
        # Note: per-speaker per-utterance turns are NOT currently stored in DB —
        # only segment-level summaries are. The conversation view shows those summaries
        # with identified speaker labels from the segment.speakers field.

        lines = []
        for seg in segments:
            seg_type = seg.type
            speakers_in_seg = []
            # Identify which persons are in this segment via speaker_identities
            # (we check label_to_name for all labels that appear in the segment's timerange).
            # Since segments.speakers is not stored in DB (only in the in-memory Segment dataclass),
            # we approximate by showing the segment summary attributed to known speakers.
            for label, name in label_to_name.items():
                role = label_to_role.get(label, "unknown")
                speakers_in_seg.append({"label": label, "name": name, "role": role})

            lines.append({
                "start": seg.start,
                "end": seg.end,
                "type": seg_type,
                "summary": seg.summary,
                "speakers": speakers_in_seg,
            })

        episode_info = {
            "id": episode.id,
            "station": episode.station.name if episode.station else "Unknown",
            "date": episode.recorded_at.strftime("%Y-%m-%d %H:%M"),
            "duration": episode.duration,
        }

        # Unique identified speakers for the sidebar legend
        speaker_legend = {
            label: {"name": name, "role": label_to_role.get(label, "unknown")}
            for label, name in label_to_name.items()
        }

        return {
            "episode": episode_info,
            "lines": lines,
            "speakers": speaker_legend,
        }


@st.cache_data(ttl=300)
def get_segment_distribution(station_id: int | None = None, days: int = 30) -> Dict:
    """Get distribution of segment types (cached for 5 minutes)."""
    with get_session() as session:
        query = (
            session.query(
                Segment.type,
                func.count(Segment.id).label("count"),
            )
            .join(Episode, Segment.episode_id == Episode.id)
        )

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        query = query.group_by(Segment.type).order_by(desc("count"))

        results = query.all()
        return {r.type: r.count for r in results}
