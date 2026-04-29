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
    Guest,
    GuestAppearance,
    SentimentResult,
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
        guest_count = sum(len(seg.guest_appearances) for seg in episode.segments)

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
            "guest_count": guest_count,
            "segment_types": segment_types,
        }


@st.cache_data(ttl=300)
def get_top_guests(station_id: int | None = None, days: int = 30, limit: int = 10) -> List[Dict]:
    """Get most frequently appearing guests (cached for 5 minutes)."""
    with get_session() as session:
        query = (
            session.query(
                Guest.id,
                Guest.name_en,
                Guest.name_he,
                Guest.title,
                func.count(GuestAppearance.id).label("appearances"),
            )
            .join(GuestAppearance, Guest.id == GuestAppearance.guest_id)
            .join(Segment, GuestAppearance.segment_id == Segment.id)
            .join(Episode, Segment.episode_id == Episode.id)
        )

        start_date, end_date = get_date_range(days)
        query = query.filter(Episode.recorded_at.between(start_date, end_date))

        if station_id:
            query = query.filter(Episode.station_id == station_id)

        query = query.group_by(Guest.id).order_by(desc("appearances")).limit(limit)

        guests = query.all()
        return [
            {
                "name": g.name_en,
                "name_he": g.name_he,
                "title": g.title,
                "appearances": g.appearances,
            }
            for g in guests
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
