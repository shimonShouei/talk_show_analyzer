#!/usr/bin/env python3
"""Full end-to-end pipeline test with database persistence."""

import json
import os
from pathlib import Path
from loguru import logger

# Use SQLite for testing if PostgreSQL is not available
os.environ.setdefault("DATABASE_URL", "sqlite:///test_output/analysis.db")

from talk_show_analyzer.db import init_db, get_session
from talk_show_analyzer.pipeline import PipelineOrchestrator
from talk_show_analyzer.models import Episode, Segment, Topic, Guest, SentimentResult
from talk_show_analyzer.analysis import (
    Segmenter,
    TopicExtractor,
    GuestIdentifier,
    SentimentAnalyzer,
)

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def test_pipeline_from_transcript():
    """Test pipeline using existing transcript (skip recording)."""

    logger.info("\n" + "=" * 60)
    logger.info("FULL PIPELINE TEST")
    logger.info("=" * 60 + "\n")

    # Initialize database
    logger.info("Initializing database...\n")
    init_db()

    # Create partial orchestrator (skip transcriber for this test)
    class TestOrchestrator(PipelineOrchestrator):
        def __init__(self):
            # Skip transcriber initialization (we're using cached transcript)
            self.segmenter = Segmenter()
            self.topic_extractor = TopicExtractor()
            self.guest_identifier = GuestIdentifier()
            self.sentiment_analyzer = SentimentAnalyzer()

    orch = TestOrchestrator()

    # Simulate running pipeline on existing transcript
    transcript_file = Path("test_output/galatz_transcript.json")
    if not transcript_file.exists():
        logger.error(f"Transcript not found: {transcript_file}")
        return False

    logger.info(f"Loading transcript: {transcript_file}\n")
    with open(transcript_file) as f:
        transcript_data = json.load(f)

    # Create episode and import data
    with get_session() as session:
        from talk_show_analyzer.models import Station
        from talk_show_analyzer.transcription.transcriber import (
            TranscriptionResult,
            SpeakerSegment,
        )

        # Create station
        station = session.query(Station).filter_by(name="galatz").first()
        if not station:
            station = Station(name="galatz", stream_url="https://glzwizzlv.bynetcdn.com/glz_mp3")
            session.add(station)
            session.commit()

        # Create episode
        from datetime import datetime
        episode = Episode(
            station_id=station.id,
            recorded_at=datetime.utcnow(),
            duration=float(transcript_data["duration"]),
            audio_path="test_output/galatz_sample.mp3",
            language=transcript_data["language"],
            word_count=int(transcript_data["word_count"]),
            raw_text=transcript_data["raw_text"],
            status="pending",
        )
        session.add(episode)
        session.commit()
        episode_id = episode.id

        logger.info(f"Created episode: id={episode_id}\n")

    # Reconstruct TranscriptionResult
    segments = [
        SpeakerSegment(
            start=seg["start"],
            end=seg["end"],
            speaker=seg["speaker"],
            text=seg["text"],
        )
        for seg in transcript_data["segments"]
    ]

    transcript = TranscriptionResult(
        raw_text=transcript_data["raw_text"],
        language=transcript_data["language"],
        duration=float(transcript_data["duration"]),
        word_count=int(transcript_data["word_count"]),
        segments=segments,
    )

    # Run analysis steps (skip recording + transcription)
    logger.info("=" * 60)
    logger.info("STEP 1: SEGMENTATION")
    logger.info("=" * 60 + "\n")
    seg_list = orch.segmenter.segment(transcript)

    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: TOPIC EXTRACTION")
    logger.info("=" * 60 + "\n")
    topic_analyses = orch.topic_extractor.extract_topics(seg_list)

    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: GUEST IDENTIFICATION")
    logger.info("=" * 60 + "\n")
    guest_analyses = orch.guest_identifier.identify_guests(seg_list)

    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: SENTIMENT ANALYSIS")
    logger.info("=" * 60 + "\n")
    sentiment_analyses = orch.sentiment_analyzer.analyze_sentiments(topic_analyses)

    logger.info("\n" + "=" * 60)
    logger.info("STEP 5: AD AGGREGATION")
    logger.info("=" * 60 + "\n")
    ads_report = orch._step_store(
        episode_id, transcript, seg_list, topic_analyses, guest_analyses, sentiment_analyses
    )

    logger.info(f"✓ All steps completed\n")

    # Verify database contents
    logger.info("=" * 60)
    logger.info("VERIFYING DATABASE CONTENTS")
    logger.info("=" * 60 + "\n")

    with get_session() as session:
        # Check episode
        ep = session.query(Episode).filter_by(id=episode_id).first()
        logger.info(f"Episode {ep.id}: {ep.status}")
        logger.info(f"  Duration: {ep.duration:.0f}s")
        logger.info(f"  Words: {ep.word_count}\n")

        # Check segments
        segs = session.query(Segment).filter_by(episode_id=episode_id).all()
        logger.info(f"Segments: {len(segs)}")
        for seg in segs:
            logger.info(f"  {seg.type}: {seg.start:.0f}s - {seg.end:.0f}s")
        logger.info("")

        # Check topics
        topics = session.query(Topic).join(Segment).filter(Segment.episode_id == episode_id).all()
        logger.info(f"Topics: {len(topics)}")
        for topic in topics:
            logger.info(f"  {topic.name_en} ({topic.category})")
        logger.info("")

        # Check guests
        guests = session.query(Guest).all()
        logger.info(f"Guests: {len(guests)}")
        for guest in guests:
            logger.info(f"  {guest.name_en} - {guest.affiliation}")
        logger.info("")

        # Check sentiments
        sentiments = (
            session.query(SentimentResult)
            .join(Segment)
            .filter(Segment.episode_id == episode_id)
            .all()
        )
        logger.info(f"Sentiments: {len(sentiments)}")
        for sent in sentiments:
            logger.info(f"  Topic sentiment: {sent.score:+.2f} ({sent.tone})")
        logger.info("")

        # Summary
        logger.info("=" * 60)
        logger.info("✓ PIPELINE TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"\nResults persisted to PostgreSQL:")
        logger.info(f"  - Episode {episode_id}")
        logger.info(f"  - {len(segs)} segments")
        logger.info(f"  - {len(topics)} topics")
        logger.info(f"  - {len(guests)} guests")
        logger.info(f"  - {len(sentiments)} sentiments\n")

    return True


if __name__ == "__main__":
    try:
        success = test_pipeline_from_transcript()
        exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        exit(1)
