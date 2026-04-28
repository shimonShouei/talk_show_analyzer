# Next Steps

Prioritized action items after the working E2E test (record + transcribe on RTX 3090).

## Immediate (improve transcription quality)

- [ ] **Set `HF_TOKEN` in `.env`** — current run fell back to single-speaker (`SPEAKER_00` only) because Pyannote couldn't authenticate. Get token at https://huggingface.co/settings/tokens.
- [ ] **Switch to `medium` or `large` Whisper model** — `base` produced rough Hebrew on noisy radio audio. `large-v3` is significantly better; fits on RTX 3090 (24GB).
- [ ] **Tune VAD / beam size** in `transcriber.py` for radio-specific audio (background music, ads, jingles).

## Phase 2: Analysis pipeline (`src/talk_show_analyzer/analysis/`)

Currently empty — needs Claude API integration:

- [ ] **`segmenter.py`** — split transcript into segments (interview / panel / news / ad) via Claude
- [ ] **`guests.py`** — identify guests + dedup across episodes
- [ ] **`topics.py`** — topic extraction per segment
- [ ] **`sentiment.py`** — sentiment per speaker per topic
- [ ] **`political.py`** — political leaning analysis
- [ ] **`ads.py`** — aggregate ad time
- [ ] **`prompts/`** — Hebrew-aware Claude prompt templates

## Phase 3: Database layer

- [ ] **`models.py`** — SQLAlchemy ORM (Episodes, Segments, Guests, Topics, Sentiment)
- [ ] **`db.py`** — engine/session factory
- [ ] **`alembic/`** — initial migration

## Phase 4: Pipeline orchestration (`src/talk_show_analyzer/pipeline/`)

- [ ] **`orchestrator.py`** — record → chunk → transcribe → analyze → store, with checkpointing
- [ ] **`retry.py`** — resume from last successful step on failure

## Phase 5: Daily automation

- [ ] **Cron-equivalent SLURM job** — daily 05:50 IST recording (4 hr per station × 3 stations)
- [ ] **Failure alerting** — email/Slack on stream-down or transcription errors

## Phase 6: Dashboard (`src/talk_show_analyzer/dashboard/app.py`)

- [ ] Streamlit UI: trends over time, guest leaderboard, topic heatmaps, sentiment per political leaning

## Operational / infra

- [ ] **Multi-station SLURM array job** — record Galatz + Kan Bet + 103FM in parallel (3 jobs)
- [ ] **Checkpoint chunking** — for 4hr recordings, chunk first then transcribe in parallel across multiple GPU jobs
- [ ] **Output location** — currently `test_output/`, needs proper `data/<date>/<station>/` structure
- [ ] **Cleanup** — old MP3s after transcription (keep transcripts only)

## Tech debt / cleanup

- [ ] Remove `test_gpu_setup.py` once setup is stable (it was for debugging the install)
- [ ] Add `tests/` directory with pytest (currently empty)
- [ ] Implement health-check endpoint / dashboard for daily cron status
