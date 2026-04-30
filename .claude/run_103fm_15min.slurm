#!/bin/bash
#SBATCH --job-name=tsa-103fm-15min
#SBATCH --time=0:35:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.err
#SBATCH --begin=10:00:00

set -e

echo "=========================================="
echo "103FM 15-MIN PIPELINE - SLURM JOB"
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

# Run full pipeline on 103FM for 15 minutes
echo "Starting full pipeline for 103FM (15 min)..."
echo ""

python << 'EOF'
import sys
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
logger.info("103FM 15-MINUTE PIPELINE")
logger.info("=" * 70 + "\n")

# Initialize database
logger.info("Step 1: Initializing database...\n")
init_db()
logger.info("✓ Database initialized\n")

# Create output directory
output_dir = Path("data/103fm")
output_dir.mkdir(parents=True, exist_ok=True)

# Run pipeline
logger.info("=" * 70)
logger.info("Step 2: Running full pipeline")
logger.info("=" * 70 + "\n")
logger.info("Timeline:")
logger.info("  - Record: 15 min of audio (real-time)")
logger.info("  - Transcribe: Faster-Whisper + Pyannote (2-3 min on RTX 3090)")
logger.info("  - Analyze: Topics, guests, sentiment (2-3 min with Claude API)")
logger.info("  - Store: Persist to SQLite\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run(
        station="103fm",
        duration_seconds=900,  # 15 minutes
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
