"""Store analysis results to PostgreSQL."""

from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.analysis.topics import TopicAnalysis
from talk_show_analyzer.analysis.guests import GuestAnalysis
from talk_show_analyzer.analysis.sentiment import SentimentAnalysis
from talk_show_analyzer.models import (
    Episode,
    Segment as SegmentModel,
    Topic as TopicModel,
    Guest,
    GuestAppearance,
    SentimentResult,
)


def store_episode_results(
    session: Session,
    episode: Episode,
    segments: list[Segment],
    topic_analyses: list[TopicAnalysis],
    guest_analyses: list[GuestAnalysis],
    sentiment_analyses: list[SentimentAnalysis],
    ads_count: int,
    ads_percentage: float,
) -> None:
    """
    Store all analysis results to database.

    Args:
        session: SQLAlchemy session
        episode: Episode model instance
        segments: Segmentation results
        topic_analyses: Topic extraction results
        guest_analyses: Guest identification results
        sentiment_analyses: Sentiment analysis results
        ads_count: Number of ad segments
        ads_percentage: Ad time percentage
    """
    logger.info(f"Storing results for episode {episode.id}")

    # Store segments (use list + index mapping since Segment dataclass isn't hashable)
    segment_models = []
    segment_to_model = {}  # Map by (start, end) tuple instead of object
    for i, seg in enumerate(segments):
        segment_model = SegmentModel(
            episode_id=episode.id,
            type=seg.type,
            start=seg.start,
            end=seg.end,
            summary=seg.summary,
        )
        session.add(segment_model)
        session.flush()  # Get the auto-generated ID
        segment_models.append(segment_model)
        segment_to_model[(seg.start, seg.end)] = segment_model
        logger.debug(f"Added segment {segment_model.id}: {seg.type}")

    # Store topics
    topic_models = {}  # Map by (name_en, category) tuple instead of object
    for topic_analysis in topic_analyses:
        seg = topic_analysis.segment
        segment_model = segment_to_model[(seg.start, seg.end)]

        # Main topic
        main_topic_model = TopicModel(
            segment_id=segment_model.id,
            name_he=topic_analysis.main_topic.name_he,
            name_en=topic_analysis.main_topic.name_en,
            category=topic_analysis.main_topic.category,
            summary_he=topic_analysis.main_topic.summary_he,
            summary_en=topic_analysis.main_topic.summary_en,
            is_main=True,
        )
        session.add(main_topic_model)
        session.flush()
        topic_models[(topic_analysis.main_topic.name_en, topic_analysis.main_topic.category)] = main_topic_model
        logger.debug(f"Added main topic {main_topic_model.id}: {topic_analysis.main_topic.name_en}")

        # Subtopics
        for subtopic in topic_analysis.subtopics:
            subtopic_model = TopicModel(
                segment_id=segment_model.id,
                name_he=subtopic.name_he,
                name_en=subtopic.name_en,
                category=subtopic.category,
                summary_he=subtopic.summary_he,
                summary_en=subtopic.summary_en,
                is_main=False,
            )
            session.add(subtopic_model)
            session.flush()
            topic_models[(subtopic.name_en, subtopic.category)] = subtopic_model

    # Store guests (with dedup)
    guest_models = {}
    for guest_analysis in guest_analyses:
        for guest in guest_analysis.guests:
            # Check if guest already exists (by name_en)
            existing = session.query(Guest).filter_by(name_en=guest.name_en).first()
            if existing:
                guest_model = existing
                logger.debug(f"Guest {guest.name_en} already exists (id={guest_model.id})")
            else:
                guest_model = Guest(
                    name_he=guest.name_he,
                    name_en=guest.name_en,
                    title=guest.title,
                    affiliation=guest.affiliation,
                )
                session.add(guest_model)
                session.flush()
                logger.debug(f"Added guest {guest_model.id}: {guest.name_en}")

            guest_models[guest] = guest_model

            # Create appearance record
            seg = guest_analysis.segment
            segment_model = segment_to_model[(seg.start, seg.end)]
            appearance = GuestAppearance(
                guest_id=guest_model.id,
                segment_id=segment_model.id,
                speaker_label=guest.speaker_label,
                confidence=guest.confidence,
            )
            session.add(appearance)

    # Store sentiment
    for sentiment_analysis in sentiment_analyses:
        topic_analysis = sentiment_analysis.topic_analysis
        topic_model = topic_models[(topic_analysis.main_topic.name_en, topic_analysis.main_topic.category)]
        seg = topic_analysis.segment
        segment_model = segment_to_model[(seg.start, seg.end)]

        for sentiment in sentiment_analysis.sentiments:
            sentiment_model = SentimentResult(
                segment_id=segment_model.id,
                topic_id=topic_model.id,
                speaker_label=sentiment.speaker_label,
                score=sentiment.score,
                tone=sentiment.tone,
                quotes=sentiment.quotes,
            )
            session.add(sentiment_model)
            logger.debug(
                f"Added sentiment: {sentiment.topic} score={sentiment.score:.2f}"
            )

    # Update episode status
    episode.status = "analyzed"

    # Commit all changes
    session.commit()
    logger.info(
        f"✓ Stored results for episode {episode.id}: "
        f"{len(segments)} segments, {len(topic_analyses)} topics, "
        f"{sum(len(g.guests) for g in guest_analyses)} guests, "
        f"{sum(len(s.sentiments) for s in sentiment_analyses)} sentiments"
    )
