# End-to-End Test Guide: Pipeline + Dashboard

Complete workflow test with real data from Israeli radio streams.

## Prerequisites

1. **Dependencies installed**: `pip install -e .`
2. **Database running**: PostgreSQL with `DATABASE_URL` set in `.env`
3. **Environment variables**:
   ```bash
   export DATABASE_URL="postgresql://user:pass@localhost:5432/talk_show"
   export HF_TOKEN="hf_xxxxx"  # For Pyannote diarization
   ```
4. **GPU available** (RTX 3090+ recommended for transcription + diarization)

## Quick Start

```bash
python test_e2e_with_dashboard.py
```

This runs the **complete pipeline** in one command:
1. ✅ Records 5 minutes of audio from Galatz stream
2. ✅ Transcribes with Faster-Whisper (large-v3) + Pyannote diarization
3. ✅ Analyzes content (segments, topics, guests, sentiment)
4. ✅ Stores results in database
5. ✅ Opens dashboard in browser

## What Happens Step-by-Step

### 1. Database Initialization
```
Initializing database...
✓ Database initialized
```

Creates PostgreSQL schema if not exists. Tables:
- `stations` — Radio stations (Galatz, 103FM, Kan Reshet Bet)
- `episodes` — Recording sessions
- `segments` — Content segments (interview, news, ads, etc.)
- `topics` — Extracted topics with categories
- `guests` — People appearing in shows
- `guest_appearances` — Guest-segment relationships
- `sentiment_results` — Sentiment analysis per speaker/topic
- `pipeline_runs` — Pipeline execution tracking

### 2. Pipeline Execution

The `PipelineOrchestrator` runs 7 steps with **checkpoint recovery**:

```
STEP 1: RECORD (5 minutes from Galatz)
  ├─ Check stream health
  ├─ Record audio via ffmpeg
  └─ Save to data/test/galatz_*.mp3

STEP 2: TRANSCRIBE (Faster-Whisper + Pyannote)
  ├─ Load Whisper model (large-v3)
  ├─ Load Pyannote diarization
  ├─ Process audio (speech-to-text + speaker labels)
  └─ Save JSON with speaker segments

STEP 3: SEGMENT (Content classification)
  ├─ Identify interview/panel/news/ad/jingle/music/callers
  ├─ 20-min windows with 2-min overlap
  └─ Generate summaries for each segment

STEP 4: TOPICS (Extract main topics)
  ├─ Identify topics per segment
  ├─ Extract subtopics and categories
  ├─ Bilingual output (Hebrew + English)
  └─ Store category: politics/security/economy/social/culture

STEP 5: GUESTS (Identify speakers)
  ├─ Map speaker labels to real names
  ├─ Extract title and affiliation
  ├─ Confidence scoring
  └─ Deduplication across speakers

STEP 6: SENTIMENT (Emotional analysis)
  ├─ Sentiment score per speaker per topic (-1.0 to +1.0)
  ├─ Tone classification (angry, calm, enthusiastic, etc.)
  ├─ Extract supporting quotes
  └─ Aggregate by segment

STEP 7: STORE (Persist to database)
  └─ Transaction commit for all results
```

Each step is **checkpointed** — if pipeline fails, rerun same command to resume from where it stopped.

### 3. Dashboard Launch

Opens Streamlit dashboard at http://localhost:8501

**5 Analysis Pages:**

| Page | Features |
|------|----------|
| **📊 Overview** | Daily metrics, top guests, trending topics, sentiment stats |
| **📺 Episodes** | Browse, filter by station/date/status, detailed view |
| **👥 Guests** | Leaderboard of appearances, bilingual names, titles |
| **🎯 Topics** | Trending topics, category distribution, sentiment trends |
| **💭 Sentiment** | Sentiment statistics, distribution by tone, scale view |

**Navigation**: Use Streamlit sidebar to switch pages

## Expected Results (5-min recording)

After running the test, you should see:

```
Episode ID: 1
Status: analyzed
Segments: ~15-20 (depends on content)
Topics: ~25-40
Guests: ~2-5 (typical morning show segment)
```

In the dashboard:
- ✅ Episode appears in "Episodes" page
- ✅ Guests listed in "Guest Leaderboard"
- ✅ Topics visible in "Topics" page with sentiment scores
- ✅ Overall metrics in "Overview" page

## Troubleshooting

### "No streams are healthy"
- Check network connection (need Israeli IP or VPN)
- Verify stream URLs in `src/talk_show_analyzer/recorder/streams.py`
- Try individual stream test: `python -c "from talk_show_analyzer.recorder import check_all_streams; print(check_all_streams())"`

### "Transcription failed"
- Ensure GPU is available: `nvidia-smi`
- Check HF_TOKEN for Pyannote: `echo $HF_TOKEN`
- Verify Whisper model: `find ~/.cache -name "large-v3*"`

### "Database connection refused"
- Start PostgreSQL: `pg_ctl -D /path/to/db start`
- Check DATABASE_URL: `echo $DATABASE_URL`
- Test connection: `psql $DATABASE_URL -c "SELECT 1"`

### "Claude API rate limit"
- Analysis uses Anthropic API (Sonnet + Opus models)
- Reduce segment count or increase wait time between requests
- Check rate limits: https://console.anthropic.com/

### "Dashboard shows no data"
- Verify episode was created: `SELECT COUNT(*) FROM episodes;`
- Check episode status: `SELECT status FROM episodes ORDER BY id DESC LIMIT 1;`
- Look for errors in orchestrator logs (watch for step failures)

## Advanced Usage

### Resume Failed Pipeline

If pipeline fails on step 5, resume from step 5:

```python
from talk_show_analyzer.pipeline import PipelineOrchestrator
orch = PipelineOrchestrator()
episode = orch.resume(episode_id=1)  # Resume from last successful step
```

### Process Multiple Stations

```bash
# Modify test_e2e_with_dashboard.py to run all 3 stations
for station in galatz 103fm kan_bet; do
    python test_e2e_with_dashboard.py --station $station
done
```

### Use Existing Transcript

Skip recording/transcription, just run analysis:

```python
from pathlib import Path
from talk_show_analyzer.pipeline import PipelineOrchestrator

orch = PipelineOrchestrator()
# Load from cached transcript
episode = orch.resume(episode_id=1)
```

### Measure Performance

Check pipeline timing in database:

```sql
SELECT step, 
       AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as duration_sec
FROM pipeline_runs
WHERE episode_id = 1
GROUP BY step;
```

## Performance Notes

**Typical timeline for 5 min recording (RTX 3090):**
- Record: ~5 min (real-time)
- Transcribe: ~2-3 min
- Segment: ~20 sec
- Topics: ~60 sec (Claude API)
- Guests: ~40 sec (Claude API)
- Sentiment: ~80 sec (Claude API)
- Store: ~5 sec
- **Total: ~12-14 minutes**

## Next Steps

After successful E2E test:

1. ✅ Verify diarization works (multiple speakers detected)
2. ✅ Check topic extraction quality (Hebrew topics readable)
3. ✅ Validate sentiment scores (-1.0 to +1.0 range)
4. ✅ Confirm database persistence (check Dashboard data)
5. 📋 Add more test data (run on multiple stations/times)
6. 🚀 Deploy to production

## Data Cleanup

Remove test data:

```bash
# Delete test output
rm -rf data/test test_output

# Clear test episodes from database
psql $DATABASE_URL -c "DELETE FROM episodes WHERE station_id = (SELECT id FROM stations WHERE name = 'galatz');"
```

## Documentation

- **CLAUDE.md** — Project setup & environment
- **PLAN.md** — Architecture & technical decisions
- **NEXT_STEPS.md** — Roadmap & completion status
- **DASHBOARD_SETUP.md** — Dashboard configuration & deployment
- **dashboard/README.md** — Dashboard architecture & features
