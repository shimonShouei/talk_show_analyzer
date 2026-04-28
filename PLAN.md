# Israeli Talk Show Analyzer — Implementation Plan

## Context

Build a daily automated system that records morning talk shows from 3 Israeli radio stations (Galatz, 103FM, Kan Reshet Bet), transcribes them (Hebrew), and analyzes them for: guests, topics, ad time, sentiment per speaker/topic, and political leaning. Results displayed in a Streamlit dashboard. Deployed on cloud (AWS/GCP), designed as MVP that can grow into a product.

## Architecture Overview

```
[Cron 05:50 IST] → [Record 3 streams via ffmpeg ~4hrs]
    → [Chunk audio into 25-min pieces]
    → [GPT-4o-transcribe-diarize (Hebrew + speaker labels)]
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
│   │   ├── chunker.py          # Split audio into 25-min chunks
│   │   └── transcriber.py      # GPT-4o-transcribe-diarize client
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
| Transcription + Diarization | **Faster-Whisper** (free) + **Pyannote** (free) | Self-hosted, no API costs, keeps Whisper accuracy. Requires GPU or beefy CPU. Diarization via open-source Pyannote model. |
| NLP analysis | Claude Sonnet for bulk, Opus for political leaning | Cost-effective for volume, nuanced model for hardest task |
| Scheduling | ECS Fargate / Cloud Run | Long-running recording task (4hrs) needs persistent compute |
| Object storage | S3/GCS | Raw audio by date/station, 30-day retention |

## Stream URLs & Access Strategy

Stream URLs require proper HTTP headers to avoid 403 errors. The CDN servers check `Referer` and `User-Agent`.

| Station | Primary URL | Format | Referer Header |
|---------|------------|--------|----------------|
| Galatz | `https://glzwizzlv.bynetcdn.com/glz_mp3` | MP3/Icecast | `https://glfrp.glz.co.il/` |
| Kan Bet | `https://kanlivep2event-i.akamaihd.net/hls/live/749624/749624/kanbet_mp3/chunklist.m3u8` | HLS/M3U8 | `https://www.kan.org.il/` |
| 103FM | Needs extraction from 103fm.maariv.co.il player | Likely HLS | `https://103fm.maariv.co.il/` |

**ffmpeg recording with headers:**
```bash
ffmpeg -headers "Referer: https://glfrp.glz.co.il/\r\nUser-Agent: Mozilla/5.0\r\n" \
  -i "https://glzwizzlv.bynetcdn.com/glz_mp3" \
  -t 14400 -acodec libmp3lame -ab 128k -ar 16000 -ac 1 output.mp3
```

**Resilience strategy:**
- Keep a registry of primary + fallback URLs per station in `streams.py`
- `test_streams.py` validates all URLs before each recording session
- Use `yt-dlp` or `streamlink` as fallback extractors for 103FM
- If ffmpeg dies mid-recording, keep partial file (still valuable)
- Reference: fmstream.org/index.php?c=ISR for updated URLs

## Data Models (Key Tables)

- **Station** — id, name, stream_url, show_start/end times
- **Recording** — station_id, date, audio_path (S3), duration, status
- **Transcript** — recording_id, raw_text, diarized_output (JSON with speaker segments), word_count
- **Segment** — transcript_id, type (interview/panel/news/ad/music), start/end time, summary, raw_text
- **Guest** — name_he, name_en, title, affiliation, first_seen_date
- **Topic** — name_he, name_en, category
- **SegmentTopic** — segment_id, topic_id, sentiment_score, political_leaning
- **SpeakerSentiment** — segment_id, speaker_label, guest_id (nullable), topic_id, sentiment, leaning, supporting_quotes (JSON)
- **DailySummary** — station_id, date, ad_%, num_guests, overall_sentiment/leaning, summary_text, summary_json
- **PipelineRun** — station_id, date, step, status, started_at, completed_at, error_message

## Claude Prompt Strategy

### Segmentation Prompt
Feed diarized transcript in 20-min windows with 2-min overlap. Ask Claude to classify each contiguous block as: `interview`, `panel_discussion`, `news_update`, `ad`, `jingle`, `music`, `caller`. Return JSON array of segments with start/end timestamps.

### Guest Identification Prompt
For interview/panel segments, provide the speaker-labeled text and ask Claude to:
1. Map speaker labels (SPEAKER_00, SPEAKER_01) to real names using context clues (introductions, "welcome X", "thank you minister Y")
2. Identify title, role, organizational affiliation
3. Return structured JSON with confidence scores

### Topic Extraction Prompt
Per segment, extract: main topic, subtopics, category (politics/security/economy/social/culture/sports), and 1-2 sentence summary in both Hebrew and English.

### Sentiment Analysis Prompt
Per speaker per topic within each segment:
- Overall sentiment: -1.0 (very negative) to +1.0 (very positive)
- Emotional tone: angry/calm/enthusiastic/dismissive/neutral
- Supporting quotes (2-3 key quotes per speaker)

### Political Leaning Analysis Prompt (use Claude Opus)
This is the most nuanced analysis. The system prompt must include:

```
You are an expert analyst of Israeli media and politics.

Current Israeli political landscape:
RIGHT BLOC: Likud (nationalist-liberal), Religious Zionism/Otzma Yehudit (far-right nationalist),
  Shas (Mizrachi ultra-orthodox), UTJ (Ashkenazi ultra-orthodox)
CENTER: Yesh Atid (liberal-centrist), National Unity (security-centrist)
LEFT BLOC: Labor (social-democratic), Meretz/Democrats (progressive), Hadash-Ta'al (Arab-Jewish left)

Key issue axes:
- Security/defense: hawkish (right) vs. diplomatic/negotiation (left)
- Judicial/democratic: pro-judicial reform (right) vs. pro-judicial independence (left)
- Economy: free market (right) vs. welfare state (left)
- Religion-state: pro-religious legislation (right) vs. secular (left)
- Settlements: pro-expansion (right) vs. two-state/freeze (left)

Analyze political leaning based on:
1. FRAMING: How issues are presented (e.g., "security operation" vs. "military escalation")
2. WORD CHOICE: Loaded terms, euphemisms, labels
3. GUEST SELECTION: Who is invited, how much airtime they get, ratio of left/right guests
4. HOST BEHAVIOR: Pushback given to each side, leading questions, tone
5. TOPIC EMPHASIS: Which stories lead, which are omitted
6. SOURCING: Which officials/organizations are cited as authorities

Rate on scale: -1.0 (strong left) to +1.0 (strong right)
Provide separate scores for: host_leaning, guest_balance, framing_leaning, overall_leaning
Include reasoning and specific indicators for each score.
```

**Important**: This prompt must be updated periodically as the Israeli political landscape shifts (coalitions change, new issues emerge). Store the political context as a separate config file, not hardcoded in the prompt template.

## Implementation Phases

### Phase 1 — Scaffolding + Recording
1. ✅ Project setup: pyproject.toml, src layout, config.py, .env.example, .gitignore
2. `recorder/streams.py` — station URL registry with headers, health checks, fallback URLs
3. `recorder/capture.py` — ffmpeg subprocess wrapper with header injection
4. DB models + Alembic + docker-compose (Postgres)
5. Test: record 5 minutes of each station locally, verify audio quality

### Phase 2 — Transcription + Diarization
6. ✅ `transcription/chunker.py` — split audio into 25-min chunks (Whisper API limit is 25MB; at 128kbps mono that's ~26 min)
7. ✅ `transcription/transcriber.py` — Faster-Whisper + Pyannote for free transcription + diarization, `language="he"`
8. ✅ Post-processing: merge speaker labels via Pyannote overlay on Whisper segments
9. TODO: Test with 30 min of Hebrew audio, evaluate quality + diarization accuracy

### Phase 3 — Analysis
10. `analysis/segmenter.py` — segment identification via Claude (with overlap windows)
11. `analysis/guests.py` — guest identification from diarized text + dedup against guest registry
12. `analysis/topics.py` — topic extraction per segment
13. `analysis/ads.py` — ad time from segment data + audio heuristics (volume/speaker changes)
14. `analysis/sentiment.py` — sentiment per speaker per topic
15. `analysis/political.py` — political leaning (Claude Opus, Israeli context prompt)
16. `reports/daily_summary.py` — daily report generation
17. Store all results in PostgreSQL

### Phase 4 — Pipeline Orchestration
18. `pipeline/orchestrator.py` — chain all steps, checkpoint per step in PipelineRun table
19. `pipeline/retry.py` — resume from last successful step on failure
20. `scripts/run_pipeline.py` — CLI with Click

### Phase 5 — Dashboard
21. Streamlit app pages:
    - **Daily Overview**: per-station summary, key guests, top topics, ad percentage
    - **Station Comparison**: side-by-side sentiment/leaning for same day
    - **Topic Trends**: topic frequency and sentiment over time
    - **Guest Log**: who appeared where, how often, sentiment toward them
    - **Political Leaning Over Time**: per-station leaning trends, host vs. framing vs. guest balance
22. Plotly charts, Hebrew text support

### Phase 6 — Cloud Deployment
23. Dockerfile for pipeline runner
24. Terraform/CDK for cloud infra (ECS/Cloud Run, RDS/Cloud SQL, S3/GCS, EventBridge/Cloud Scheduler)
25. Deploy and run first full daily cycle

## Estimated Daily Cost (~3 stations)

**With Free Transcription:**

| Component | Calculation | Daily Cost |
|-----------|-------------|------------|
| Faster-Whisper (self-hosted) | No API cost, amortized GPU/compute | ~$0 (pay once for hardware) |
| Pyannote diarization (self-hosted) | No API cost | ~$0 (pay once for hardware) |
| Claude Sonnet (bulk analysis) | ~300K input tokens × 3 stations | ~$9-12 |
| Claude Opus (political leaning) | ~50K tokens × 3 stations | ~$5-8 |
| Cloud compute (recording) | 4 hrs on t3.medium or equivalent | ~$0.50 |
| Cloud compute (analysis) | 1-2 hrs processing | ~$0.50 |
| PostgreSQL (managed) | db.t3.micro or equivalent | ~$1 |
| S3/GCS storage | ~350MB/day, negligible | ~$0.01 |
| **Total** | | **~$16-22/day (~$480-660/month)** |

**Upfront hardware investment:**
- GPU (NVIDIA 4070 or similar): ~$600 one-time, ~300W sustained → ~$25-30/month electricity
- Or: Use cloud GPU instance (p3.2xlarge ~$3-4/hr) for transcription, spin down after use

**Cost optimization paths:**
- Use Claude Haiku for initial segmentation/topic extraction, Sonnet only for sentiment → save ~30%
- Batch API for non-time-sensitive analysis (Claude offers 50% discount) → save ~$5-7/day
- Replace Claude entirely with open-source LLMs (Llama 3) if doing this fully free (but loses quality for political analysis)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stream URLs change without notice | Recording fails | URL registry with fallbacks, `test_streams.py` pre-check, fmstream.org monitoring, alerts on failure |
| 403/geo-blocking from CDN | Can't record from cloud | Use cloud instance in IL region, or set up a lightweight relay on an Israeli VPS |
| Hebrew transcription errors (names, places) | Bad guest identification | Post-process with Claude to normalize names, maintain known-guests seed list |
| Speaker label inconsistency across chunks | Wrong speaker attribution | Cross-chunk speaker merging heuristic (voice embedding similarity or Claude-based matching) |
| `gpt-4o-transcribe-diarize` retires (2027-04-16) | Need migration | Monitor OpenAI deprecation notices, have fallback to whisper + pyannote |
| Political leaning bias in LLM itself | Unreliable scores | Calibrate with known-bias shows, compare across models, expose reasoning for manual review |
| Israeli political landscape shifts | Stale prompts | Store political context in a separate updatable config file, not hardcoded |
| Rate limits on OpenAI/Claude APIs | Pipeline stalls | Implement exponential backoff with tenacity, process stations sequentially if needed |
| Large audio files fail to upload | Lost recordings | Stream directly to S3 during recording (tee to local + S3), chunk uploads |

## Hebrew-Specific Considerations

- Use `language="he"` in transcription API
- Store `name_he` + `name_en` for all entities (guests, topics)
- Maintain a seed list of ~200 common Israeli public figures (politicians, journalists, commentators) for guest matching
- Political leaning prompts need current Israeli party/coalition context, stored in updateable config
- Hebrew renders correctly in PostgreSQL (UTF-8) and Streamlit
- For Plotly charts with Hebrew labels, configure explicit RTL-supporting fonts
- Post-process Whisper output with Claude to fix common Hebrew name transcription errors

## Verification Plan

1. Record 5 min of each station → verify audio quality, confirm headers work
2. Transcribe 30 min → check Hebrew accuracy + diarization quality (are speakers separated correctly?)
3. Run full analysis pipeline on a 30-min sample → verify JSON output structure for each analysis step
4. Full pipeline dry run on 1 hour of 1 station, end-to-end
5. Dashboard renders correctly with test data, Hebrew displays properly
6. Full day recording + analysis for 1 station
7. Compare political leaning scores against known editorial positions as sanity check
