#!/bin/bash
#
# Run the talk-show-analyzer pipeline on an existing audio file.
# Skips the record step; starts from transcription (or resumes from checkpoint).
#
# Usage:
#   sbatch --export=AUDIO_PATH=/path/to/file.mp3,STATION=103fm,DURATION=1800 slurm/run_from_file.slurm
#
# Parameters (passed via --export):
#   AUDIO_PATH  — absolute path to the audio file (required)
#   STATION     — station name stored in DB: 103fm | kan_bet | galatz (default: unknown)
#   DURATION    — if set, trim the audio to this many seconds before processing
#

#SBATCH --job-name=tsa-from-file
#SBATCH --time=1:30:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/from_file_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/from_file_%j.err

set -e

STATION="${STATION:-unknown}"
DURATION="${DURATION:-}"

if [[ -z "$AUDIO_PATH" ]]; then
    echo "ERROR: AUDIO_PATH is required"; exit 1
fi

echo "=========================================="
echo "TALK SHOW ANALYZER — FROM FILE"
echo "=========================================="
echo "Audio file   : $AUDIO_PATH"
echo "Station      : $STATION"
echo "Trim to      : ${DURATION:-no trim} seconds"
echo "Job started  : $(date)"
echo "Node: $(hostname) | GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi | head -10
echo "=========================================="

cd /home/shouei/talk_show_analyzer

source /storage/modules/packages/anaconda/etc/profile.d/conda.sh
conda activate talk_show
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
echo "Python: $(python --version) at $(which python)"
echo ""

mkdir -p slurm_logs

export TSA_AUDIO_PATH="$AUDIO_PATH"
export TSA_STATION="$STATION"
export TSA_DURATION="${DURATION:-0}"

python << 'EOF'
import os, sys
from pathlib import Path
from loguru import logger

from talk_show_analyzer.db import init_db
from talk_show_analyzer.pipeline import PipelineOrchestrator

audio_path = Path(os.environ["TSA_AUDIO_PATH"])
station    = os.environ["TSA_STATION"]
duration   = int(os.environ["TSA_DURATION"])

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {time:HH:mm:ss} | {message}",
)

logger.info("\n" + "=" * 70)
logger.info(f"FROM-FILE PIPELINE: {audio_path.name}")
logger.info(f"Station: {station} | Trim: {duration or 'none'}s")
logger.info("Steps: transcribe → chunk_analyze → deferred_resolve → resolve_hosts → enrich_parts → store")
logger.info("=" * 70 + "\n")

init_db()
logger.info("✓ Database initialized\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run_from_file(
        audio_path=audio_path,
        station=station,
        duration_seconds=duration if duration > 0 else None,
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
        identified = sum(1 for i in identities if i.role != "unknown")
        parts_with_stance = sum(1 for p in parts if p.speaker_analyses)
        parts_with_qa     = sum(1 for p in parts if p.qa_pairs)
        logger.info(f"  Speakers    : {identified}/{len(identities)} identified")
        logger.info(f"  Parts       : {len(parts)} — " + ", ".join(p.type for p in parts))
        logger.info(f"  Topics      : {len(topics)}")
        logger.info(f"  Stance data : {parts_with_stance} parts enriched")
        logger.info(f"  Q&A pairs   : {parts_with_qa} interview parts with Q&A")
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
