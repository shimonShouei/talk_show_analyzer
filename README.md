# Israeli Talk Show Analyzer

Automated daily recording, transcription, and analysis of Israeli radio talk shows (Galatz, 103FM, Kan Reshet Bet).

## Key Features

- **Free speech-to-text**: Faster-Whisper + Pyannote (self-hosted, no API costs)
- **Hebrew support**: Native transcription and analysis in Hebrew
- **Speaker identification**: Automatic speaker diarization
- **Analysis**: Guest identification, topic extraction, sentiment analysis, political leaning assessment
- **Dashboard**: Streamlit-based visualization of trends and insights

## Architecture

```
[Cron 05:50 IST] → [Record 3 streams via ffmpeg ~4hrs]
    → [Chunk audio into 25-min pieces]
    → [Faster-Whisper transcription (Hebrew) + Pyannote diarization]
    → [Claude API analysis: segments, guests, topics, sentiment, political leaning]
    → [Store in PostgreSQL]
    → [Streamlit dashboard]
```

**Cost**: ~$16-22/day (Claude API only; transcription is free self-hosted)

## Setup

### 1. Prerequisites

- Python 3.10+
- PostgreSQL 13+
- NVIDIA GPU recommended (for faster Whisper/Pyannote inference)
  - CPU-only is possible but ~10x slower
- HuggingFace account (free, for Pyannote models)
- Anthropic API key (for Claude analysis, optional for testing)

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install project
pip install -e .
```

### 3. Setup Environment

```bash
cp .env.example .env
# Edit .env and fill in:
#   - DATABASE_URL (PostgreSQL)
#   - HF_TOKEN (from https://huggingface.co/settings/tokens)
#   - ANTHROPIC_API_KEY (optional, for analysis phase)
```

### 4. Download Models

Models are downloaded automatically on first use, but you can pre-download:

```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('base')"
python -c "from pyannote.audio import Pipeline; Pipeline.from_pretrained('pyannote/speaker-diarization-3.0', use_auth_token=True)"
```

**Model sizes** (Faster-Whisper):
- `tiny`: ~39M, ~16GB VRAM, ~4x real-time (fastest)
- `base`: ~140M, ~15GB VRAM, ~8x real-time (recommended)
- `small`: ~244M, ~24GB VRAM, ~6x real-time
- `medium`: ~769M, ~48GB VRAM, ~2x real-time
- `large`: ~1.5B, ~60GB VRAM, 1x real-time (best quality)

### 5. Quick Test

```bash
# Transcribe a sample Hebrew audio file
python example_transcribe.py
```

This will create a `transcript.json` with transcription + speaker segments.

## Usage

### Transcribe a file

```python
from talk_show_analyzer.transcription import Transcriber

transcriber = Transcriber(
    model_size="base",
    device="auto",      # Use GPU if available
    enable_diarization=True,
)

result = transcriber.transcribe_file(
    "sample_radio.mp3",
    output_json="transcript.json",
    language="he",
)

print(f"Transcribed {result.duration/60:.1f} min of audio")
print(f"Found {len(result.segments)} speaker segments")
```

### Chunk audio

For long files (>25 min), split into chunks first:

```python
from talk_show_analyzer.transcription import chunk_audio

chunks = chunk_audio(
    "long_recording.mp3",
    chunk_duration_seconds=1500,  # 25 min chunks
    overlap_seconds=60,            # 1 min overlap
)

for chunk_path in chunks:
    result = transcriber.transcribe_file(chunk_path, language="he")
```

## Project Structure

```
talk_show_analyzer/
├── src/talk_show_analyzer/
│   ├── config.py                 # Configuration (Pydantic)
│   ├── transcription/
│   │   ├── transcriber.py        # Faster-Whisper + Pyannote
│   │   ├── chunker.py            # Audio chunking
│   │   └── __init__.py
│   ├── recorder/                 # (TODO: Recording module)
│   ├── analysis/                 # (TODO: Analysis module)
│   └── pipeline/                 # (TODO: Pipeline orchestration)
├── pyproject.toml
├── .env.example
├── README.md
└── example_transcribe.py
```

## FAQ

### Q: Do I need a GPU?
**A:** GPU is highly recommended. With a GPU (RTX 4070), transcription runs 8-10x realtime. CPU-only would require ~30-40 min to transcribe 4 hrs of audio.

### Q: Will this work on a cloud instance?
**A:** Yes. For inference:
- AWS: `g4dn.xlarge` (NVIDIA T4) or `p3.2xlarge` (V100) — costs ~$0.50-1.00/hr
- Google Cloud: `n1-standard-4` with `NVIDIA T4`
- Self-hosted: Rent a GPU instance from Vast.ai, Lambda Labs, or Runpod

For recording streams (which need Israeli IP/headers), use an Israeli VPS relay or cloud region.

### Q: What about accuracy?
**A:** Faster-Whisper's accuracy is equivalent to the official OpenAI Whisper API. For Hebrew, expect ~95-98% character accuracy on formal speech.

Diarization accuracy (speaker identification) depends on:
- Number of speakers (2-4 speakers: ~90-95%, 5+ speakers: ~80-85%)
- Audio quality (clean studio audio: ~95%, noisy: ~70%)

### Q: Can I use CPU only?
**A:** Yes, but it will be very slow:
- `tiny` model: ~5 min to transcribe 1 min of audio
- `base` model: ~15-20 min per 1 min of audio

Not practical for daily 4-hour recordings without significant hardware.

### Q: How do I handle multiple chunks from a single show?
**A:** The pipeline will:
1. Transcribe each chunk independently
2. Merge diarization across chunks (cross-chunk speaker continuity)
3. Concatenate transcripts preserving timestamps

Speaker merging is handled via Pyannote's temporal continuity, so `SPEAKER_00` in chunk 1 becomes `SPEAKER_00` in chunk 2 if the same person speaks.

## Development

### Run tests

```bash
pytest tests/
```

### Code quality

```bash
black src/
ruff check src/
mypy src/
```

## Next Steps

1. **Phase 1B**: Implement `recorder/` module for streaming capture
2. **Phase 3**: Implement analysis modules (Claude-based segmentation, guest ID, sentiment, etc.)
3. **Phase 4**: Orchestrator + CLI
4. **Phase 5**: Streamlit dashboard
5. **Phase 6**: Cloud deployment (Terraform + Docker)

## References

- [Faster-Whisper docs](https://github.com/SYSTRAN/faster-whisper)
- [Pyannote speaker diarization](https://github.com/pyannote/pyannote-audio)
- [HuggingFace models](https://huggingface.co/pyannote)
