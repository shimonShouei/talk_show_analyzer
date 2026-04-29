# Next Steps

## ✅ Completed

### Phase 1: Transcription Quality
- [x] **Upgraded Whisper** to `large-v3` with tuned VAD (`whisper_vad_min_silence_ms=500`, `beam_size=5`)
- [x] **Pyannote diarization** attempted (auth working, but numerical singularity → skipped; single-speaker fallback acceptable for initial MVP)

### Phase 2: Analysis Pipeline
- [x] **`segmenter.py`** — Claude-based segmentation (interview/panel/news/ad/jingle) with 20-min windows + 2-min overlap
- [x] **`guests.py`** — guest identification with confidence scoring
- [x] **`topics.py`** — Hebrew-aware topic extraction (main + subtopics) with bilingual output
- [x] **`sentiment.py`** — sentiment analysis per speaker per topic with tone classification and quotes
- [x] **`ads.py`** — ad time aggregation
- [x] **`prompts/`** — Hebrew-aware prompt templates

### Phase 3: Database Layer
- [x] **`models.py`** — 8 SQLAlchemy ORM tables (Station, Episode, Segment, Topic, Guest, GuestAppearance, SentimentResult, PipelineRun)
- [x] **`db.py`** — engine/session factory with context managers
- [x] **`alembic/`** — initial schema migration

### Phase 4: Pipeline Orchestration
- [x] **`orchestrator.py`** — full pipeline (record → transcribe → segment → topics → guests → sentiment → store) with checkpoint recovery
- [x] **Checkpointing** — `PipelineRun` table tracks step status for resumable execution

## Phase 5: Daily Automation

- [ ] **CLI entry point** (`src/talk_show_analyzer/cli.py`) — `analyze-episode <station>` for single run
- [ ] **Multi-station SLURM job** — `.claude/daily_pipeline.slurm` for Galatz + Kan Bet + 103FM in parallel
- [ ] **Output structure** — switch from `test_output/` to `data/<YYYY-MM-DD>/<station>/`
- [ ] **Failure alerting** — email/Slack on stream-down, transcription errors, or analysis failures

## Phase 6: Dashboard

- [ ] **`src/talk_show_analyzer/dashboard/app.py`** — Streamlit UI
  - [ ] Episode list with filters (date, station, status)
  - [ ] Guest leaderboard (appearances over time)
  - [ ] Topic trends (word clouds, timeline heatmaps)
  - [ ] Sentiment by speaker / by topic
  - [ ] Political leaning analysis (TODO: add ML classifier)

## Phase 7: Operational Infrastructure

- [ ] **Chunking for parallel transcription** — split 4hr recordings into 30-min chunks, submit as SLURM array
- [ ] **Audio cleanup** — delete MP3s after successful transcription (keep transcripts + analysis)
- [ ] **Retry logic** — auto-retry failed steps with exponential backoff
- [ ] **Metrics / monitoring** — log processing time per step, token usage, storage costs

## Tech Debt / Cleanup

- [ ] Add pytest suite (`tests/`) for analysis modules and database
- [ ] Implement political leaning classifier (NLP on generated summaries)
- [ ] Add health-check endpoint for cron monitoring
- [ ] Remove `test_gpu_setup.py` (debug script, no longer needed)
- [ ] Profile token usage per episode (optimize prompt caching)
