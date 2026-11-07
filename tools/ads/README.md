# Ad fingerprint and podcast-diff tools

Standalone scripts from the November 2026 laptop pass. They are not stages of `PipelineOrchestrator`.

## What they do not establish

- `find_repeats.py` clusters recurring audio with landmark fingerprints. A cluster was not fully validated: spot-checks transcribed one clip per selected cluster. The 103FM 74× group and the Kan Bet 120× group are dubious and may be over-merged.
- `recurring_spot_minutes` in `summary.json` is repeated audio time (occurrence length, including padding). It is not commercial ad minutes. Jingles, station IDs, news bumpers, and PSAs recur too.
- `label_ads_103fm.py` marks audio that is inside a show window but missing from that show's ad-free podcast. The label `ad_candidate` mixes ads, news, promos, and jingles. The ~32 minute figure in the spot-check report is only inside the shows that had a podcast that day, not a full-day ad total.
- Spot-check labels in `docs/reports/` are provisional transcription labels.

## Dependencies (not part of the core install)

Core `pip install -e .` does not install or run these tools.

- `find_repeats.py`, `eval_repeats.py`: Python 3.10+, numpy, scipy, ffmpeg on `PATH`
- `label_ads_103fm.py`, `eval_podlabels.py`: those plus `requests` (podcast RSS and MP3 download)
- `build_labels.py`: the talk_show_analyzer tree on `PYTHONPATH` (the script adds `src/`), plus the excluded SQLite files and transcripts
- `fetch_batches.py`: the `anthropic` package and `ANTHROPIC_API_KEY` in the environment. It writes raw model dumps under `raw/`. Those dumps are gitignored. Do not commit them.

```bash
pip install numpy scipy requests
```

## Paths

`build_labels.py` reads `TSA_DATA_ROOT`. That variable is required. The historical box used `/workspace/tsa_data`. There is no default, so an unset variable cannot silently point at the old machine path.

`install_ad_tools.sh` expects `WIN_USER` (see `ops/require_win_user.sh`) and a tarball at `/mnt/c/Users/$WIN_USER/ad_tools.tgz`. It also enables a user systemd timer at 00:15. That timer was a local experiment. WSL sleep stopped work on this machine. Do not treat the script as a production installer. It was not run during the repo integration.

The other shell wrappers under `ops/laptop/` call `~/talk_show_analyzer/.venv/bin/python` and `~/tsa_data/...`. That is the laptop layout, recorded as it was used.
