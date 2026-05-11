#!/bin/bash
#
# Re-analyze an existing episode (re-run speaker identification).
#
# Usage:
#   sbatch --export=EPISODE_ID=1 slurm/reanalyze.slurm
#

#SBATCH --job-name=tsa-reanalyze
#SBATCH --time=0:30:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/reanalyze_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/reanalyze_%j.err

set -e

# Defaults
EPISODE_ID="${EPISODE_ID:-1}"

echo "=========================================="
echo "RE-ANALYZE EPISODE"
echo "=========================================="
echo "Episode ID   : $EPISODE_ID"
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

mkdir -p slurm_logs

python << EOF
import sys
from loguru import logger
from talk_show_analyzer.identification import UnifiedSpeakerIdentifier
from scripts.reidentify_speakers import reidentify_episode

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | {time:HH:mm:ss} | {message}",
)

try:
    identifier = UnifiedSpeakerIdentifier()
    reidentify_episode(identifier, ${EPISODE_ID})
    logger.info(f"✓ Episode ${EPISODE_ID} re-analyzed")
except Exception as e:
    logger.error(f"✗ Re-analysis failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

echo ""
echo "=========================================="
echo "Job completed at $(date)"
echo "=========================================="
