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
from pathlib import Path
from loguru import logger

from talk_show_analyzer.db import init_db
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
        # Record 5 minutes from the first available station
        episode = orchestrator.run(
            station="galatz",
            duration_seconds=300,  # 5 minutes for testing
            output_dir=output_dir,
        )

        logger.info(f"\n✅ Pipeline complete!")
        logger.info(f"   Episode ID: {episode.id}")
        logger.info(f"   Status: {episode.status}")
        logger.info(f"   Segments: {len(episode.segments)}")
        logger.info(f"   Topics: {sum(len(s.topics) for s in episode.segments)}")
        logger.info(f"   Guests: {sum(len(s.guest_appearances) for s in episode.segments)}\n")

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Launch dashboard
    logger.info("=" * 70)
    logger.info("LAUNCHING DASHBOARD")
    logger.info("=" * 70 + "\n")

    logger.info("🚀 Starting Streamlit dashboard...\n")
    logger.info("📊 Dashboard URL: http://localhost:8501\n")
    logger.info("   - Overview: Daily metrics & summary")
    logger.info("   - Episodes: Browse & filter episodes")
    logger.info("   - Guests: Top speakers leaderboard")
    logger.info("   - Topics: Trending topics & sentiment")
    logger.info("   - Sentiment: Emotional tone analysis\n")
    logger.info("Press Ctrl+C to stop\n")

    try:
        subprocess.run(
            [
                "streamlit",
                "run",
                "src/talk_show_analyzer/dashboard/app.py",
                "--logger.level=warning",
            ],
            check=False,
        )
    except KeyboardInterrupt:
        logger.info("\n✓ Dashboard closed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
