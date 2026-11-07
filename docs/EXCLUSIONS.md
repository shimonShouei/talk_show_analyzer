# Excluded
- Audio: all recordings (*.mp3/*.wav, ~/tsa_data/rec*), spotcheck clips.
- Features/models: feats_*.npy (~16 MB), PANNs checkpoints, whisper models.
- extract.log (550 KB noisy log), ad_labels/raw/*.json (LLM chunk dumps, 296 KB), laptop/ad_tools.tgz (duplicate archive).
- Secrets/env: .env, API keys, git config/credentials — none bundled. Byte scan for sk-ant/sk-/ghp_/github_pat_/AKIA/private keys/xox/hf_: 0 hits.
- venvs, __pycache__, sqlite DBs, caches.
- Personal identifiers: Windows username paths sanitized; no contact metadata.

## Re-check when the export was added to the repo

The same categories stay out. `.gitignore` ignores audio, `*.npy`, model checkpoints, `*.db` / `*.sqlite*`, virtualenvs, `.env`, and `tools/ads/raw/` (the batch-download script writes model dumps there). `data/*` stays ignored except `data/ads/*.csv`, `*.json`, and `*.md`.

A second text scan of the export and of the files copied into the repo found no API keys, private keys, or cloud tokens. Anthropic batch ids in `tools/ads/fetch_batches.py` are historical batch identifiers. They are not credentials. The script still expects `ANTHROPIC_API_KEY` from the environment.

