# Ad label files

These three files are the output of one local run of `tools/ads/build_labels.py`. The audio, SQLite databases, and raw LLM chunk dumps that produced them are not in git. See `docs/EXCLUSIONS.md`.

## gold_hour1.csv

Manual spans for a single 103FM recording, about 55 minutes (`DUR = 3294.36` seconds in `build_labels.py`). The script comment calls it a hand-checked reference read from the transcript and snapped to segment times.

What is known:

- One station only: 103FM.
- The gold CSV has no date and no station column. The audio-style pilot attributes this hour to 2026-11-02 and to the box file `/workspace/tsa_data/runs/hour1/hour.mp3`. That date is the pilot's attribution, not a field stored in this CSV.
- `text_snippet` is copied from `hour_transcript.json` on that box (Whisper text). It was not re-heard against the audio during this integration, because the audio is not in the repo.
- Brand names in `note` are the annotator's reading of that transcript. Mis-hearings are possible. Several short "Maccabi app" rows are labeled as stream pre-roll on connect or reconnect.

This is not a multi-day or multi-station gold set.

## labels.csv

Weak labels. Sources are LLM chunk `part_type` / topic titles, plus rows from the local SQLite `parts`, `merged_topics`, and `speaker_identities` tables. They are not hand gold. `text_snippet` is transcript text.

## stats.json

Per-second overlap of those weak labels with `gold_hour1.csv` for the `hour1` and `hour2` runs. It is an agreement figure against this one reference hour, not a held-out test and not a cross-station score.
