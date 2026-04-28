# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

**Setup (using conda — pip on this cluster is too slow for PyTorch):**
```bash
# Create conda env with prebuilt PyTorch + CUDA
conda create -n talk_show -y python=3.11 pytorch torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
conda activate talk_show

# ffmpeg is required for stream recording
conda install -y -c conda-forge ffmpeg

# Install project + remaining deps
pip install -e . --no-cache-dir

# IMPORTANT: conda libstdc++ is needed at runtime (system one is too old)
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Configure .env
cp .env.example .env  # Add HF_TOKEN, DATABASE_URL, ANTHROPIC_API_KEY
```

**Run E2E test (record + transcribe 5 min from Israeli radio):**
```bash
# Local (needs GPU)
python test_e2e.py

# Submit to SLURM cluster
sbatch .claude/run_gpu_test.slurm
```

**Validate setup:**
```bash
python test_gpu_setup.py
```

**Code quality:**
```bash
black src/
ruff check src/
mypy src/
```

## Project Overview

**Israeli Talk Show Analyzer** — Daily automated recording, transcription, and analysis of Israeli radio talk shows (Galatz, 103FM, Kan Reshet Bet). Pipeline:

1. **Recording**: ffmpeg captures audio from 3 stations
2. **Transcription**: Faster-Whisper (free, self-hosted) for Hebrew + Pyannote diarization
3. **Chunking**: Long recordings split into 25-min pieces
4. **Analysis**: Claude API for guests, topics, sentiment, political leaning (TODO)
5. **Storage**: PostgreSQL (TODO)
6. **Dashboard**: Streamlit (TODO)

## Architecture & Key Modules

**`src/talk_show_analyzer/`**:

- **`config.py`** — Pydantic `Settings` from env vars (DATABASE_URL, HF_TOKEN, ANTHROPIC_API_KEY)
- **`transcription/`**:
  - `transcriber.py` — `Transcriber` class: Faster-Whisper + Pyannote diarization. Returns `TranscriptionResult` with `segments: list[SpeakerSegment]`.
  - `chunker.py` — `chunk_audio()` splits long files into 25-min pieces with 1-min overlap
- **`recorder/`**:
  - `capture.py` — `record_station(station, output_path, duration_seconds)` via ffmpeg with custom Referer/User-Agent headers (bypasses geo-blocking)
  - `streams.py` — Registry of Galatz, Kan Bet, 103FM with health checks
- **`analysis/`, `dashboard/`, `pipeline/`, `reports/`, `models/`** — Empty placeholders (see `PLAN.md`)

## SLURM Cluster Notes (BGU)

**GPU types available** (from `sinfo -o "%P %N %G"`):
- `gtx_1080`, `rtx_2080`, `rtx_3090`, `rtx_4090`, `rtx_6000`, `rtx_pro_6000`

**⚠️ GTX 1080 / TITAN Xp won't work** — Pascal architecture (sm_61) is unsupported by PyTorch 2.11. Request `rtx_3090` or newer.

**Submit job:**
```bash
sbatch .claude/run_gpu_test.slurm  # Edit GPU type/walltime in script header
```

**Monitor:**
```bash
squeue -u $USER -l
tail -f slurm_logs/job_<JOBID>.out
scancel <JOBID>
```

**E2E benchmark:** RTX 3090 transcribes 5 min of audio + records in ~4.5 min total.

## Important Constraints & Patterns

**Conda env over pip-only**: PyTorch + CUDA via conda's prebuilt binaries (~5 min). Pure pip on the cluster takes ~2 hr (slow network) and frequently hits disk quota issues with `~/.cache/pip`.

**libstdc++ mismatch**: System `libstdc++.so.6` is older than what conda packages need (missing `CXXABI_1.3.15`). Always set `LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH` after activating env, or imports of `optuna` / `pyannote` fail.

**HuggingFace token required for Pyannote**: Without `HF_TOKEN`, diarization silently falls back to single-speaker (`SPEAKER_00`). See `transcriber.py` line 86.

**Stream recording requires Israeli IP**: BGU cluster has Israeli IP, so streams work directly. From other clouds you'd need a VPS relay.

**Whisper compute_type**: Use `float16` on RTX 3090+ (Ampere). Older GPUs (Pascal sm_61) don't support efficient fp16 — would need `int8` or `float32`.

**Logging**: Project uses `loguru` (not stdlib). All modules import `logger` from loguru.

## Codebase Maturity

✅ Transcription + diarization (working)
✅ Recording from streams (working — verified on Galatz)
✅ SLURM job submission (working — `.claude/run_gpu_test.slurm`)
⏳ Analysis modules (TODO — Claude prompts for guests/topics/sentiment)
⏳ Pipeline orchestration (TODO)
⏳ Database layer (TODO)
⏳ Dashboard (TODO)

See `PLAN.md` for full roadmap and `NEXT_STEPS.md` for prioritized next actions.

## Dependencies & Key Libraries

- **Audio**: `faster-whisper`, `pyannote.audio`, `librosa`, `pydub`, `ffmpeg` (system)
- **GPU**: `torch>=2.11`, `torchaudio`, CUDA 12.1+
- **Database**: `sqlalchemy>=2.0`, `psycopg2-binary` (PostgreSQL)
- **LLM**: `anthropic>=0.28.0`
- **Config**: `pydantic>=2.0`, `pydantic-settings`, `python-dotenv`
- **Dashboard**: `streamlit`, `plotly`, `pandas`
- **Logging**: `loguru`
