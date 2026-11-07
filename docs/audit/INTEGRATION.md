# Integration of the 2026-11-07 local export

Remote `master` at integration time was `6a370be` (Deferred speaker resolution, part enrichment, Q&A/stance dashboard views). That is the parent the six local commits were made on. None of them were already on the remote, so all six were applied with `git am` and no conflict.

Original local SHAs, in order:

- `c07b7e2` Minimal local fixes: pin anthropic<1, fail-fast API key, diarization flag, failed-chunk count
- `510d50e` Host schedule timezone, deep-analysis max_tokens, legacy dashboard backfill
- `04535c5` Haiku / Message Batches cost path, recorder resume after stream drops
- `42153f6` Restore full chunk `<thinking>`
- `69368ea` Chunk JSON retry, voice-based speaker merge, Hebrew person keys, multi-show hosts
- `cb01f1e` Decode diarization audio with PyAV instead of torchaudio/torchcodec

`git am` rewrote the commit hashes (committer is this integration, authors stay as in the patch). Applied hashes:

- `e2433b6ebf9d32d9df033ee1e19267042797334e` (was `c07b7e2`)
- `ba2e23ec595ee799d3891c7dfe8d7858a808e039` (was `510d50e`)
- `6ce9b0516048792f993489cde1cac1f8cf253d69` (was `04535c5`)
- `d9c62952367a6b1417e420d34099e209ddaf0947` (was `42153f6`)
- `b97e3028fc14733b7de6b2db9be5b1ce296216ba` (was `69368ea`)
- `03cc8048119ee09d487dbb3e6a5ad1d482598521` (was `cb01f1e`)

The patch contents are the applied changes. `av==15.1.0` was not inside that patch. It is pinned in `pyproject.toml` because current `faster-whisper` (1.2.1) still calls `av.open(..., metadata_errors="ignore")` while declaring only `av>=11`, and PyAV 19 removed that argument. 15.1.0 is the version that worked with this decode path.

The 50-file export was copied to the destinations in `MANIFEST.tsv`. Edits after the copy:

- Scripts that expand `${WIN_USER}` source `ops/require_win_user.sh` and stop if it is unset or not a single folder name.
- `loginctl show-user administrator` now uses `LINUX_USER` or `USER`.
- `build_labels.py` and `extract.py` require explicit data paths. They no longer default to `/workspace/tsa_data`.
- Caveats were added in front of the spot-check report, the audio-style README, and `data/ads/PROVENANCE.md`. The original report text and the result CSVs were kept.
- `find_repeats.py` still writes `recurring_spot_minutes` and adds a note that the number is not commercial ad time.

`scripts/init_db.py` was not redesigned. Its docstring records what `create_all` does and does not do. It was not executed against a database in this integration.

Not run: pip/conda installers, recording scripts, systemd installers, Windows keepalive, PANNs or Whisper downloads, fingerprinting over audio.
