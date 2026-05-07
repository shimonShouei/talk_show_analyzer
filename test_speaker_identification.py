#!/usr/bin/env python3
"""Test speaker identification end-to-end with acoustic merge.

Builds a synthetic transcript with deliberate over-segmentation: one host
fragmented across two SPEAKER labels (with near-identical embeddings), one
guest with a distinct embedding. Confirms that the merge collapses the host
fragments and that the LLM correctly identifies host/guest by name.

Requires ANTHROPIC_API_KEY. No GPU needed (embeddings are synthetic).
"""

from datetime import datetime

import numpy as np
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


def build_transcript() -> TranscriptionResult:
    """Synthetic over-segmented transcript: host fragmented into 2 labels + 1 guest.

    The host's two labels (SPEAKER_00, SPEAKER_02) share near-identical embeddings,
    so the acoustic merge step should collapse them into one canonical SPEAKER_00.
    """
    segments = [
        SpeakerSegment(
            start=0.0,
            end=10.0,
            speaker="SPEAKER_00",
            text="שלום לכם, שמי דן שיסר ואני מארח את תוכנית הבוקר של 103FM. היום עם אותנו אורח מיוחד",
        ),
        SpeakerSegment(
            start=10.0,
            end=20.0,
            speaker="SPEAKER_01",
            text="שלום, תודה על ההזמנה. שמי יוסי כהן ואני כתב במשרד התקשורת",
        ),
        SpeakerSegment(
            start=20.0,
            end=30.0,
            speaker="SPEAKER_02",  # actually the host again, just a different diarization label
            text="ברוך הבא יוסי, אתה יכול להגיד לנו על החדשות של היום?",
        ),
        SpeakerSegment(
            start=30.0,
            end=45.0,
            speaker="SPEAKER_01",
            text="כן כמובן. היום יש חדשות חשובות מהעולם הטכנולוגיה. למעשה, מה שראינו השבוע הוא שינוי דרמטי בכל המערכת",
        ),
        SpeakerSegment(
            start=45.0,
            end=55.0,
            speaker="SPEAKER_00",
            text="מעניין מאוד יוסי, מה דעתך על ההשלכות?",
        ),
        SpeakerSegment(
            start=55.0,
            end=70.0,
            speaker="SPEAKER_01",
            text="ההשלכות מרחיקות לכת. אנחנו רואים שינוי בהתנהגות הצרכנים, בדרך שבה חברות פועלות, ובאסדרה",
        ),
    ]

    # Host (SPEAKER_00, SPEAKER_02) → near-identical vectors. Guest (SPEAKER_01) → distinct.
    rng = np.random.default_rng(42)
    host_base = rng.normal(size=192).astype(np.float32)
    host_base /= np.linalg.norm(host_base)
    guest_base = rng.normal(size=192).astype(np.float32)
    guest_base /= np.linalg.norm(guest_base)
    # Make host_02 a tiny perturbation of host_00 → cosine similarity > 0.99
    perturbation = rng.normal(size=192).astype(np.float32) * 0.02

    speaker_embeddings = {
        "SPEAKER_00": host_base,
        "SPEAKER_01": guest_base,
        "SPEAKER_02": (host_base + perturbation) / np.linalg.norm(host_base + perturbation),
    }

    return TranscriptionResult(
        raw_text=" ".join(s.text for s in segments),
        language="he",
        duration=70.0,
        word_count=120,
        segments=segments,
        speaker_embeddings=speaker_embeddings,
    )


def build_content_segments(transcript: TranscriptionResult) -> list[Segment]:
    """Single conversation segment covering the whole transcript."""
    speakers = sorted({s.speaker for s in transcript.segments})
    return [
        Segment(
            type="interview",
            start=0.0,
            end=transcript.duration,
            speakers=speakers,
            summary="Host interviews tech-affairs reporter about today's news.",
            raw_text=transcript.raw_text,
        )
    ]


def main() -> None:
    logger.info("\n=== SPEAKER IDENTIFICATION TEST (synthetic, with acoustic merge) ===\n")

    init_db(settings.database_url)

    with get_session() as session:
        station = session.query(Station).filter_by(name="103fm").first()
        if not station:
            station = Station(name="103fm", stream_url="http://test.url")
            session.add(station)
            session.flush()

        episode = Episode(
            station_id=station.id,
            recorded_at=datetime.utcnow(),
            duration=70,
            audio_path="/test/synthetic.mp3",
            language="he",
            word_count=120,
            raw_text="",
            status="pending",
        )
        session.add(episode)
        session.flush()
        episode_id = episode.id
        # Clear any stale identities from prior runs of this test
        session.query(SpeakerIdentity).filter_by(episode_id=episode_id).delete()
        session.commit()

    transcript = build_transcript()
    content_segments = build_content_segments(transcript)
    n_input = len({s.speaker for s in transcript.segments})
    logger.info(f"Built transcript with {n_input} diarization labels (expecting merge to 2)")

    identifier = UnifiedSpeakerIdentifier()
    with get_session() as session:
        results = identifier.identify_speakers(
            transcript, content_segments, episode_id, session
        )
        session.commit()

    logger.info("\n=== RESULTS (per original label) ===\n")
    for label in sorted(results.keys()):
        r = results[label]
        logger.info(
            f"  {label} -> {r.name_en} ({r.role}, conf={r.confidence:.2f})"
        )

    logger.info("\n=== DATABASE: SpeakerIdentity rows ===\n")
    with get_session() as session:
        identities = (
            session.query(SpeakerIdentity).filter_by(episode_id=episode_id).all()
        )
        canonical_to_person: dict[str, int | None] = {}
        for si in identities:
            person_name = si.person.name_en if si.person else "Unknown"
            canonical = (si.evidence or {}).get("canonical_label", si.speaker_label)
            merged_from = (si.evidence or {}).get("merged_from", [si.speaker_label])
            logger.info(
                f"  {si.speaker_label} -> {person_name} "
                f"(canonical={canonical}, merged_from={merged_from}, "
                f"role={si.role}, conf={si.confidence:.2f}, method={si.method})"
            )
            canonical_to_person[canonical] = si.person_id

        persons = session.query(Person).all()
        logger.info(f"\n  Persons in DB: {len(persons)}")
        for p in persons:
            logger.info(f"    - {p.name_en} ({p.role})")

    # ---- Assertions ----
    expected_canonicals = {results[lab].speaker_label for lab in results}  # all = original
    # Acoustic merge should have collapsed SPEAKER_00 + SPEAKER_02 → same canonical:
    canonicals = set()
    with get_session() as session:
        for si in session.query(SpeakerIdentity).filter_by(episode_id=episode_id).all():
            canonicals.add((si.evidence or {}).get("canonical_label", si.speaker_label))

    logger.info(f"\n  Distinct canonical labels: {len(canonicals)} ({sorted(canonicals)})")
    assert len(canonicals) == 2, (
        f"Expected acoustic merge to collapse 3 labels into 2 canonicals, got {canonicals}"
    )

    # SPEAKER_00 and SPEAKER_02 should share the same person_id
    p00 = next(r for r in results.values() if r.speaker_label == "SPEAKER_00")
    p02 = next(r for r in results.values() if r.speaker_label == "SPEAKER_02")
    assert p00.person_id == p02.person_id, (
        f"Host fragments should share person_id; got {p00.person_id} vs {p02.person_id}"
    )

    logger.info("\n✓ Test passed: acoustic merge collapsed host fragments into one identity")


if __name__ == "__main__":
    main()
