"""Pipeline orchestration with checkpointing and recovery."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from sqlalchemy.orm import Session

from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import Episode, PipelineRun, Station
from talk_show_analyzer.recorder import record_station
from talk_show_analyzer.transcription import Transcriber
from talk_show_analyzer.analysis import ThematicAnalyzer
from talk_show_analyzer.analysis.thematic_analyzer import TopicAnalysis
from talk_show_analyzer.identification import UnifiedSpeakerIdentifier
from talk_show_analyzer.transcription.transcriber import (
    TranscriptionResult,
    SpeakerSegment,
)
from talk_show_analyzer.pipeline.store import store_thematic_results


class PipelineOrchestrator:
    """Orchestrate recording, transcription, analysis, and storage."""

    STEPS = [
        "record",
        "transcribe",
        "identify_speakers",
        "thematic",
        "store",
    ]

    def __init__(self):
        """Initialize orchestrator."""
        self.transcriber = Transcriber(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        self.speaker_identifier = UnifiedSpeakerIdentifier()
        self.thematic_analyzer = ThematicAnalyzer()

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

            # Step 3: Identify speakers across the whole transcript
            speaker_identities = self._run_step_with_checkpoint(
                episode_id,
                "identify_speakers",
                lambda: self._step_identify_speakers(
                    transcript, transcript.segments, episode_id
                ),
            )

            # Step 4: Thematic Intelligence pipeline (segment + merge + analyze)
            topic_analyses = self._run_step_with_checkpoint(
                episode_id,
                "thematic",
                lambda: self._step_thematic(transcript),
            )

            # Step 5: Store
            self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(episode_id, transcript, topic_analyses),
            )

            logger.info(f"\n{'='*60}")
            logger.info("✓ PIPELINE COMPLETE")
            logger.info(f"{'='*60}\n")

            # Fetch and return updated episode
            with get_session() as session:
                episode = (
                    session.query(Episode).filter_by(id=episode_id).first()
                )
                return episode

        except Exception as e:
            logger.error(f"\n✗ PIPELINE FAILED: {e}")
            raise

    def run_from_file(
        self,
        audio_path: str | Path,
        station: str = "unknown",
        duration_seconds: int | None = None,
    ) -> Episode:
        """
        Run the pipeline on an existing audio file, skipping the record step.

        Args:
            audio_path: Path to the audio file (e.g. a downloaded episode).
            station: Station name to associate in the database.
            duration_seconds: If set, trim the audio to this many seconds before
                processing (uses ffmpeg; handy for quick tests).

        Returns:
            Episode model instance.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)

        if duration_seconds is not None:
            trimmed = audio_path.parent / f"{audio_path.stem}_trim{duration_seconds}s.mp3"
            logger.info(f"Trimming to {duration_seconds}s → {trimmed}")
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-i", str(audio_path), "-t", str(duration_seconds),
                 "-acodec", "copy", "-y", str(trimmed)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg trim failed: {result.stderr[-300:]}")
            audio_path = trimmed

        logger.info(f"\n{'='*60}")
        logger.info(f"PIPELINE START (from file): {audio_path.name}")
        logger.info(f"{'='*60}\n")

        with get_session() as session:
            db_station = self._get_or_create_station(session, station)
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

        try:
            transcript = self._run_step_with_checkpoint(
                episode_id, "transcribe", lambda: self._step_transcribe(audio_path)
            )
            speaker_identities = self._run_step_with_checkpoint(
                episode_id,
                "identify_speakers",
                lambda: self._step_identify_speakers(transcript, transcript.segments, episode_id),
            )
            topic_analyses = self._run_step_with_checkpoint(
                episode_id, "thematic", lambda: self._step_thematic(transcript)
            )
            self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(episode_id, transcript, topic_analyses),
            )

            logger.info(f"\n{'='*60}")
            logger.info("✓ PIPELINE COMPLETE")
            logger.info(f"{'='*60}\n")

            with get_session() as session:
                return session.query(Episode).filter_by(id=episode_id).first()

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
                speaker_identities = self._run_step_with_checkpoint(
                    episode_id,
                    "identify_speakers",
                    lambda: self._step_identify_speakers(
                        transcript, transcript.segments, episode_id
                    ),
                )

            if not last_done or last_done in ["transcribe", "identify_speakers"]:
                topic_analyses = self._run_step_with_checkpoint(
                    episode_id,
                    "thematic",
                    lambda: self._step_thematic(transcript),
                )

            self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(episode_id, transcript, topic_analyses),
            )

            logger.info("✓ Resume completed")

            with get_session() as session:
                episode = (
                    session.query(Episode).filter_by(id=episode_id).first()
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

    def _step_identify_speakers(
        self, transcript: TranscriptionResult, content_segments: list, episode_id: int
    ) -> dict:
        """Identify all speakers using cross-speaker name mentions."""
        logger.info("Identifying speakers...")
        with get_session() as session:
            speaker_identities = self.speaker_identifier.identify_speakers(
                transcript, content_segments, episode_id, session
            )
            session.commit()
        return speaker_identities

    def _step_thematic(self, transcript: TranscriptionResult) -> list[TopicAnalysis]:
        """Run the Thematic Intelligence pipeline (segment → merge → analyze)."""
        logger.info("Running thematic analysis...")
        return self.thematic_analyzer.analyze(transcript)

    def _step_store(
        self,
        episode_id: int,
        transcript: TranscriptionResult,
        topic_analyses: list[TopicAnalysis],
    ) -> dict:
        """Store thematic results to database."""
        logger.info("Storing thematic results to database...")

        with get_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()
            episode.duration = transcript.duration
            episode.word_count = transcript.word_count
            episode.raw_text = transcript.raw_text

            store_thematic_results(session, episode, topic_analyses)

        return {"merged_topics": len(topic_analyses)}
