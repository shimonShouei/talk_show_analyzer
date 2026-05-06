#!/bin/bash
#SBATCH --job-name=tsa-e2e-10min
#SBATCH --time=0:45:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/e2e_10min_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/e2e_10min_%j.err

set -e

echo "=========================================="
echo "103FM 10-MIN E2E TEST"
echo "=========================================="
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

mkdir -p slurm_logs data/e2e_10min

python << 'EOF'
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
logger.info("E2E 10-MIN PIPELINE TEST")
logger.info("Station: 103FM | Duration: 10 min")
logger.info("Steps: record → transcribe → segment → identify_speakers → topics → sentiment → store")
logger.info("=" * 70 + "\n")

init_db()
logger.info("✓ Database initialized\n")

try:
    orchestrator = PipelineOrchestrator()
    episode = orchestrator.run(
        station="103fm",
        duration_seconds=600,  # 10 minutes
        output_dir=Path("data/e2e_10min"),
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

    logger.info(f"  Topics      : {sum(len(s.topics) for s in episode.segments)}")
    logger.info(f"  Sentiments  : {sum(len(s.sentiments) for s in episode.segments)}")

    # Speaker identification results
    from talk_show_analyzer.db import get_session
    from talk_show_analyzer.models import SpeakerIdentity, Person
    with get_session() as session:
        identities = (
            session.query(SpeakerIdentity)
            .filter(SpeakerIdentity.episode_id == episode.id)
            .all()
        )
        logger.info(f"\n  Speaker Identities ({len(identities)} total):")
        for si in identities:
            name = si.person.name_en if si.person else "Unknown"
            logger.info(f"    {si.speaker_label} → {name} ({si.role}, conf={si.confidence:.2f})")

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
