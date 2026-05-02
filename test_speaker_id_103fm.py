#!/usr/bin/env python3
"""Test speaker identification on real 103FM transcript."""

import json
from pathlib import Path
from datetime import datetime
from loguru import logger

from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session, init_db
from talk_show_analyzer.identification import LLMSpeakerIdentifier
from talk_show_analyzer.transcription.transcriber import TranscriptionResult, SpeakerSegment
from talk_show_analyzer.models import Station, Episode, Person, SpeakerIdentity

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def load_transcript(json_path: str) -> TranscriptionResult:
    """Load transcript from JSON file."""
    with open(json_path) as f:
        data = json.load(f)

    segments = [
        SpeakerSegment(
            start=seg["start"],
            end=seg["end"],
            speaker=seg["speaker"],
            text=seg["text"],
        )
        for seg in data["segments"]
    ]

    return TranscriptionResult(
        raw_text=data["raw_text"],
        language=data["language"],
        duration=data["duration"],
        word_count=data["word_count"],
        segments=segments,
    )


def main():
    """Test speaker identification on 103FM transcript."""
    logger.info("\n=== 103FM SPEAKER IDENTIFICATION TEST ===\n")

    # Load transcript
    transcript_path = Path("data/103fm/103fm_2026-04-30T07:55:50.803741_transcript.json")
    if not transcript_path.exists():
        logger.error(f"Transcript not found: {transcript_path}")
        return

    logger.info(f"Loading transcript from {transcript_path}...")
    transcript = load_transcript(str(transcript_path))
    logger.info(f"  Language: {transcript.language}")
    logger.info(f"  Duration: {transcript.duration}s ({transcript.duration/60:.1f}m)")
    logger.info(f"  Segments: {len(transcript.segments)}")
    logger.info(f"  Unique speakers: {len(set(s.speaker for s in transcript.segments))}\n")

    # Initialize database
    logger.info("Initializing database...")
    init_db(settings.database_url)

    # Create episode
    logger.info("Creating episode...")
    with get_session() as session:
        station = session.query(Station).filter_by(name="103fm").first()
        if not station:
            station = Station(name="103fm", stream_url="http://103fm.maariv.co.il")
            session.add(station)
            session.flush()

        episode = Episode(
            station_id=station.id,
            recorded_at=datetime.utcnow(),
            duration=transcript.duration,
            audio_path=str(transcript_path),
            language=transcript.language,
            word_count=transcript.word_count,
            raw_text=transcript.raw_text[:500],
            status="pending",
        )
        session.add(episode)
        session.flush()
        episode_id = episode.id

    # Identify speakers
    logger.info(f"\nIdentifying {len(set(s.speaker for s in transcript.segments))} speakers...\n")
    identifier = LLMSpeakerIdentifier()

    with get_session() as session:
        speaker_identities = identifier.identify_speakers(transcript, episode_id, session)
        session.commit()

    # Display results
    logger.info("\n=== IDENTIFIED SPEAKERS ===\n")
    sorted_speakers = sorted(speaker_identities.items(), key=lambda x: x[1].confidence, reverse=True)

    for speaker_label, resolved in sorted_speakers:
        confidence_bar = "█" * int(resolved.confidence * 10) + "░" * (10 - int(resolved.confidence * 10))
        logger.info(
            f"{speaker_label:<15} {resolved.name_en:<20} ({resolved.role:<10}) "
            f"[{confidence_bar}] {resolved.confidence:.2f}"
        )

    # Database summary
    logger.info("\n=== DATABASE SUMMARY ===\n")
    with get_session() as session:
        identities = session.query(SpeakerIdentity).filter_by(episode_id=episode_id).all()

        # Count by role
        role_counts = {}
        for identity in identities:
            role = identity.role
            role_counts[role] = role_counts.get(role, 0) + 1

        logger.info("Speakers by role:")
        for role, count in sorted(role_counts.items()):
            logger.info(f"  {role}: {count}")

        # Count identified vs unresolved
        identified = sum(1 for i in identities if i.person_id is not None)
        unresolved = len(identities) - identified
        logger.info(f"\nIdentified: {identified}")
        logger.info(f"Unresolved: {unresolved}\n")

        # List persons created
        persons = session.query(Person).all()
        if persons:
            logger.info(f"Created {len(persons)} Person records:")
            for person in sorted(persons, key=lambda p: p.name_en):
                logger.info(f"  - {person.name_en} ({person.role})")

    logger.info("\n✓ Test completed")


if __name__ == "__main__":
    main()
