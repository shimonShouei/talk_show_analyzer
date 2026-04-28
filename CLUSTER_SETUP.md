# Cluster Setup Guide

Instructions for running the talk show analyzer on your GPU cluster.

## Prerequisites

- Python 3.10+
- NVIDIA GPU (with CUDA 11.0+)
- FFmpeg
- Internet access (for stream capture and HuggingFace models)

## 1. Copy Code to Cluster

```bash
scp -r . user@cluster:/path/to/talk_show_analyzer
ssh user@cluster
cd /path/to/talk_show_analyzer
```

## 2. Create HuggingFace Token

1. Go to https://huggingface.co/settings/tokens
2. Create a new token (read access is enough)
3. Copy the token

## 3. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install project + dependencies
pip install -e .

# Install ffmpeg (if not already installed)
sudo apt-get update && sudo apt-get install ffmpeg
```

## 4. Configure Environment

```bash
cp .env.example .env
nano .env
```

Set:
```
HF_TOKEN=hf_your_token_from_step_2
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
PYANNOTE_DEVICE=cuda
```

## 5. Test Setup

```bash
# Check if CUDA is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Run E2E test: record from live stream → transcribe
python test_e2e.py
```

This will:
1. Check Israeli radio stream health
2. Record 5 minutes from the first healthy stream
3. Transcribe using Faster-Whisper
4. Perform speaker diarization
5. Save results to `test_output/`

## 6. Troubleshooting

### ffmpeg not found
```bash
sudo apt-get install ffmpeg
```

### CUDA errors
```bash
# Check CUDA is available
nvidia-smi

# Check PyTorch sees GPU
python -c "import torch; print(torch.cuda.is_available())"
```

### HuggingFace token errors
```bash
# Set HF_TOKEN directly
export HF_TOKEN=hf_your_token

# Or add to .env file (it will be auto-loaded)
```

### Stream connection errors
```bash
# Check if streams are accessible
python -c "from talk_show_analyzer.recorder import check_all_streams; check_all_streams()"

# Try curl to debug
curl -H "Referer: https://glfrp.glz.co.il/" https://glzwizzlv.bynetcdn.com/glz_mp3 -I
```

### Out of memory during transcription
- Try smaller model: `WHISPER_MODEL=tiny` or `small`
- Or reduce audio quality (increase chunk size)

## 7. Expected Performance

With NVIDIA GPU:

| Model | VRAM | Speed | Quality |
|-------|------|-------|---------|
| tiny  | 1GB  | 20x realtime | Low |
| base  | 2GB  | 8x realtime | Good |
| small | 4GB  | 6x realtime | Very Good |
| medium | 6GB | 2x realtime | Excellent |
| large | 8GB+ | 1x realtime | Best |

For 4 hours of audio with `base` model: ~30 min with GPU, ~4-5 hours with CPU-only.

## 8. Running in Production

Once tested locally, you can:

1. Schedule recordings via cron:
```bash
0 5 * * * cd /path && python -m talk_show_analyzer.scripts.run_pipeline
```

2. Or use cluster job scheduler (SLURM, etc):
```bash
sbatch run_pipeline.sh
```

3. Set up PostgreSQL for storing results
4. Deploy Streamlit dashboard on a web server

See main README.md for full pipeline architecture.
