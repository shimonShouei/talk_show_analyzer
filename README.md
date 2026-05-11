# Israeli Talk Show Analyzer

Automated daily recording, transcription, and analysis of Israeli radio talk shows (Galatz, 103FM, Kan Reshet Bet).

## Key Features

- **Free speech-to-text**: Faster-Whisper + Pyannote (self-hosted, no API costs)
- **Hebrew support**: Native transcription and analysis
- **Speaker identification**: Automatic diarization + re-identification across episodes
- **Episode download**: Fetch recorded episodes from any URL (HLS, direct MP3, etc.)
- **Analysis**: Guest identification, topic/thematic extraction, sentiment analysis
- **Dashboard**: Streamlit multi-page visualization (overview, episodes, guests, topics, sentiment)
- **Pipeline**: Checkpoint-based orchestration with database persistence

## Architecture

```
[Cron 05:50 IST] → [Record 3 streams via ffmpeg ~4hrs]  OR  [Download episode by URL]
    → [Chunk audio into 25-min pieces]
    → [Faster-Whisper transcription (Hebrew) + Pyannote diarization]
    → [Claude API analysis: segments, guests, topics, sentiment]
    → [Store in SQLite / PostgreSQL]
    → [Streamlit dashboard]
```

**Cost**: ~$16-22/day (Claude API only; transcription is free and self-hosted)

## Setup

### Prerequisites

- Python 3.11 (conda env recommended — see cluster notes below)
- NVIDIA GPU recommended (RTX 3090+ for fp16; CPU-only is ~10x slower)
- HuggingFace account (free, for Pyannote models)
- Anthropic API key (for Claude analysis)
- ffmpeg (for recording and download)

### Install (conda — recommended on clusters)

```bash
conda create -n talk_show -y python=3.11 pytorch torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
conda activate talk_show
conda install -y -c conda-forge ffmpeg
pip install -e . --no-cache-dir

# Required at runtime on clusters with older system libstdc++
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

cp .env.example .env  # Fill in HF_TOKEN, DATABASE_URL, ANTHROPIC_API_KEY
```

### Database

```bash
# Local / SLURM (no server needed)
DATABASE_URL=sqlite:///./talk_show.db

# Production
DATABASE_URL=postgresql://user:password@db-host/talk_show_analyzer
```

## Usage

### Record a live stream

```python
from talk_show_analyzer.recorder import record_station

record_station("103fm", "output.mp3", duration_seconds=3600)
```

### Download a recorded episode

```python
from talk_show_analyzer.recorder import download_episode

# Works with HLS playlists, direct MP3/M4A links, and most media URLs
download_episode(
    url="https://example.com/episode.mp3",
    output_path="episode.mp3",
    referer="https://example.com",  # optional, for geo-gated pages
    use_ffmpeg=True,                 # False → plain HTTP download
)
```

### Transcribe

```python
from talk_show_analyzer.transcription import Transcriber

transcriber = Transcriber(model_size="base", device="auto", enable_diarization=True)
result = transcriber.transcribe_file("episode.mp3", language="he")
print(f"{result.duration/60:.1f} min, {len(result.segments)} segments")
```

### Chunk long recordings

```python
from talk_show_analyzer.transcription import chunk_audio

chunks = chunk_audio("long_recording.mp3", chunk_duration_seconds=1500, overlap_seconds=60)
```

## Project Structure

```
talk_show_analyzer/
├── src/talk_show_analyzer/
│   ├── config.py                   # Pydantic settings (env vars)
│   ├── recorder/
│   │   ├── capture.py              # Live stream recording via ffmpeg
│   │   ├── downloader.py           # Download recorded episodes by URL
│   │   └── streams.py              # Station registry + health checks
│   ├── transcription/
│   │   ├── transcriber.py          # Faster-Whisper + Pyannote diarization
│   │   ├── chunker.py              # Audio chunking (25-min pieces, 1-min overlap)
│   │   └── speaker_linking.py      # Cross-chunk speaker label merging
│   ├── analysis/
│   │   ├── thematic_analyzer.py    # ⭐ Active: topic-first 3-stage analyzer
│   │   ├── utils.py                # Shared utilities (sliding windows)
│   │   ├── legacy/                 # Deprecated: old pipeline (segmenter, topics, sentiment, guests, ads)
│   │   └── prompts/                # Prompt templates for Claude API
│   ├── identification/
│   │   └── llm_identifier.py       # Speaker re-identification across episodes
│   ├── pipeline/
│   │   ├── orchestrator.py         # End-to-end pipeline with checkpoint recovery
│   │   └── store.py                # Database persistence
│   ├── dashboard/                  # Streamlit multi-page app
│   ├── models/                     # SQLAlchemy ORM models
│   └── db.py                       # SQLAlchemy engine + session
├── tests/                          # Test suite
│   ├── conftest.py                 # Shared fixtures (transcript loading)
│   ├── test_analysis.py            # Legacy pipeline tests
│   ├── test_dashboard.py           # Dashboard validation
│   ├── test_e2e.py                 # Full E2E pipeline test
│   └── test_speaker_*.py           # Speaker identification tests
├── scripts/                        # Utility scripts
│   ├── run_dashboard.py            # Streamlit dashboard launcher
│   ├── reidentify_speakers.py      # Re-run speaker ID on existing episodes
│   └── example_transcribe.py       # Transcription example
├── slurm/                          # ⭐ Parameterized SLURM job templates
│   ├── run_pipeline.slurm          # Main pipeline (station + duration)
│   ├── run_e2e_test.slurm          # E2E test validation
│   ├── run_gpu_test.slurm          # GPU environment check
│   └── reanalyze.slurm             # Re-analyze episode
├── .claude/                        # Claude Code settings
├── alembic/                        # Database migrations
├── pyproject.toml
├── CLAUDE.md                       # Project guide for Claude Code
└── .env.example
```

## Running on SLURM (BGU Cluster)

```bash
# Run main pipeline: record 103FM for 15 minutes
sbatch --export=STATION=103fm,DURATION=900 slurm/run_pipeline.slurm

# Run Kan Bet for 30 minutes
sbatch --export=STATION=kan_bet,DURATION=1800 slurm/run_pipeline.slurm

# Run E2E tests
sbatch slurm/run_e2e_test.slurm

# Check GPU setup
sbatch slurm/run_gpu_test.slurm

# Re-analyze episode 5
sbatch --export=EPISODE_ID=5 slurm/reanalyze.slurm

# Monitor jobs
squeue -u $USER -l
tail -f slurm_logs/pipeline_<JOBID>.out
```

See `.claude/SLURM_MIGRATION.md` for detailed parameter documentation.

**Supported GPUs**: RTX 3090, 4090, 6000, RTX Pro 6000. GTX 1080 and TITAN Xp (Pascal, sm_61) are unsupported.

## Code Quality

```bash
black src/
ruff check src/
mypy src/
```

## FAQ

**Do I need a GPU?** GPU is highly recommended. RTX 3090 transcribes 5 min of audio in ~4.5 min total (recording + transcription). CPU-only would take ~30-40 min for 4 hrs of audio.

**What about accuracy?** Faster-Whisper matches OpenAI Whisper API quality. Hebrew: ~95-98% character accuracy on clear studio speech. Diarization: ~90-95% for 2-4 speakers in clean audio.

**Can I download instead of record live?** Yes — use `download_episode()` for any podcast/archive URL. It supports HLS playlists and direct file links via ffmpeg.

**Will this work from outside Israel?** Recording live streams requires an Israeli IP (BGU cluster works directly). For episode downloads, a standard IP is usually sufficient.

## References

- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
- [Pyannote speaker diarization](https://github.com/pyannote/pyannote-audio)
- [HuggingFace models](https://huggingface.co/pyannote)
