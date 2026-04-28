#!/bin/bash
#SBATCH --job-name=tsa-gpu-test
#SBATCH --time=0:30:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/job_%j.err

set -e

echo "=========================================="
echo "Job started at $(date)"
echo "Node: $(hostname) | GPU: $CUDA_VISIBLE_DEVICES"
nvidia-smi -L
echo "=========================================="

cd /home/shouei/talk_show_analyzer

# Activate conda env
source /storage/modules/packages/anaconda/etc/profile.d/conda.sh
conda activate talk_show
# Use conda's newer libstdc++ instead of system's (fixes CXXABI_1.3.15 missing)
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
echo "Python: $(python --version) at $(which python)"

# Run full E2E test: record + transcribe
python test_e2e.py

echo ""
echo "Job completed at $(date)"
