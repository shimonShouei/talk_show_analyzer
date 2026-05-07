"""Re-run speaker identification on existing episodes using the existing orchestrator."""

import json
import sys
from pathlib import Path

import sqlalchemy as sa
from loguru import logger

from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import Episode, SpeakerIdentity
from talk_show_analyzer.models import Segment as OrmSegment
from talk_show_analyzer.analysis.segmenter import Segment
from talk_show_analyzer.transcription.transcriber import TranscriptionResult, SpeakerSegment
from talk_show_analyzer.identification.llm_identifier import UnifiedSpeakerIdentifier


def _reconstruct_segments(orm_segments: list, transcript: TranscriptionResult) -> list[Segment]:
    """Rebuild in-memory Segment dataclasses from ORM rows + transcript speaker data."""
    result = []
    for orm_seg in orm_segments:
        speakers = sorted({
            ts.speaker
            for ts in transcript.segments
            if ts.start < orm_seg.end and ts.end > orm_seg.start
        })
        result.append(Segment(
            type=orm_seg.type,
            start=orm_seg.start,
            end=orm_seg.end,
            speakers=speakers,
            summary=orm_seg.summary or "",
            raw_text="",  # not needed for speaker identification
        ))
    return result

AD_TYPES = {"ad", "jingle", "music"}


def reidentify_episode(identifier: UnifiedSpeakerIdentifier, episode_id: int) -> None:
    with get_session() as session:
        episode = session.query(Episode).filter_by(id=episode_id).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        audio_path = Path(episode.audio_path)
        transcript_file = audio_path.parent / f"{audio_path.stem}_transcript.json"
        if not transcript_file.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_file}")

        with open(transcript_file) as f:
            data = json.load(f)

        transcript = TranscriptionResult(
            raw_text=data["raw_text"],
            language=data["language"],
            duration=data["duration"],
            word_count=data["word_count"],
            segments=[
                SpeakerSegment(
                    start=seg["start"],
                    end=seg["end"],
                    speaker=seg["speaker"],
                    text=seg["text"],
                )
                for seg in data["segments"]
            ],
        )

        orm_segments = session.query(OrmSegment).filter_by(episode_id=episode_id).all()
        if not orm_segments:
            raise ValueError(f"No segments for episode {episode_id} — run segmentation first")

        segments = _reconstruct_segments(orm_segments, transcript)
        content_segments = [s for s in segments if s.type not in AD_TYPES]
        logger.info(f"Episode {episode_id}: {len(content_segments)}/{len(segments)} content segments")

        deleted = session.query(SpeakerIdentity).filter_by(episode_id=episode_id).delete()
        session.commit()
        logger.info(f"Cleared {deleted} old SpeakerIdentity rows")

        results = identifier.identify_speakers(transcript, content_segments, episode_id, session)
        session.commit()

    identified = sum(1 for r in results.values() if r.name_en != "Unknown")
    logger.info(f"Episode {episode_id}: {identified}/{len(results)} speakers identified")


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
    if not ids:
        with get_session() as s:
            ids = [e.id for e in s.query(Episode).all()]
        logger.info(f"No episode IDs given — running on all episodes: {ids}")

    identifier = UnifiedSpeakerIdentifier()
    for eid in ids:
        logger.info(f"\n=== Episode {eid} ===")
        reidentify_episode(identifier, eid)
