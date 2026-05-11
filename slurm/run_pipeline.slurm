#!/bin/bash
#
# Parameterized SLURM script for the talk-show-analyzer pipeline.
#
# Usage:
#   sbatch --export=STATION=103fm,DURATION=600 slurm/run_pipeline.slurm
#   sbatch --export=STATION=kan_bet,DURATION=1800 slurm/run_pipeline.slurm
#
# Parameters (passed via --export):
#   STATION     — 103fm, galatz, or kan_bet (default: 103fm)
#   DURATION    — Duration in seconds (default: 600 = 10 minutes)
#   OUTPUT_DIR  — Output directory (default: data/e2e_<STATION>_<DURATION>)
#

#SBATCH --job-name=tsa-pipeline
#SBATCH --time=1:00:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/pipeline_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/pipeline_%j.err

set -e

# Defaults
STATION="${STATION:-103fm}"
DURATION="${DURATION:-600}"
OUTPUT_DIR="${OUTPUT_DIR:-data/e2e_${STATION}_${DURATION}}"

STATION_NAME=""
case "$STATION" in
    103fm) STATION_NAME="103FM" ;;
    galatz) STATION_NAME="Galatz" ;;
    kan_bet) STATION_NAME="Kan Reshet Bet" ;;
    *) echo "Invalid STATION: $STATION"; exit 1 ;;
esac

DURATION_MIN=$((DURATION / 60))

echo "=========================================="
echo "TALK SHOW ANALYZER PIPELINE"
echo "=========================================="
echo "Station      : $STATION_NAME ($STATION)"
echo "Duration     : $DURATION_MIN minutes ($DURATION seconds)"
echo "Output dir   : $OUTPUT_DIR"
echo "Job started at $(date)"
echo "Node: $(hostname) | GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi | head -20
echo "=========================================="

cd /home/shouei/talk_show_analyzer

source /storage/modules/packages/anaconda/etc/profile.d/conda.sh
conda activate talk_show
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
echo "Python: $(python --version) at $(which python)"
echo ""

mkdir -p slurm_logs "$OUTPUT_DIR"

python << EOF
import sys
from pathlib import Path
from loguru import logger

from talk_show_analyzer.db import init_db
from talk_show_analyzer.pipeline import PipelineOrchestrator

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {time:HH:mm:ss} | {message}",
)

logger.info("\n" + "=" * 70)
logger.info(f"PIPELINE: {STATION_NAME}")
logger.info(f"Duration: {DURATION_MIN} min | Station: {STATION}")
logger.info("Steps: record → transcribe → identify_speakers → topics → store")
logger.info("=" * 70 + "\n")

init_db()
logger.info("✓ Database initialized\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run(
        station="${STATION}",
        duration_seconds=${DURATION},
        output_dir=Path("${OUTPUT_DIR}"),
    )

    logger.info("\n" + "=" * 70)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Episode ID  : {episode.id}")
    logger.info(f"  Status      : {episode.status}")
    logger.info(f"  Duration    : {episode.duration:.1f}s ({episode.duration/60:.1f} min)")
    logger.info(f"  Words       : {episode.word_count}")
    logger.info(f"  Segments    : {len(episode.segments)}")

    seg_by_type = {}
    for s in episode.segments:
        seg_by_type[s.type] = seg_by_type.get(s.type, 0) + 1
    for t, c in sorted(seg_by_type.items()):
        logger.info(f"    {t}: {c}")

    from talk_show_analyzer.db import get_session
    from talk_show_analyzer.models import SpeakerIdentity
    with get_session() as session:
        identities = (
            session.query(SpeakerIdentity)
            .filter(SpeakerIdentity.episode_id == episode.id)
            .all()
        )
        logger.info(f"  Speaker Identities ({len(identities)} total)")

    logger.info("")

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
