# Audio-style clustering pilot, 2026-11-07

Exploratory unsupervised clustering of 948 non-overlapping 10-second windows. This is not a proven ad classifier and it is not a cross-station evaluation.

## What the run actually was

- Windows: 948 × 10 s. Gold labels exist for one hour of 103FM only (see `data/ads/PROVENANCE.md`). The 2026-11-04 windows from 103FM, Galatz, and Kan Bet are unlabeled.
- Features: handcrafted librosa stats, and PANNs Cnn14 clip embeddings. PANNs tags used here are mainly music versus speech (`p_music`, `p_speech`).
- Clustering fit without labels (k-means and HDBSCAN). A later cross-fit tagged a cluster as "ad" only if gold-hour calibration windows were mostly ad, then scored the other fold of that same hour.
- For PANNs, k=3, the notes from the run say 52 of 53 gold ad windows fell in one cluster. That cluster also contains news and promos. The separation tracks speech-plus-music versus speech. `results_summary.csv` columns such as `cf_ad_rec` are that same-hour fold check. They are not accuracy on another station or another day.

Do not quote those figures as a validated detector.

## Files in git

- `windows.csv` — window metadata, gold label where the hour had one, PANNs music/speech probabilities. The `file` column still shows the box paths (`/workspace/tsa_data/...`) so the table matches the run. Those files are not in git.
- `assignments.csv`, `results_summary.csv`, `extract_config.json`, `analysis_config.json` (seed 0)
- `extract.py`, `analyze.py`

Not in git, and not regenerated here: `feats_*.npy` and the PANNs checkpoint. `.gitignore` ignores `*.npy`.

## Running again

Do not run this for a casual check. `extract.py` imports PANNs and, with `checkpoint_path=None`, downloads the Cnn14 weights. It also reads audio that is excluded from the repo.

Required environment variables (no `/workspace` default):

- `TSA_HOUR1_MP3` — the single gold-labeled recording
- `TSA_RECORDINGS_ROOT` — directory of `YYYY-MM-DD/station/part*.mp3`
- `TSA_GOLD_CSV` — gold spans (the committed file is `data/ads/gold_hour1.csv`)

Optional: `TSA_STYLE_DAYS` (default `2026-11-04`), `TSA_STYLE_STATIONS` (default `103fm,glz,kan_bet`), `TSA_HOUR1_DAY` (default `2026-11-02`), `TSA_HOUR1_STATION` (default `103fm`).

Dependencies beyond the core package: numpy, pandas, scikit-learn, librosa, torch, and `panns-inference`. torch is part of the conda setup in the main README, not a pip extra of this repo. `analyze.py` additionally needs the `feats_*.npy` files next to `windows.csv`, which are not committed.

```bash
pip install panns-inference
# then, only if the audio and the checkpoint download are acceptable:
TSA_HOUR1_MP3=/path/to/hour.mp3 \
TSA_RECORDINGS_ROOT=/path/to/recordings \
TSA_GOLD_CSV=/path/to/talk_show_analyzer/data/ads/gold_hour1.csv \
  python extract.py
python analyze.py
```

The historical command on the box was `/workspace/venv_style/bin/python extract.py` from this directory. That virtualenv is not in git.
