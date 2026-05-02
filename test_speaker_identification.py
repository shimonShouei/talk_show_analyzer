#!/usr/bin/env python3
"""Test speaker identification module."""

import json
from datetime import datetime
from pathlib import Path
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session, init_db
from talk_show_analyzer.identification import LLMSpeakerIdentifier
from talk_show_analyzer.transcription.transcriber import TranscriptionResult, SpeakerSegment
from talk_show_analyzer.models import Station, Episode, Person, SpeakerIdentity

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def create_sample_transcript() -> TranscriptionResult:
    """Create a sample transcript for testing."""
    segments = [
        SpeakerSegment(
            start=0.0,
            end=10.0,
            speaker="GLOBAL_00",
            text="שלום לכם, שמי דן שיסר ואני מארח את תוכנית הבוקר של 103FM. היום עם אותנו אורח מיוחד"
        ),
        SpeakerSegment(
            start=10.0,
            end=20.0,
            speaker="GLOBAL_01",
            text="שלום, תודה על ההזמנה. שמי יוסי כהן ואני כתב עדכונים במשרד התקשורת"
        ),
        SpeakerSegment(
            start=20.0,
            end=30.0,
            speaker="GLOBAL_00",
            text="יוסי, אתה יכול להגיד לנו על החדשות של היום?"
        ),
        SpeakerSegment(
            start=30.0,
            end=40.0,
            speaker="GLOBAL_01",
            text="כן כמובן. היום יש חדשות חשובות מהעולם הטכנולוגיה"
        ),
        SpeakerSegment(
            start=40.0,
            end=50.0,
            speaker="GLOBAL_00",
            text="מעניין מאוד. אנחנו נדבר על זה לאחר הפסק קצר"
        ),
    ]

    return TranscriptionResult(
        raw_text="שלום לכם... מעניין מאוד",
        language="he",
        duration=50.0,
        word_count=50,
        segments=segments,
    )


def main():
    """Run speaker identification test."""
    logger.info("\n=== SPEAKER IDENTIFICATION TEST ===\n")

    # Initialize database
    logger.info("Initializing database...")
    init_db(settings.database_url)

    # Create test episode
    logger.info("Creating test episode...")
    with get_session() as session:
        station = session.query(Station).filter_by(name="103fm").first()
        if not station:
            station = Station(name="103fm", stream_url="http://test.url")
            session.add(station)
            session.flush()

        episode = Episode(
            station_id=station.id,
            recorded_at=datetime.utcnow(),
            duration=0,
            audio_path="/test/path.mp3",
            language="he",
            word_count=0,
            raw_text="",
            status="pending",
        )
        session.add(episode)
        session.flush()
        episode_id = episode.id

    # Create sample transcript
    logger.info("Creating sample transcript...")
    transcript = create_sample_transcript()

    # Identify speakers
    logger.info("\nIdentifying speakers...\n")
    identifier = LLMSpeakerIdentifier()

    with get_session() as session:
        speaker_identities = identifier.identify_speakers(transcript, episode_id, session)
        session.commit()

    # Display results
    logger.info("\n=== RESULTS ===\n")
    for speaker_label, resolved in speaker_identities.items():
        logger.info(f"{speaker_label}:")
        logger.info(f"  Name (HE): {resolved.name_he}")
        logger.info(f"  Name (EN): {resolved.name_en}")
        logger.info(f"  Role: {resolved.role}")
        logger.info(f"  Confidence: {resolved.confidence:.2f}\n")

    # Check database
    logger.info("=== DATABASE RECORDS ===\n")
    with get_session() as session:
        identities = session.query(SpeakerIdentity).filter_by(episode_id=episode_id).all()
        for identity in identities:
            person_name = identity.person.name_en if identity.person else "Unknown"
            logger.info(
                f"{identity.speaker_label} -> {person_name} "
                f"({identity.role}, {identity.confidence:.2f})"
            )

        persons = session.query(Person).all()
        logger.info(f"\nTotal persons created: {len(persons)}\n")

    logger.info("✓ Test completed successfully")


if __name__ == "__main__":
    main()
