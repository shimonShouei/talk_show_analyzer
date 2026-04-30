#!/bin/bash
#SBATCH --job-name=tsa-e2e-pipeline
#SBATCH --time=0:45:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.err

set -e

echo "=========================================="
echo "E2E PIPELINE TEST - SLURM JOB"
echo "=========================================="
echo "Job started at $(date)"
echo "Node: $(hostname) | GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi
echo "=========================================="

cd /home/shouei/talk_show_analyzer

# Activate conda env
source /storage/modules/packages/anaconda/etc/profile.d/conda.sh
conda activate talk_show
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
echo "Python: $(python --version) at $(which python)"
echo ""

# Create logs directory
mkdir -p slurm_logs

# Run E2E test (without dashboard since this is headless)
# Pipeline will record → transcribe → analyze → store in database
echo "Starting E2E pipeline (record → transcribe → analyze → database)..."
echo ""

python << 'EOF'
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

logger.info("\n" + "=" * 70)
logger.info("E2E PIPELINE TEST ON SLURM")
logger.info("=" * 70 + "\n")

# Initialize database
logger.info("Step 1: Initializing database...\n")
init_db()
logger.info("✓ Database initialized\n")

# Create output directory
output_dir = Path("data/slurm_test")
output_dir.mkdir(parents=True, exist_ok=True)

# Run pipeline
logger.info("=" * 70)
logger.info("Step 2: Running full pipeline")
logger.info("=" * 70 + "\n")
logger.info("Timeline:")
logger.info("  - Record: 20 min of audio (real-time)")
logger.info("  - Transcribe: Faster-Whisper + Pyannote (4-5 min on RTX 3090)")
logger.info("  - Analyze: Topics, guests, sentiment (3-5 min with Claude API)")
logger.info("  - Store: Persist to SQLite\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run(
        station="galatz",
        duration_seconds=1200,  # 20 minutes
        output_dir=output_dir,
    )

    logger.info(f"\n" + "=" * 70)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("=" * 70 + "\n")
    logger.info(f"Episode ID: {episode.id}")
    logger.info(f"Status: {episode.status}")
    logger.info(f"Duration: {episode.duration:.1f}s")
    logger.info(f"Words: {episode.word_count}")
    logger.info(f"Segments: {len(episode.segments)}")
    logger.info(f"Topics: {sum(len(s.topics) for s in episode.segments)}")
    logger.info(f"Guests: {sum(len(s.guest_appearances) for s in episode.segments)}")
    logger.info(f"Sentiment results: {sum(len(s.sentiments) for s in episode.segments)}\n")

    logger.info("=" * 70)
    logger.info("NEXT STEPS")
    logger.info("=" * 70 + "\n")
    logger.info("1. View results in database:")
    logger.info(f"   psql $DATABASE_URL -c 'SELECT * FROM episodes WHERE id = {episode.id};'\n")

    logger.info("2. Launch dashboard locally:")
    logger.info("   python run_dashboard.py\n")

    logger.info("   Then navigate to: http://localhost:8501\n")

    logger.info("3. Check stored data:")
    logger.info("   - Episodes page: View the recorded episode")
    logger.info("   - Overview page: See key metrics and top guests")
    logger.info("   - Topics page: Browse extracted topics")
    logger.info("   - Sentiment page: Analyze emotional tone\n")

except Exception as e:
    logger.error(f"\n❌ Pipeline failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

echo ""
echo "=========================================="
echo "Job completed at $(date)"
echo "=========================================="
