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

export TSA_STATION="$STATION"
export TSA_STATION_NAME="$STATION_NAME"
export TSA_DURATION="$DURATION"
export TSA_DURATION_MIN="$DURATION_MIN"
export TSA_OUTPUT_DIR="$OUTPUT_DIR"

python << 'EOF'
import os, sys
from pathlib import Path
from loguru import logger

from talk_show_analyzer.db import init_db
from talk_show_analyzer.pipeline import PipelineOrchestrator

station      = os.environ["TSA_STATION"]
station_name = os.environ["TSA_STATION_NAME"]
duration     = int(os.environ["TSA_DURATION"])
duration_min = int(os.environ["TSA_DURATION_MIN"])
output_dir   = Path(os.environ["TSA_OUTPUT_DIR"])

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {time:HH:mm:ss} | {message}",
)

logger.info("\n" + "=" * 70)
logger.info(f"PIPELINE: {station_name}")
logger.info(f"Duration: {duration_min} min | Station: {station}")
logger.info("Steps: record → transcribe → chunk_analyze → deferred_resolve → resolve_hosts → enrich_parts → store")
logger.info("=" * 70 + "\n")

init_db()
logger.info("✓ Database initialized\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run(
        station=station,
        duration_seconds=duration,
        output_dir=output_dir,
    )

    logger.info("\n" + "=" * 70)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Episode ID  : {episode.id}")
    logger.info(f"  Status      : {episode.status}")

    from talk_show_analyzer.db import get_session
    from talk_show_analyzer.models import SpeakerIdentity, PartORM, MergedTopic
    with get_session() as session:
        identities = session.query(SpeakerIdentity).filter_by(episode_id=episode.id).all()
        parts      = session.query(PartORM).filter_by(episode_id=episode.id).all()
        topics     = session.query(MergedTopic).filter_by(episode_id=episode.id).all()
        logger.info(f"  Speakers    : {len(identities)}")
        logger.info(f"  Parts       : {len(parts)} — " + ", ".join(p.type for p in parts))
        logger.info(f"  Topics      : {len(topics)}")

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
