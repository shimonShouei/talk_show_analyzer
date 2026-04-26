# Israeli Talk Show Analyzer — Implementation Plan

## Context

Build a daily automated system that records morning talk shows from 3 Israeli radio stations (Galatz, 103FM, Kan Reshet Bet), transcribes them (Hebrew), and analyzes them for: guests, topics, ad time, sentiment per speaker/topic, and political leaning. Results displayed in a Streamlit dashboard. Deployed on cloud (AWS/GCP), designed as MVP that can grow into a product.

## Architecture Overview

```
[Cron 05:50 IST] → [Record 3 streams via ffmpeg ~4hrs]
    → [Chunk audio into 10-min pieces]
    → [Whisper API transcription (Hebrew)]
    → [Claude API analysis: segments, guests, topics, sentiment, political leaning]
    → [Store in PostgreSQL]
    → [Streamlit dashboard]
```

## Project Structure

```
talk_show_analyzer/
├── pyproject.toml
├── .env.example
├── alembic/                    # DB migrations
├── src/talk_show_analyzer/
│   ├── config.py               # Pydantic Settings
│   ├── models.py               # SQLAlchemy ORM models
│   ├── db.py                   # Engine/session factory
│   ├── recorder/
│   │   ├── streams.py          # Station URL registry + health checks
│   │   ├── capture.py          # ffmpeg stream recording
│   │   └── storage.py          # S3/GCS upload
│   ├── transcription/
│   │   ├── chunker.py          # Split audio into 10-min chunks
│   │   └── whisper_client.py   # Whisper API + context chaining
│   ├── analysis/
│   │   ├── segmenter.py        # Segment identification (interview/panel/news/ad)
│   │   ├── guests.py           # Guest identification + dedup
│   │   ├── topics.py           # Topic extraction per segment
│   │   ├── ads.py              # Ad time aggregation
│   │   ├── sentiment.py        # Sentiment per speaker per topic
│   │   ├── political.py        # Political leaning analysis
│   │   └── prompts/            # Claude prompt templates
│   ├── reports/
│   │   └── daily_summary.py    # Claude-generated daily report
│   ├── pipeline/
│   │   ├── orchestrator.py     # Main pipeline with checkpointing
│   │   └── retry.py            # Resume from last successful step
│   └── dashboard/
│       └── app.py              # Streamlit dashboard
├── scripts/
│   ├── run_pipeline.py         # CLI entry point
│   └── test_streams.py         # Verify stream URLs
├── tests/
├── infra/
│   ├── Dockerfile
│   ├── docker-compose.yml      # Local dev: postgres + app
│   └── terraform/
└── docs/
```

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | PostgreSQL | JSON columns for semi-structured data, mature, good Streamlit integration |
| Audio format | MP3 128kbps, 16kHz mono | Whisper's native rate, ~115MB per station per 4hrs |
| Transcription | OpenAI Whisper API | Best Hebrew accuracy, `language="he"`, chain context between chunks |
| NLP analysis | Claude Sonnet for bulk, Opus for political leaning | Cost-effective for volume, nuanced model for hardest task |
| Diarization | Deferred to Phase 7 | pyannote.audio needs GPU, MVP works without it |
| Scheduling | ECS Fargate / Cloud Run | Long-running recording task (4hrs) needs persistent compute |
| Object storage | S3/GCS | Raw audio by date/station, 30-day retention |

## Stream URLs (Known)

| Station | URL | Format |
|---------|-----|--------|
| Galatz | `https://glzwizzlv.bynetcdn.com/glz_mp3` | MP3/Icecast |
| Kan Bet | `https://kanlivep2event-i.akamaihd.net/hls/live/749624/749624/kanbet_mp3/chunklist.m3u8` | HLS |
| 103FM | Extract from 103fm.maariv.co.il player | Likely HLS |

## Data Models (Key Tables)

- **Station** — id, name, stream_url, show_start/end times
- **Recording** — station_id, date, audio_path (S3), duration, status
- **Transcript** — recording_id, raw_text, whisper_output (JSON), word_count
- **Segment** — transcript_id, type (interview/panel/news/ad/music), start/end time, summary
- **Guest** — name_he, name_en, title, affiliation, first_seen_date
- **Topic** — name_he, name_en, category
- **SegmentTopic** — segment_id, topic_id, sentiment_score, political_leaning
- **SpeakerSentiment** — segment_id, speaker_label, topic_id, sentiment, leaning, quotes
- **DailySummary** — station_id, date, ad_%, num_guests, overall_sentiment/leaning, summary_text
- **PipelineRun** — station_id, date, step, status, timestamps, error_message

## Implementation Phases

### Phase 1 — Scaffolding + Recording (build first)
1. Project setup: pyproject.toml, src layout, config.py, .env.example, .gitignore
2. `recorder/streams.py` — station URL registry with health checks
3. `recorder/capture.py` — ffmpeg subprocess wrapper
4. DB models + Alembic + docker-compose (Postgres)
5. Test: record 5 minutes of one station locally

### Phase 2 — Transcription
6. `transcription/chunker.py` — split audio into 10-min chunks (pydub)
7. `transcription/whisper_client.py` — Whisper API with context chaining
8. Test: transcribe 30 min of Hebrew audio, evaluate quality

### Phase 3 — Analysis
9. `analysis/segmenter.py` — segment identification via Claude
10. `analysis/topics.py` + `analysis/guests.py` — topic & guest extraction
11. `analysis/ads.py` — ad time from segment data
12. `analysis/sentiment.py` — sentiment per speaker per topic
13. `analysis/political.py` — political leaning (Israeli context in prompt)
14. `reports/daily_summary.py` — daily report generation
15. Store all results in PostgreSQL

### Phase 4 — Pipeline Orchestration
16. `pipeline/orchestrator.py` — chain all steps, checkpoint per step
17. `scripts/run_pipeline.py` — CLI with Click

### Phase 5 — Dashboard
18. Streamlit app: Daily Overview, Station Comparison, Topic Trends, Guest Log, Political Leaning Over Time
19. Plotly charts

### Phase 6 — Cloud Deployment
20. Dockerfile, Terraform, scheduling (ECS/Cloud Run)

### Phase 7 — Speaker Diarization (future)
21. pyannote.audio integration, speaker-labeled transcripts

## Estimated Daily Cost (~3 stations)

- Whisper API: ~$43/day (dominant cost)
- Claude API: ~$9-15/day
- Compute + DB: ~$2/day
- **Total: ~$55-60/day (~$1,700/month)**

Optimization path: self-host Whisper on GPU → reduce to ~$5-10/day for transcription.

## Hebrew-Specific Considerations

- Always `language="he"` in Whisper API
- Store `name_he` + `name_en` for all entities
- Political leaning prompts need Israeli party/issue context, updated periodically
- Chain Whisper chunks via `prompt` parameter for continuity
- Post-process proper nouns with Claude (Whisper struggles with Hebrew names)

## Verification Plan

1. Record 5 min of each station → verify audio quality
2. Transcribe 30 min → check Hebrew accuracy
3. Run analysis on a transcript sample → verify JSON output structure
4. Full pipeline dry run on 1 hour of 1 station
5. Dashboard renders correctly with test data
6. Full day recording + analysis for 1 station end-to-end
