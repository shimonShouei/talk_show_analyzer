# talk_show_analyzer — export of work since 2026-11-02 (for integration)

Suggested repo layout: `tools/ads/`, `ops/`, `experiments/`, `docs/reports/` (see `docs/audit/MANIFEST.tsv`).
Core-code changes: separate `box-local-fixes.patch` (6 commits, `git am` onto origin/master 6a370be; incl. cb01f1e PyAV decode for diarization).

## Integration corrections

The sections under this heading are the original export notes. Read these limits with them:

- Fingerprint groups were not fully validated. The 74× (103FM) and 120× (Kan Bet) groups are dubious. Repeated minutes are not commercial ad time.
- Spot-check labels are provisional transcripts of one clip per cluster. See the correction at the top of `docs/reports/spotcheck_2026-11-04_report.md`.
- `gold_hour1.csv` is one 103FM recording of about 55 minutes. Provenance and uncertainty are in `data/ads/PROVENANCE.md`.
- The audio-style pilot is 948 windows of 10 seconds. PANNs clustering in that run is mainly music versus speech. It is not a general ad classifier and it has no cross-station accuracy claim. `results_summary.csv` is the historical table, not a leaderboard.
- `ops/systemd_20261108` is 2026-11-08 only. It is not a daily schedule and it does not wake Windows.
- `WIN_USER` must be set to the Windows account folder name. Scripts that expand it source `ops/require_win_user.sh` and exit if it is unset or looks like a path. The bundler had replaced `/mnt/c/Users/Administrator`.
- `$HOME` and `~` in the WSL scripts are the Linux home (`~/tsa_data`, `~/talk_show_analyzer`). They are not a sanitized placeholder. Do not blank them out.

How this was integrated is in `docs/audit/INTEGRATION.md`.

## What was tested (as previously reported, no new claims)
- find_repeats.py: fingerprint-based repeat clustering (>=3 repeats, 4–120 s). Ran nightly on Nov 4 recordings (~15 h/station).
- Spotcheck (reports/): 55 strong clusters cut/transcribed/classified; ~1/4 real ads, ~1/2 jingles/promos/station IDs.
- label_ads_103fm.py: live vs podcast diff found ~32 min suspected ads in 3 shows.
- Audio-style pilot: 948 x 10 s windows; PANNs, k=3: 52/53 ad windows in one cluster, but cluster also holds news/promos (speech+music vs speech). Labels from ONE hour of 103FM only.

## Label status
- `ad_tools/data/gold_hour1.csv`: manual gold, 1 hour 103FM only.
- `ad_tools/data/labels.csv`: WEAK labels (LLM chunk part_type/topic), not gold.
- reports/spotcheck_classifications.json: PROVISIONAL (single-sample transcripts; not verified that all members of a cluster are the same segment).

## Known caveats
- Huge groups (103FM 74x, Kan Bet 120x) are dubious/possibly over-merged; "repeated minutes" inflates (count x length, incl. padding).
- Kan Bet top group = sponsored news intro, not a regular ad.
- ops/windows keepalive*.ps1: WSL keepalive was later NOT found running; unreliable, laptop sleep/disconnects stopped recording twice. Not a supported service.
- ops/systemd_20261108: one-off timer for 2026-11-08 only (07:00–23:59 Asia/Jerusalem); depends on WSL staying up. Keep as example.
- The Windows account folder was replaced with `${WIN_USER}`. Set `WIN_USER` to that folder name before any script that copies through `/mnt/c/Users`. Unset is refused. `$HOME` in the systemd examples is the real WSL home, not a placeholder.
- No recordings/weekend data (Fri/Sat not recorded).
