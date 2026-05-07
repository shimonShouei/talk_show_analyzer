#!/usr/bin/env python3
"""Test speaker identification on a real stored 103FM transcript.

The transcript JSON does NOT preserve pyannote embeddings, so the acoustic-merge
step short-circuits to identity (pass-through). This test exercises:
  - the new content_segments argument flow
  - naming-moment extraction on real Hebrew text
  - chain-of-thought reasoning + strict confidence persistence
  - per-original-label SpeakerIdentity rows

For full acoustic-merge coverage, use the SLURM job (run_kanbet_10min.slurm) —
it runs the orchestrator with a live transcriber that populates embeddings.

Requires ANTHROPIC_API_KEY. No GPU needed.
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session, init_db
from talk_show_analyzer.identification import UnifiedSpeakerIdentifier
from talk_show_analyzer.models import Episode, Person, SpeakerIdentity, Station
from talk_show_analyzer.transcription.transcriber import (
    SpeakerSegment,
    TranscriptionResult,
)

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def load_transcript(json_path: Path) -> TranscriptionResult:
    with open(json_path) as f:
        data = json.load(f)
    segments = [
        SpeakerSegment(
            start=seg["start"], end=seg["end"], speaker=seg["speaker"], text=seg["text"]
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


def build_single_content_segment(transcript: TranscriptionResult) -> list[Segment]:
    """Treat the whole transcript as one interview segment.

    Real episodes have multiple segments after segmentation, but speaker
    identification only cares about the union of speaker labels in non-ad
    segments — collapsing into one segment exercises the same code path.
    """
    speakers = sorted({s.speaker for s in transcript.segments})
    return [
        Segment(
            type="interview",
            start=0.0,
            end=transcript.duration,
            speakers=speakers,
            summary="Full episode (test).",
            raw_text=transcript.raw_text[:2000],
        )
    ]


def main() -> None:
    logger.info("\n=== 103FM SPEAKER IDENTIFICATION TEST (real transcript) ===\n")

    transcript_path = Path(
        "data/103fm/103fm_2026-04-30T07:55:50.803741_transcript.json"
    )
    if not transcript_path.exists():
        logger.error(f"Transcript not found: {transcript_path}")
        return

    logger.info(f"Loading transcript from {transcript_path}...")
    transcript = load_transcript(transcript_path)
    n_speakers = len({s.speaker for s in transcript.segments})
    logger.info(f"  Language: {transcript.language}")
    logger.info(f"  Duration: {transcript.duration:.0f}s ({transcript.duration / 60:.1f}m)")
    logger.info(f"  Segments: {len(transcript.segments)}")
    logger.info(f"  Unique speakers: {n_speakers}")
    logger.info(
        "  speaker_embeddings: empty (stored JSON omits them — merge will short-circuit)\n"
    )

    init_db(settings.database_url)

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
        session.query(SpeakerIdentity).filter_by(episode_id=episode_id).delete()
        session.commit()

    content_segments = build_single_content_segment(transcript)

    logger.info(f"Identifying {n_speakers} speakers...\n")
    identifier = UnifiedSpeakerIdentifier()
    with get_session() as session:
        results = identifier.identify_speakers(
            transcript, content_segments, episode_id, session
        )
        session.commit()

    logger.info("\n=== IDENTIFIED SPEAKERS ===\n")
    sorted_results = sorted(
        results.items(), key=lambda kv: kv[1].confidence, reverse=True
    )
    for label, r in sorted_results:
        bar_n = int(r.confidence * 10)
        bar = "█" * bar_n + "░" * (10 - bar_n)
        logger.info(
            f"  {label:<20} {r.name_en:<24} ({r.role:<8}) [{bar}] {r.confidence:.2f}"
        )

    logger.info("\n=== DB SUMMARY ===\n")
    with get_session() as session:
        identities = (
            session.query(SpeakerIdentity).filter_by(episode_id=episode_id).all()
        )
        role_counts: dict[str, int] = {}
        method_counts: dict[str, int] = {}
        with_reasoning = 0
        for si in identities:
            role_counts[si.role] = role_counts.get(si.role, 0) + 1
            method_counts[si.method] = method_counts.get(si.method, 0) + 1
            if (si.evidence or {}).get("reasoning"):
                with_reasoning += 1

        logger.info("  By role:")
        for role, c in sorted(role_counts.items()):
            logger.info(f"    {role}: {c}")
        logger.info("  By method:")
        for method, c in sorted(method_counts.items()):
            logger.info(f"    {method}: {c}")

        identified = sum(1 for i in identities if i.person_id is not None)
        logger.info(f"  Identified: {identified} / {len(identities)}")
        logger.info(f"  Rows with reasoning field: {with_reasoning}")

        persons = session.query(Person).all()
        if persons:
            logger.info(f"\n  Persons created: {len(persons)}")
            for p in sorted(persons, key=lambda p: p.name_en):
                logger.info(f"    - {p.name_en} ({p.role})")

    # Light assertions: low-confidence rows must be Unknown (strict 0.7 floor).
    with get_session() as session:
        violations = (
            session.query(SpeakerIdentity)
            .filter_by(episode_id=episode_id)
            .filter(SpeakerIdentity.person_id.is_not(None))
            .filter(SpeakerIdentity.confidence < 0.7)
            .count()
        )
    assert violations == 0, (
        f"Strict-confidence enforcement broken: {violations} rows have a person_id "
        f"with confidence < 0.7"
    )

    logger.info("\n✓ Test completed (strict-confidence floor enforced)")


if __name__ == "__main__":
    main()
