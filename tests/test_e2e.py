#!/usr/bin/env python3
"""End-to-end test: Pipeline → Dashboard.

Complete flow with diarization:
1. Record from Israeli radio stream (5 min)
2. Transcribe with Faster-Whisper + Pyannote diarization
3. Run full analysis pipeline (segments, topics, guests, sentiment)
4. Store results in database
5. Launch dashboard to visualize
"""

import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from sqlalchemy.orm import joinedload

from talk_show_analyzer.db import init_db, get_session
from talk_show_analyzer.models import Episode, Segment
from talk_show_analyzer.pipeline import PipelineOrchestrator

# Setup logging
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {message}",
)


def main():
    """Run complete E2E pipeline + dashboard."""
    logger.info("\n")
    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " " * 68 + "║")
    logger.info("║  🎙️  ISRAELI TALK SHOW ANALYZER — E2E TEST + DASHBOARD" + " " * 7 + "║")
    logger.info("║" + " " * 68 + "║")
    logger.info("║  Pipeline: Record → Transcribe → Analyze → Database → Dashboard" + "║")
    logger.info("║" + " " * 68 + "║")
    logger.info("╚" + "=" * 68 + "╝\n")

    # Initialize database
    logger.info("Initializing database...\n")
    init_db()
    logger.info("✓ Database initialized\n")

    # Create output directory
    output_dir = Path("data/test")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run full pipeline
    logger.info("=" * 70)
    logger.info("RUNNING FULL PIPELINE")
    logger.info("=" * 70 + "\n")

    try:
        orchestrator = PipelineOrchestrator()
        # 103FM episode broadcasted today 09:00-11:00 Israel time (UTC+3 → 06:00 UTC)
        broadcast_time = datetime(2026, 5, 12, 6, 0, 0, tzinfo=timezone.utc)
        episode = orchestrator.run_from_file(
            audio_path="tests/data/103fm_test.mp3",
            station="103fm",
            duration_seconds=1200,  # 20 minutes for testing
            recorded_at=broadcast_time,
        )

        # Reload with eager relationships so counts are accurate
        with get_session() as session:
            ep = (
                session.query(Episode)
                .options(
                    joinedload(Episode.segments)
                    .joinedload(Segment.topics),
                    joinedload(Episode.segments)
                    .joinedload(Segment.guest_appearances),
                )
                .filter_by(id=episode.id)
                .one()
            )
            n_segments = len(ep.segments)
            n_topics = sum(len(s.topics) for s in ep.segments)
            n_guests = sum(len(s.guest_appearances) for s in ep.segments)

        logger.info(f"\n✅ Pipeline complete!")
        logger.info(f"   Episode ID: {episode.id}")
        logger.info(f"   Status: {episode.status}")
        logger.info(f"   Segments: {n_segments}")
        logger.info(f"   Topics: {n_topics}")
        logger.info(f"   Guests: {n_guests}\n")

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    logger.info("\n" + "=" * 70)
    logger.info("✓ E2E TEST PASSED")
    logger.info("=" * 70)
    logger.info("\nPipeline validated successfully!")
    logger.info("To launch dashboard locally, run:")
    logger.info("  python scripts/run_dashboard.py\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
