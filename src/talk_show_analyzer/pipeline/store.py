"""Store analysis results to database."""

from sqlalchemy.orm import Session
from loguru import logger

from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.analysis.topics import TopicAnalysis
from talk_show_analyzer.analysis.sentiment import SentimentAnalysis
from talk_show_analyzer.models import (
    Episode,
    Segment as SegmentModel,
    Topic as TopicModel,
    SentimentResult,
)


def store_episode_results(
    session: Session,
    episode: Episode,
    segments: list[Segment],
    topic_analyses: list[TopicAnalysis],
    sentiment_analyses: list[SentimentAnalysis],
    ads_count: int,
    ads_percentage: float,
) -> None:
    """
    Store all analysis results to database.

    Speaker identities are written directly by UnifiedSpeakerIdentifier during
    the identify_speakers step and are not re-stored here.
    """
    logger.info(f"Storing results for episode {episode.id}")

    # Store segments (all, including ads — for ad reporting)
    segment_to_model: dict[tuple[float, float], SegmentModel] = {}
    for seg in segments:
        segment_model = SegmentModel(
            episode_id=episode.id,
            type=seg.type,
            start=seg.start,
            end=seg.end,
            summary=seg.summary,
        )
        session.add(segment_model)
        session.flush()
        segment_to_model[(seg.start, seg.end)] = segment_model
        logger.debug(f"Added segment {segment_model.id}: {seg.type}")

    # Store topics (only on content segments)
    topic_models: dict[tuple[str, str], TopicModel] = {}
    for topic_analysis in topic_analyses:
        seg = topic_analysis.segment
        segment_model = segment_to_model.get((seg.start, seg.end))
        if not segment_model:
            continue

        main = topic_analysis.main_topic
        main_model = TopicModel(
            segment_id=segment_model.id,
            name_he=main.name_he,
            name_en=main.name_en,
            category=main.category,
            summary_he=main.summary_he,
            summary_en=main.summary_en,
            is_main=True,
        )
        session.add(main_model)
        session.flush()
        topic_models[(main.name_en, main.category)] = main_model
        logger.debug(f"Added main topic {main_model.id}: {main.name_en}")

        for subtopic in topic_analysis.subtopics:
            sub_model = TopicModel(
                segment_id=segment_model.id,
                name_he=subtopic.name_he,
                name_en=subtopic.name_en,
                category=subtopic.category,
                summary_he=subtopic.summary_he,
                summary_en=subtopic.summary_en,
                is_main=False,
            )
            session.add(sub_model)
            session.flush()
            topic_models[(subtopic.name_en, subtopic.category)] = sub_model

    # Store sentiment
    for sentiment_analysis in sentiment_analyses:
        topic_analysis = sentiment_analysis.topic_analysis
        key = (topic_analysis.main_topic.name_en, topic_analysis.main_topic.category)
        topic_model = topic_models.get(key)
        seg = topic_analysis.segment
        segment_model = segment_to_model.get((seg.start, seg.end))
        if not topic_model or not segment_model:
            continue

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
            logger.debug(f"Added sentiment: {sentiment.topic} score={sentiment.score:.2f}")

    episode.status = "analyzed"
    session.commit()
    logger.info(
        f"✓ Stored results for episode {episode.id}: "
        f"{len(segments)} segments, {len(topic_analyses)} topics, "
        f"{sum(len(s.sentiments) for s in sentiment_analyses)} sentiments"
    )
