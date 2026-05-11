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

**Run tests:**
```bash
# Complete E2E pipeline test with dashboard
python tests/test_e2e.py

# GPU environment validation
python tests/test_gpu_setup.py

# Submit to SLURM cluster
sbatch slurm/run_gpu_test.slurm
sbatch --export=STATION=103fm,DURATION=900 slurm/run_pipeline.slurm
```

**Dashboard:**
```bash
python scripts/run_dashboard.py
```

**Database configuration:**
```bash
# Local testing (default in .env.example — SQLite, no server needed)
DATABASE_URL=sqlite:///./talk_show.db

# Production (when PostgreSQL is available)
DATABASE_URL=postgresql://user:password@db-host/talk_show_analyzer
```

⚠️ **Database setup**: `.env` is in `.gitignore` and must be created locally. For SLURM jobs, use SQLite (`sqlite:///./talk_show.db`) since compute nodes cannot easily reach external database servers. For production, switch to PostgreSQL and ensure the database server is accessible from the cluster.

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
  - `downloader.py` — `download_episode(url, output_path, ...)` downloads a recorded episode from any URL; uses ffmpeg by default (supports HLS/RTMP/direct files), falls back to plain HTTP
  - `streams.py` — Registry of Galatz, Kan Bet, 103FM with health checks
- **`analysis/`** — Thematic analysis (active) + legacy modules (deprecated)
  - `thematic_analyzer.py` — ⭐ Active: 3-stage topic-first intelligence
  - `legacy/` — Deprecated: segmenter, topics, sentiment, guests, ads (kept for reference)
  - `utils.py` — Shared utilities (sliding window functions)
  - `prompts/` — Claude API prompt templates
- **`identification/`** — Speaker re-identification across episodes
- **`dashboard/`** — Streamlit multi-page app (Overview, Episodes, Guests, Topics, Sentiment)
- **`pipeline/`** — Orchestrator with checkpoint-based recovery, database persistence
- **`db.py`** — SQLAlchemy engine + session management

**Tests, scripts, and SLURM jobs** (organized in dedicated directories):
- **`tests/`** — Test suite with shared fixtures
- **`scripts/`** — Utility scripts (dashboard launcher, reidentify, examples)
- **`slurm/`** — Parameterized SLURM job templates

## SLURM Cluster Notes (BGU)

**GPU types available** (from `sinfo -o "%P %N %G"`):
- `gtx_1080`, `rtx_2080`, `rtx_3090`, `rtx_4090`, `rtx_6000`, `rtx_pro_6000`

**⚠️ GTX 1080 / TITAN Xp won't work** — Pascal architecture (sm_61) is unsupported by PyTorch 2.11. Request `rtx_3090` or newer.

**Submit job:**
```bash
# GPU validation
sbatch slurm/run_gpu_test.slurm

# Main pipeline: 103FM for 15 minutes
sbatch --export=STATION=103fm,DURATION=900 slurm/run_pipeline.slurm

# Kan Bet for 30 minutes
sbatch --export=STATION=kan_bet,DURATION=1800 slurm/run_pipeline.slurm

# E2E test
sbatch slurm/run_e2e_test.slurm

# Re-analyze episode 2
sbatch --export=EPISODE_ID=2 slurm/reanalyze.slurm
```

See `.claude/SLURM_MIGRATION.md` for detailed parameter documentation.

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

**Pyannote diarization (v4)**: Requires `HF_TOKEN` for auth (without it, falls back to single-speaker). Pinned to `pyannote.audio>=4.0,<5.0` with model `pyannote/speaker-diarization-community-1` — older `speaker-diarization-3.x` checkpoints fail with a Cholesky error under v4 runtime. Audio is pre-decoded to a `{"waveform", "sample_rate"}` dict before being passed to the pipeline; feeding MP3 paths directly trips a sample-count guard (~158895 vs expected 160000 at 16 kHz). The pipeline returns `DiarizeOutput`; iterate via `output.exclusive_speaker_diarization.itertracks(yield_label=True)`.

**Stream recording requires Israeli IP**: BGU cluster has Israeli IP, so streams work directly. From other clouds you'd need a VPS relay.

**Whisper compute_type**: Use `float16` on RTX 3090+ (Ampere). Older GPUs (Pascal sm_61) don't support efficient fp16 — would need `int8` or `float32`.

**Logging**: Project uses `loguru` (not stdlib). All modules import `logger` from loguru.

**Database connectivity**: SQLAlchemy supports both SQLite and PostgreSQL. For local development and SLURM testing, use SQLite (`sqlite:///./talk_show.db`); it creates a local `.db` file with no server. For production, PostgreSQL provides persistence and concurrency but requires network access — on SLURM, ensure the database server hostname is resolvable from compute nodes or use SQLite as a fallback. The database URL is configured via `.env`, which is gitignored and must be created per environment.

## Codebase Maturity

✅ Transcription + diarization v4 (working — Pyannote community model)
✅ Recording from streams (working — verified on Galatz with geo-blocking bypass)
✅ Episode download by URL (working — `downloader.py`, ffmpeg + HTTP fallback)
✅ SLURM job submission (working — parameterized templates in `slurm/`)
✅ Analysis modules (working — Claude Sonnet for segmentation/topics/guests/sentiment/thematic)
✅ Pipeline orchestration (working — full E2E with checkpoint recovery)
✅ Database layer (working — SQLAlchemy with SQLite for testing, PostgreSQL for production)
✅ Dashboard (working — Streamlit multi-page with 5 analysis views)
✅ Speaker re-identification (working — clustering utility across episodes)
⏳ Daily automation (TODO — CLI + SLURM job for 3 stations in parallel)
⏳ Political leaning (TODO — Claude Opus classifier with Israeli context)

See `PLAN.md` for full roadmap and `NEXT_STEPS.md` for prioritized next actions.

## Dependencies & Key Libraries

- **Audio**: `faster-whisper`, `pyannote.audio`, `librosa`, `pydub`, `ffmpeg` (system)
- **GPU**: `torch>=2.11`, `torchaudio`, CUDA 12.1+
- **Database**: `sqlalchemy>=2.0`, `psycopg2-binary` (PostgreSQL)
- **LLM**: `anthropic>=0.28.0`
- **Config**: `pydantic>=2.0`, `pydantic-settings`, `python-dotenv`
- **Dashboard**: `streamlit`, `plotly`, `pandas`
- **Logging**: `loguru`
