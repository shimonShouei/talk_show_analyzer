#!/bin/bash
#
# E2E test SLURM script for validation.
#
# Usage:
#   sbatch slurm/run_e2e_test.slurm
#

#SBATCH --job-name=tsa-e2e-test
#SBATCH --time=0:45:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/e2e_test_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/e2e_test_%j.err

set -e

echo "=========================================="
echo "E2E VALIDATION TEST"
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

mkdir -p slurm_logs

python tests/test_e2e.py

echo ""
echo "=========================================="
echo "Test completed at $(date)"
echo "=========================================="
