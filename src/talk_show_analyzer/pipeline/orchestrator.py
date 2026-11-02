"""Pipeline orchestration with checkpointing and recovery."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from sqlalchemy.orm import Session

from talk_show_analyzer.config import settings
from talk_show_analyzer.db import get_session
from talk_show_analyzer.models import Episode, PartORM, PipelineRun, SpeakerIdentity, Station, Segment, Person
from talk_show_analyzer.recorder import record_station
from talk_show_analyzer.transcription import Transcriber
from talk_show_analyzer.analysis import ThematicAnalyzer
from talk_show_analyzer.analysis.chunk_analyzer import ChunkAnalyzer, chunk_analyses_to_thematic_chunks
from talk_show_analyzer.analysis.qa_extractor import NamedQAExtractor
from talk_show_analyzer.analysis.speaker_part_analyzer import SpeakerPartAnalyzer
from talk_show_analyzer.analysis.structural_segmenter import Part, PartType, assemble_parts_from_chunks, segment_into_parts
from talk_show_analyzer.analysis.thematic_analyzer import TopicAnalysis
from talk_show_analyzer.identification import UnifiedSpeakerIdentifier
from talk_show_analyzer.identification.host_resolver import HostResolution, HostResolver
from talk_show_analyzer.identification.llm_identifier import (
    ResolvedSpeaker,
    consolidate_speakers,
    deferred_resolve_speakers,
    _merge_speakers_acoustic,
)
from talk_show_analyzer.identification.reference_registry import load_registry, match_to_references
from talk_show_analyzer.transcription.transcriber import (
    TranscriptionResult,
    SpeakerSegment,
)
from talk_show_analyzer.pipeline.store import store_thematic_results

# Make sure schedule providers (e.g. 103fm) are registered at import time.
import talk_show_analyzer.recorder.schedules  # noqa: F401


def _setup_logging() -> None:
    """Configure loguru: file sink at DEBUG + stderr at settings.log_level."""
    try:
        logger.remove(0)  # drop default handler
    except ValueError:
        pass  # already removed
    logger.add(sys.stderr, level=settings.log_level, colorize=True,
                format="<level>{level: <8}</level> | {message}")
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(
        logs_dir / f"pipeline_{ts}.log",
        level="DEBUG",
        rotation="100 MB",
        retention=10,
        encoding="utf-8",
    )
    logger.debug(f"Logging to {logs_dir}/pipeline_{ts}.log")


class PipelineOrchestrator:
    """Orchestrate recording, transcription, analysis, and storage."""

    STEPS = [
        "record",
        "transcribe",
        "chunk_analyze",
        "deferred_resolve",
        "resolve_hosts",
        "enrich_parts",
        "store",
    ]

    def __init__(self):
        """Initialize orchestrator."""
        _setup_logging()
        self.transcriber = Transcriber(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            enable_diarization=settings.diarization_enabled,
        )
        self.chunk_analyzer = ChunkAnalyzer()
        self.host_resolver = HostResolver()
        self.thematic_analyzer = ThematicAnalyzer()
        self.speaker_part_analyzer = SpeakerPartAnalyzer()
        self.qa_extractor = NamedQAExtractor()

    @staticmethod
    def _preflight() -> None:
        """Fail fast: without a key every LLM stage silently returns "unknown"
        after the (slow) transcription has already run."""
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set - LLM stages would silently produce empty output"
            )

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
        self._preflight()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"\n{'='*60}")
        logger.info(f"PIPELINE START: {station.upper()}")
        logger.info(f"{'='*60}\n")

        recorded_at = datetime.utcnow()
        with get_session() as session:
            # Create or get station
            db_station = self._get_or_create_station(session, station)

            # Create episode record
            audio_path = output_dir / f"{station}_{recorded_at.isoformat()}.mp3"
            episode = Episode(
                station_id=db_station.id,
                recorded_at=recorded_at,
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

            # Step 3: Unified chunk analysis (speaker ID + structural parts + topics)
            chunk_result = self._run_step_with_checkpoint(
                episode_id,
                "chunk_analyze",
                lambda: self._step_chunk_analyze(transcript, episode_id),
            )
            if chunk_result is None:
                chunk_result = self._load_chunk_analyze_results(episode_id, transcript)
            speaker_identities, parts, topic_analyses = chunk_result

            # Step 4: Deferred name resolution — fill in Unknown speakers via indirect mentions
            deferred_result = self._run_step_with_checkpoint(
                episode_id,
                "deferred_resolve",
                lambda: self._step_deferred_resolve(transcript, speaker_identities, episode_id),
            )
            if deferred_result is not None:
                speaker_identities = deferred_result

            # Step 5: Resolve hosts against the station schedule
            self._run_step_with_checkpoint(
                episode_id,
                "resolve_hosts",
                lambda: self._step_resolve_hosts(station, recorded_at, speaker_identities),
            )

            # Step 6: Enrich parts — per-part stance analysis + Q&A extraction
            self._run_step_with_checkpoint(
                episode_id,
                "enrich_parts",
                lambda: self._step_enrich_parts(episode_id, parts, transcript),
            )

            # Step 7: Store
            self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(episode_id, transcript, topic_analyses),
            )

            logger.info(f"\n{'='*60}")
            logger.info("✓ PIPELINE COMPLETE")
            logger.info(f"{'='*60}\n")

            # Fetch and return updated episode (with eager-loaded relationships)
            with get_session() as session:
                from sqlalchemy.orm import joinedload
                episode = (
                    session.query(Episode)
                    .filter_by(id=episode_id)
                    .options(
                        joinedload(Episode.segments).joinedload(Segment.topics),
                        joinedload(Episode.segments).joinedload(Segment.guest_appearances),
                    )
                    .first()
                )
                # Force all lazy attributes to load while session is active
                if episode:
                    _ = episode.segments
                    for segment in episode.segments:
                        _ = segment.topics
                        _ = segment.guest_appearances
                return episode

        except Exception as e:
            logger.error(f"\n✗ PIPELINE FAILED: {e}")
            raise

    def run_from_file(
        self,
        audio_path: str | Path,
        station: str = "unknown",
        duration_seconds: int | None = None,
        recorded_at: datetime | None = None,
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
        self._preflight()

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

        if recorded_at is None:
            recorded_at = datetime.utcnow()
        with get_session() as session:
            db_station = self._get_or_create_station(session, station)
            episode = Episode(
                station_id=db_station.id,
                recorded_at=recorded_at,
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
            chunk_result = self._run_step_with_checkpoint(
                episode_id,
                "chunk_analyze",
                lambda: self._step_chunk_analyze(transcript, episode_id),
            )
            if chunk_result is None:
                chunk_result = self._load_chunk_analyze_results(episode_id, transcript)
            speaker_identities, parts, topic_analyses = chunk_result
            deferred_result = self._run_step_with_checkpoint(
                episode_id,
                "deferred_resolve",
                lambda: self._step_deferred_resolve(transcript, speaker_identities, episode_id),
            )
            if deferred_result is not None:
                speaker_identities = deferred_result
            self._run_step_with_checkpoint(
                episode_id,
                "resolve_hosts",
                lambda: self._step_resolve_hosts(station, recorded_at, speaker_identities),
            )
            self._run_step_with_checkpoint(
                episode_id,
                "enrich_parts",
                lambda: self._step_enrich_parts(episode_id, parts, transcript),
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
                from sqlalchemy.orm import joinedload
                episode = (
                    session.query(Episode)
                    .filter_by(id=episode_id)
                    .options(
                        joinedload(Episode.segments).joinedload(Segment.topics),
                        joinedload(Episode.segments).joinedload(Segment.guest_appearances),
                    )
                    .first()
                )
                # Force all lazy attributes to load while session is active
                if episode:
                    _ = episode.segments
                    for segment in episode.segments:
                        _ = segment.topics
                        _ = segment.guest_appearances
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
            chunk_result = self._run_step_with_checkpoint(
                episode_id,
                "chunk_analyze",
                lambda: self._step_chunk_analyze(transcript, episode_id),
            )
            if chunk_result is None:
                chunk_result = self._load_chunk_analyze_results(episode_id, transcript)
            speaker_identities, parts, topic_analyses = chunk_result

            # Need station + recorded_at for host resolution; pull from DB.
            with get_session() as session:
                ep = session.query(Episode).filter_by(id=episode_id).first()
                ep_recorded_at = ep.recorded_at
                ep_station = session.query(Station).filter_by(id=ep.station_id).first()
                ep_station_name = ep_station.name if ep_station else "unknown"

            deferred_result = self._run_step_with_checkpoint(
                episode_id,
                "deferred_resolve",
                lambda: self._step_deferred_resolve(transcript, speaker_identities, episode_id),
            )
            if deferred_result is not None:
                speaker_identities = deferred_result

            self._run_step_with_checkpoint(
                episode_id,
                "resolve_hosts",
                lambda: self._step_resolve_hosts(
                    ep_station_name, ep_recorded_at, speaker_identities
                ),
            )

            self._run_step_with_checkpoint(
                episode_id,
                "enrich_parts",
                lambda: self._step_enrich_parts(episode_id, parts, transcript),
            )

            self._run_step_with_checkpoint(
                episode_id,
                "store",
                lambda: self._step_store(episode_id, transcript, topic_analyses),
            )

            logger.info("✓ Resume completed")

            with get_session() as session:
                from sqlalchemy.orm import joinedload
                episode = (
                    session.query(Episode)
                    .filter_by(id=episode_id)
                    .options(
                        joinedload(Episode.segments).joinedload(Segment.topics),
                        joinedload(Episode.segments).joinedload(Segment.guest_appearances),
                    )
                    .first()
                )
                # Force all lazy attributes to load while session is active
                if episode:
                    _ = episode.segments
                    for segment in episode.segments:
                        _ = segment.topics
                        _ = segment.guest_appearances
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

    def _step_chunk_analyze(
        self,
        transcript: TranscriptionResult,
        episode_id: int,
    ) -> tuple[dict[str, ResolvedSpeaker], list[Part], list[TopicAnalysis]]:
        """Unified chunk analysis: speaker ID + structural parts + thematic topics.

        Replaces the old identify_speakers + structural_segment + thematic steps with:
          1. Acoustic merge (no API)
          2. Per-chunk API call (speaker roles + topics + part_type) — parallel
          3. Speaker consolidation across chunks (no API)
          4. Part assembly from chunk part_types (no API)
          5. Topic Stage 2 — embedding cluster + LLM verification (1 API call)
          6. Topic Stage 3 — deep analysis per merged topic (1 API call each)
        """
        logger.info("Running unified chunk analysis...")

        # --- Acoustic merge ---
        content_labels: set[str] = {s.speaker for s in transcript.segments}
        content_embeddings = {
            lab: emb
            for lab, emb in transcript.speaker_embeddings.items()
            if lab in content_labels
        }
        if settings.acoustic_merge_enabled and len(content_embeddings) >= 2:
            label_map = _merge_speakers_acoustic(
                content_embeddings, settings.acoustic_merge_threshold
            )
        else:
            label_map = {}
        for label in content_labels:
            label_map.setdefault(label, label)

        # --- Reference registry matching (known hosts/guests by voice) ---
        references = load_registry(settings.reference_registry_path)
        reference_matches: dict[str, any] = {}
        if references and content_embeddings:
            logger.info("Matching episode speakers against reference registry...")
            reference_matches = match_to_references(
                content_embeddings, references, threshold=settings.reference_match_threshold
            )
            logger.info(f"Reference matching: {len(reference_matches)}/{len(content_embeddings)} speakers matched")

        # --- Per-chunk parallel API calls ---
        chunk_analyses = self.chunk_analyzer.analyze_all(transcript)

        # --- Speaker consolidation ---
        logger.info("Consolidating speaker roles across chunks...")
        resolved_speakers = consolidate_speakers(chunk_analyses, label_map)

        # --- Override with reference matches (high-confidence voice-based ID) ---
        for original_label, ref in reference_matches.items():
            canonical = label_map.get(original_label, original_label)
            # Apply to all original labels that map to the same canonical
            for orig, can in label_map.items():
                if can == canonical:
                    resolved_speakers[orig] = ResolvedSpeaker(
                        speaker_label=orig,
                        name_he=ref.name_he,
                        name_en=ref.name_en,
                        role=ref.role,
                        confidence=0.95,
                    )
            logger.info(f"  {canonical} → {ref.name_en} (voice match, conf=0.95)")

        # Persist speaker identities to DB
        with get_session() as session:
            for original_label, rs in resolved_speakers.items():
                person_id = None
                if rs.name_en != "Unknown":
                    person = session.query(Person).filter_by(name_en=rs.name_en).first()
                    if not person:
                        person = Person(
                            name_he=rs.name_he, name_en=rs.name_en, role=rs.role
                        )
                        session.add(person)
                        session.flush()
                    person_id = person.id
                    rs.person_id = person_id
                identity = SpeakerIdentity(
                    episode_id=episode_id,
                    speaker_label=original_label,
                    person_id=person_id,
                    role=rs.role,
                    confidence=rs.confidence,
                    method="chunk_consolidation",
                    evidence={"canonical_label": label_map.get(original_label, original_label)},
                )
                session.add(identity)
            session.commit()

        # --- Part assembly ---
        parts = assemble_parts_from_chunks(chunk_analyses)
        self._persist_parts(episode_id, parts)

        # --- Thematic Stage 2 + 3 ---
        # Exclude non-content windows (ads, news, jingles) from topic analysis
        _SKIP_TYPES = {"commercial", "jingle", "news"}
        content_chunks = [ca for ca in chunk_analyses if ca.part_type not in _SKIP_TYPES]
        skipped = len(chunk_analyses) - len(content_chunks)
        if skipped:
            logger.info(f"Thematic: skipping {skipped} non-content window(s) (ads/news/jingles)")
        thematic_chunks = chunk_analyses_to_thematic_chunks(content_chunks, transcript)
        logger.info(f"Thematic: {len(thematic_chunks)} topic chunks from {len(content_chunks)} content windows")

        topic_analyses: list[TopicAnalysis] = []
        if thematic_chunks:
            merged = self.thematic_analyzer.global_merge(thematic_chunks)
            logger.info(f"Stage 2: merged to {len(merged)} cross-show topics")
            for i, m in enumerate(merged):
                logger.info(f"Stage 3: deep analysis {i+1}/{len(merged)} — {m['merged_title_he']}")
                ta = self.thematic_analyzer.analyze_topic(m, thematic_chunks)
                if ta is not None:
                    topic_analyses.append(ta)
            logger.info(f"Thematic: completed {len(topic_analyses)} topic analyses")

        identified = sum(1 for r in resolved_speakers.values() if r.name_en != "Unknown")
        logger.info(
            f"chunk_analyze complete: {identified}/{len(resolved_speakers)} speakers identified, "
            f"{len(parts)} parts, {len(topic_analyses)} topic analyses"
        )
        return resolved_speakers, parts, topic_analyses

    def _load_chunk_analyze_results(
        self, episode_id: int, transcript: TranscriptionResult
    ) -> tuple[dict[str, ResolvedSpeaker], list[Part], list[TopicAnalysis]]:
        """Reload chunk_analyze outputs from DB when the checkpoint was already done."""
        resolved_speakers = self._load_resolved_speakers(episode_id)
        parts = self._load_parts(episode_id, transcript)
        return resolved_speakers, parts, []  # topic_analyses must come from store step

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

    def _step_resolve_hosts(
        self,
        station: str,
        recorded_at: datetime,
        resolved_speakers: dict[str, ResolvedSpeaker],
    ) -> HostResolution:
        """Match scheduled hosts against the LLM-identified speakers."""
        logger.info(f"Resolving hosts for {station} at {recorded_at.isoformat()}...")
        res = self.host_resolver.resolve(station, recorded_at, resolved_speakers)
        if res.schedule_available:
            logger.info(
                f"Show: {res.show_name!r} | expected={res.expected_hosts} | "
                f"confirmed={res.confirmed} | substitutes={res.substitutes} | "
                f"missing={res.missing_expected} | unknown={res.unknown_hosts}"
            )
        else:
            logger.info("No schedule available for this station/time; skipping match.")
        return res

    def _step_structural_segment(
        self,
        transcript: TranscriptionResult,
        resolved_speakers: dict[str, ResolvedSpeaker],
        episode_id: int | None = None,
    ) -> list[Part]:
        """Group transcript segments into structural parts and persist them."""
        logger.info("Segmenting transcript into structural parts...")
        parts = segment_into_parts(transcript.segments, resolved_speakers)
        for i, p in enumerate(parts):
            logger.info(
                f"  part {i}: {p.type.value} {p.start:.0f}–{p.end:.0f}s "
                f"({p.duration:.0f}s) hosts={sorted(p.host_labels)} "
                f"guests={sorted(p.guest_labels)}"
            )
        if episode_id is not None:
            self._persist_parts(episode_id, parts)
        return parts

    def _persist_parts(self, episode_id: int, parts: list[Part]) -> None:
        """Replace any existing parts for this episode with the new list."""
        with get_session() as session:
            session.query(PartORM).filter_by(episode_id=episode_id).delete()
            for idx, p in enumerate(parts):
                session.add(
                    PartORM(
                        episode_id=episode_id,
                        idx=idx,
                        type=p.type.value,
                        start_seconds=p.start,
                        end_seconds=p.end,
                        host_labels=sorted(p.host_labels),
                        guest_labels=sorted(p.guest_labels),
                        unknown_labels=sorted(p.unknown_labels),
                    )
                )
            session.commit()
        logger.info(f"Persisted {len(parts)} part(s) for episode {episode_id}")

    def _step_thematic(
        self,
        transcript: TranscriptionResult,
        parts: list[Part] | None = None,
    ) -> list[TopicAnalysis]:
        """Run the Thematic Intelligence pipeline per-part (or whole-transcript fallback)."""
        logger.info("Running thematic analysis...")
        if not parts:
            return self.thematic_analyzer.analyze(transcript)
        all_analyses: list[TopicAnalysis] = []
        for idx, part in enumerate(parts):
            results = self.thematic_analyzer.analyze_part(part)
            for ta in results:
                ta.part_idx = idx
            all_analyses.extend(results)
        logger.info(f"Per-part thematic: {len(all_analyses)} topic analyses across {len(parts)} parts")
        return all_analyses

    def _load_parts(self, episode_id: int, transcript: TranscriptionResult) -> list[Part]:
        """Reconstruct list[Part] from PartORM rows, re-attaching transcript segments."""
        from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
        with get_session() as session:
            rows = (
                session.query(PartORM)
                .filter_by(episode_id=episode_id)
                .order_by(PartORM.idx)
                .all()
            )
            parts: list[Part] = []
            for row in rows:
                segs = [
                    s for s in transcript.segments
                    if s.start >= row.start_seconds and s.end <= row.end_seconds
                ]
                parts.append(
                    Part(
                        type=PartType(row.type),
                        start=row.start_seconds,
                        end=row.end_seconds,
                        segments=segs,
                        host_labels=set(row.host_labels or []),
                        guest_labels=set(row.guest_labels or []),
                        unknown_labels=set(row.unknown_labels or []),
                    )
                )
        logger.info(f"_load_parts: loaded {len(parts)} part(s) for episode {episode_id}")
        return parts

    def _load_resolved_speakers(self, episode_id: int) -> dict[str, ResolvedSpeaker]:
        """Reconstruct the speaker-label → ResolvedSpeaker map from the DB.

        Used when a previous identify_speakers checkpoint was skipped and the
        in-memory return value is therefore None.
        """
        with get_session() as session:
            rows = (
                session.query(SpeakerIdentity)
                .filter_by(episode_id=episode_id)
                .all()
            )
            out: dict[str, ResolvedSpeaker] = {}
            for r in rows:
                person = r.person
                out[r.speaker_label] = ResolvedSpeaker(
                    speaker_label=r.speaker_label,
                    name_he=person.name_he if person else "Unknown",
                    name_en=person.name_en if person else "Unknown",
                    role=r.role,
                    confidence=r.confidence,
                    person_id=person.id if person else None,
                )
            logger.info(f"Reloaded {len(out)} resolved speakers from DB for ep {episode_id}")
            return out

    def _step_deferred_resolve(
        self,
        transcript: TranscriptionResult,
        resolved: dict[str, ResolvedSpeaker],
        episode_id: int,
    ) -> dict[str, ResolvedSpeaker]:
        """Second-pass speaker identification: fill in Unknown speakers via indirect mentions."""
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
        updated = deferred_resolve_speakers(transcript, resolved, client)

        # Persist any newly resolved speakers to DB.
        newly_resolved = {
            label: rs
            for label, rs in updated.items()
            if rs.name_en != "Unknown"
            and resolved.get(label, ResolvedSpeaker(label, "Unknown", "Unknown", "unknown", 0.0)).name_en == "Unknown"
        }
        if newly_resolved:
            with get_session() as session:
                for label, rs in newly_resolved.items():
                    person = session.query(Person).filter_by(name_en=rs.name_en).first()
                    if not person:
                        person = Person(name_he=rs.name_he, name_en=rs.name_en, role=rs.role)
                        session.add(person)
                        session.flush()
                    # Update existing SpeakerIdentity row for this label.
                    identity = (
                        session.query(SpeakerIdentity)
                        .filter_by(episode_id=episode_id, speaker_label=label)
                        .first()
                    )
                    if identity:
                        identity.person_id = person.id
                        identity.role = rs.role
                        identity.confidence = rs.confidence
                        identity.method = "deferred_resolve"
                    else:
                        session.add(SpeakerIdentity(
                            episode_id=episode_id,
                            speaker_label=label,
                            person_id=person.id,
                            role=rs.role,
                            confidence=rs.confidence,
                            method="deferred_resolve",
                            evidence={},
                        ))
                session.commit()
            logger.info(f"deferred_resolve: persisted {len(newly_resolved)} newly resolved speaker(s)")

        return updated

    def _step_enrich_parts(
        self, episode_id: int, parts: list[Part], transcript: TranscriptionResult
    ) -> dict:
        """Per-part enrichment: speaker stance analysis + Q&A extraction.

        Skips JINGLE / COMMERCIAL / NEWS parts (no discourse to analyze).
        Uses the transcript to attach segments to each part (parts from
        assemble_parts_from_chunks have no segments populated).
        Results are stored as JSON directly on the PartORM rows.
        """
        _SKIP_TYPES = {PartType.JINGLE, PartType.COMMERCIAL, PartType.NEWS}

        # Attach transcript segments to each part by time range.
        segs = sorted(transcript.segments, key=lambda s: s.start)
        enriched_parts: list[Part] = []
        for p in parts:
            if p.type in _SKIP_TYPES:
                continue
            part_segs = [s for s in segs if s.start >= p.start and s.end <= p.end + 1.0]
            enriched = Part(
                type=p.type,
                start=p.start,
                end=p.end,
                segments=part_segs,
                host_labels=p.host_labels,
                guest_labels=p.guest_labels,
                unknown_labels=p.unknown_labels,
            )
            enriched_parts.append((parts.index(p), enriched))

        logger.info(
            f"enrich_parts: {len(enriched_parts)} content part(s) "
            f"(skipping {len(parts) - len(enriched_parts)} boundary/news parts)"
        )

        # Run LLM analysis for each part (outside session — API calls can be slow).
        results: list[tuple[int, list, list]] = []  # (idx, speaker_analyses, qa_pairs)
        for idx, part in enriched_parts:
            speaker_analyses = self.speaker_part_analyzer.analyze(part)
            qa_pairs = self.qa_extractor.extract(part) if part.type == PartType.INTERVIEW else []
            results.append((idx, speaker_analyses, qa_pairs))

        # Persist all results in a single session.
        total_analyses = 0
        total_qa = 0
        with get_session() as session:
            orm_parts = (
                session.query(PartORM)
                .filter_by(episode_id=episode_id)
                .order_by(PartORM.idx)
                .all()
            )
            orm_by_idx = {row.idx: row for row in orm_parts}

            for idx, speaker_analyses, qa_pairs in results:
                orm_row = orm_by_idx.get(idx)
                if orm_row is None:
                    logger.warning(f"enrich_parts: no PartORM row for part idx={idx}, skipping")
                    continue
                orm_row.speaker_analyses = [a.model_dump() for a in speaker_analyses]
                orm_row.qa_pairs = [p.model_dump() for p in qa_pairs]
                total_analyses += len(speaker_analyses)
                total_qa += len(qa_pairs)

            session.commit()

        logger.info(
            f"enrich_parts complete: {total_analyses} speaker analyses, {total_qa} Q&A pairs"
        )
        return {"speaker_analyses": total_analyses, "qa_pairs": total_qa}

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
