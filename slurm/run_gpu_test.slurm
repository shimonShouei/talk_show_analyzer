#!/bin/bash
#
# GPU/CUDA environment validation.
#
# Usage:
#   sbatch slurm/run_gpu_test.slurm
#

#SBATCH --job-name=tsa-gpu-test
#SBATCH --time=0:05:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=2
#SBATCH --gres=gpu:rtx_3090:1
#SBATCH --output=/home/shouei/talk_show_analyzer/slurm_logs/gpu_test_%j.out
#SBATCH --error=/home/shouei/talk_show_analyzer/slurm_logs/gpu_test_%j.err

set -e

echo "=========================================="
echo "GPU ENVIRONMENT VALIDATION"
echo "=========================================="
echo "Job started at $(date)"
echo "Node: $(hostname)"
echo ""

nvidia-smi

cd /home/shouei/talk_show_analyzer

source /storage/modules/packages/anaconda/etc/profile.d/conda.sh
conda activate talk_show
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

echo ""
echo "Python environment:"
python --version
which python
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'GPU devices: {torch.cuda.device_count()}')"

echo ""
echo "✓ GPU test passed"
echo ""
echo "=========================================="
echo "Test completed at $(date)"
echo "=========================================="
