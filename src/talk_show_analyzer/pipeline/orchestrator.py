"""Pipeline orchestration with checkpointing and recovery."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from sqlalchemy.orm import Session, joinedload

from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import Episode, PipelineRun, Station, Segment
from talk_show_analyzer.recorder import record_station
from talk_show_analyzer.transcription import Transcriber
from talk_show_analyzer.analysis import (
    Segmenter,
    TopicExtractor,
    SentimentAnalyzer,
    aggregate_ads,
)
from talk_show_analyzer.identification import UnifiedSpeakerIdentifier
from talk_show_analyzer.transcription.transcriber import (
    TranscriptionResult,
    SpeakerSegment,
)
from talk_show_analyzer.pipeline.store import store_episode_results


class PipelineOrchestrator:
    """Orchestrate recording, transcription, analysis, and storage."""

    STEPS = [
        "record",
        "transcribe",
        "segment",
        "identify_speakers",
        "topics",
        "sentiment",
        "store",
    ]

    # Segment types treated as non-content (filtered before analysis)
    AD_TYPES = {"ad", "jingle", "music"}

    def __init__(self):
        """Initialize orchestrator."""
        self.transcriber = Transcriber(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        self.segmenter = Segmenter()
        self.speaker_identifier = UnifiedSpeakerIdentifier()
        self.topic_extractor = TopicExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()

    def run(
        self,
        station: str,
        duration_seconds: int = 14400,  # 4 hours
        output_dir: Path = Path("data"),
    ) -> Episode:
        """
        Run full pipeline: record → transcribe → analyze → store.

        Args:
            station: Station name (galatz, kan_bet, 103fm)
            duration_seconds: Recording duration in seconds
            output_dir: Directory to save recordings

        Returns:
            Episode model instance from database
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"\n{'='*60}")
        logger.info(f"PIPELINE START: {station.upper()}")
        logger.info(f"{'='*60}\n")

        with get_session() as session:
            # Create or get station
            db_station = self._get_or_create_station(session, station)

            # Create episode record
            audio_path = output_dir / f"{station}_{datetime.utcnow().isoformat()}.mp3"
            episode = Episode(
                station_id=db_station.id,
                recorded_at=datetime.utcnow(),
                duration=0,
                audio_path=str(audio_path),
                language="he",
                word_count=0,
                raw_text="",
                status="pending",
            )
            session.add(episode)
            session.commit()
            episode_id = episode.id

            logger.info(f"Created episode record: id={episode_id}\n")

        # Run pipeline steps
        try:
            # Step 1: Record
            audio_path = self._run_step_with_checkpoint(
                episode_id,
                "record",
                lambda: self._step_record(station, audio_path, duration_seconds),
            )

            # Step 2: Transcribe
            transcript = self._run_step_with_checkpoint(
                episode_id,
                "transcribe",
                lambda: self._step_transcribe(audio_path),
            )

            # Step 3: Segment (before speaker ID so ads can be filtered)
            segments = self._run_step_with_checkpoint(
                episode_id,
                "segment",
                lambda: self._step_segment(transcript),
            )

            content_segments = [s for s in segments if s.type not in self.AD_TYPES]
            logger.info(
                f"Filtered to {len(content_segments)}/{len(segments)} content segments "
                f"(excluded: {len(segments) - len(content_segments)} ad/jingle/music)"
            )

            # Step 4: Identify speakers using cross-speaker name mentions
            speaker_identities = self._run_step_with_checkpoint(
                episode_id,
                "identify_speakers",
                lambda: self._step_identify_speakers(transcript, content_segments, episode_id),
            )

            # Step 5: Topics
            topic_analyses = self._run_step_with_checkpoint(
                episode_id,
                "topics",
                lambda: self._step_topics(content_segments),
            )

            # Step 6: Sentiment
            sentiment_analyses = self._run_step_with_checkpoint(
                episode_id,
                "sentiment",
                lambda: self._step_sentiment(topic_analyses),
            )

            # Step 7: Store
            ads_report = self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(
                    episode_id,
                    transcript,
                    segments,
                    topic_analyses,
                    sentiment_analyses,
                ),
            )

            logger.info(f"\n{'='*60}")
            logger.info("✓ PIPELINE COMPLETE")
            logger.info(f"{'='*60}\n")

            # Fetch and return updated episode with relationships eagerly loaded
            with get_session() as session:
                episode = (
                    session.query(Episode)
                    .filter_by(id=episode_id)
                    .options(
                        joinedload(Episode.segments).joinedload(Segment.topics),
                        joinedload(Episode.segments).joinedload(Segment.guest_appearances),
                        joinedload(Episode.segments).joinedload(Segment.sentiments),
                    )
                    .first()
                )
                return episode

        except Exception as e:
            logger.error(f"\n✗ PIPELINE FAILED: {e}")
            raise

    def resume(self, episode_id: int) -> Episode:
        """
        Resume a failed pipeline run from the last completed step.

        Args:
            episode_id: Episode ID to resume

        Returns:
            Episode model instance
        """
        logger.info(f"\nResuming episode {episode_id}...\n")

        with get_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()
            if not episode:
                raise ValueError(f"Episode {episode_id} not found")

            audio_path = Path(episode.audio_path)
            logger.info(f"Audio: {audio_path}")

            # Load transcript from file if it exists
            transcript_file = audio_path.parent / f"{audio_path.stem}_transcript.json"
            if transcript_file.exists():
                with open(transcript_file) as f:
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
                transcript = TranscriptionResult(
                    raw_text=data["raw_text"],
                    language=data["language"],
                    duration=data["duration"],
                    word_count=data["word_count"],
                    segments=segments,
                )
                logger.info(f"Loaded cached transcript from {transcript_file}")
            else:
                raise ValueError("Cached transcript not found for resume")

            # Run remaining steps
            last_done = self._get_last_completed_step(episode_id)
            logger.info(f"Last completed step: {last_done or 'none'}")

        # Continue from where we left off
        try:
            if not last_done or last_done == "transcribe":
                segments = self._run_step_with_checkpoint(
                    episode_id,
                    "segment",
                    lambda: self._step_segment(transcript),
                )

            content_segments = [s for s in segments if s.type not in self.AD_TYPES]

            if not last_done or last_done in ["transcribe", "segment"]:
                speaker_identities = self._run_step_with_checkpoint(
                    episode_id,
                    "identify_speakers",
                    lambda: self._step_identify_speakers(transcript, content_segments, episode_id),
                )

            if not last_done or last_done in ["transcribe", "segment", "identify_speakers"]:
                topic_analyses = self._run_step_with_checkpoint(
                    episode_id,
                    "topics",
                    lambda: self._step_topics(content_segments),
                )

            if not last_done or last_done in ["transcribe", "segment", "identify_speakers", "topics"]:
                sentiment_analyses = self._run_step_with_checkpoint(
                    episode_id,
                    "sentiment",
                    lambda: self._step_sentiment(topic_analyses),
                )

            ads_report = self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(
                    episode_id,
                    transcript,
                    segments,
                    topic_analyses,
                    sentiment_analyses,
                ),
            )

            logger.info("✓ Resume completed")

            with get_session() as session:
                episode = (
                    session.query(Episode)
                    .filter_by(id=episode_id)
                    .options(
                        joinedload(Episode.segments).joinedload(Segment.topics),
                        joinedload(Episode.segments).joinedload(Segment.guest_appearances),
                        joinedload(Episode.segments).joinedload(Segment.sentiments),
                    )
                    .first()
                )
                return episode

        except Exception as e:
            logger.error(f"Resume failed: {e}")
            raise

    def _get_or_create_station(self, session: Session, name: str) -> Station:
        """Get or create station record."""
        station = session.query(Station).filter_by(name=name).first()
        if not station:
            station = Station(
                name=name,
                stream_url="",  # Will be filled by recorder
            )
            session.add(station)
            session.commit()
        return station

    def _run_step_with_checkpoint(
        self, episode_id: int, step: str, fn: Callable[[], Any]
    ) -> Any:
        """
        Run a step with checkpointing and recovery.

        If step already completed, skip it. Otherwise run it and record status.
        """
        with get_session() as session:
            # Check if already done
            existing = (
                session.query(PipelineRun)
                .filter_by(episode_id=episode_id, step=step, status="done")
                .first()
            )
            if existing:
                logger.info(f"Skipping {step} (already completed)")
                return None

            # Mark as running
            run = PipelineRun(
                episode_id=episode_id,
                step=step,
                status="running",
                started_at=datetime.utcnow(),
            )
            session.add(run)
            session.commit()

        logger.info(f"Running step: {step}")
        start = datetime.utcnow()

        try:
            result = fn()

            with get_session() as session:
                run = (
                    session.query(PipelineRun)
                    .filter_by(episode_id=episode_id, step=step)
                    .order_by(PipelineRun.id.desc())
                    .first()
                )
                run.status = "done"
                run.completed_at = datetime.utcnow()
                session.commit()

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info(f"✓ {step} completed ({duration:.1f}s)\n")
            return result

        except Exception as e:
            with get_session() as session:
                run = (
                    session.query(PipelineRun)
                    .filter_by(episode_id=episode_id, step=step)
                    .order_by(PipelineRun.id.desc())
                    .first()
                )
                run.status = "failed"
                run.error = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

            logger.error(f"✗ {step} failed: {e}")
            raise

    def _get_last_completed_step(self, episode_id: int) -> str | None:
        """Get the last completed pipeline step."""
        with get_session() as session:
            run = (
                session.query(PipelineRun)
                .filter_by(episode_id=episode_id, status="done")
                .order_by(PipelineRun.id.desc())
                .first()
            )
            return run.step if run else None

    # Pipeline step implementations
    def _step_record(self, station: str, output_path: Path, duration: int) -> Path:
        """Record audio from stream."""
        logger.info(f"Recording {duration}s from {station}...")
        success = record_station(station, output_path, duration)
        if not success:
            raise RuntimeError(f"Failed to record from {station}")
        return output_path

    def _step_transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio."""
        logger.info(f"Transcribing {audio_path}...")
        transcript = self.transcriber.transcribe_file(
            audio_path,
            output_json=audio_path.parent / f"{audio_path.stem}_transcript.json",
            language="he",
        )
        return transcript

    def _step_segment(self, transcript: TranscriptionResult) -> list:
        """Segment transcript into content types (including ads)."""
        logger.info("Segmenting transcript...")
        return self.segmenter.segment(transcript)

    def _step_identify_speakers(
        self, transcript: TranscriptionResult, content_segments: list, episode_id: int
    ) -> dict:
        """Identify all speakers using cross-speaker name mentions in non-ad segments."""
        logger.info("Identifying speakers...")
        with get_session() as session:
            speaker_identities = self.speaker_identifier.identify_speakers(
                transcript, content_segments, episode_id, session
            )
            session.commit()
        return speaker_identities

    def _step_topics(self, content_segments: list) -> list:
        """Extract topics from non-ad segments."""
        logger.info("Extracting topics...")
        return self.topic_extractor.extract_topics(content_segments)

    def _step_sentiment(self, topic_analyses: list) -> list:
        """Analyze sentiment."""
        logger.info("Analyzing sentiment...")
        return self.sentiment_analyzer.analyze_sentiments(topic_analyses)

    def _step_store(
        self,
        episode_id: int,
        transcript: TranscriptionResult,
        segments: list,
        topic_analyses: list,
        sentiment_analyses: list,
    ) -> dict:
        """Store results to database."""
        logger.info("Storing results to database...")

        ads_report = aggregate_ads(segments, transcript.duration)

        with get_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()
            episode.duration = transcript.duration
            episode.word_count = transcript.word_count
            episode.raw_text = transcript.raw_text

            store_episode_results(
                session,
                episode,
                segments,
                topic_analyses,
                sentiment_analyses,
                ads_report.ad_count,
                ads_report.ad_percentage,
            )

        return {
            "ads_count": ads_report.ad_count,
            "ads_percentage": ads_report.ad_percentage,
        }
