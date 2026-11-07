# Operational notes from one WSL laptop (November 2026)

These scripts are the historical recording and bookkeeping commands from a single Windows + WSL box. They are not the project pipeline and they are not a supported daily schedule.

What they assume, and what they do not do:

- Layout on that machine was `~/talk_show_analyzer` (a checkout with `.venv`) and `~/tsa_data` (recordings, repeats, labels). `~` and `$HOME` mean that Linux home. They were not placeholders for a deleted path. Leave them as the WSL home.
- Windows copies used `/mnt/c/Users/${WIN_USER}/...`. `WIN_USER` must be set to the account folder name before those scripts run. `ops/require_win_user.sh` exits if it is missing or looks like a path. The old folder name on the box was `Administrator`.
- Laptop sleep and WSL disconnects stopped recording more than once. `ops/windows/keepalive.ps1` and `keepalive2.ps1` were an attempt to hold WSL open and disable sleep. A later check did not find that keepalive running. They do not guarantee the machine stays awake, and they are not a service this repo supports.
- `ops/laptop/setup_daily.sh` would install a user timer for 07:00–10:00 every day. That attempt is not the Nov 8 schedule and was not reliable. Do not treat it as production automation.
- `ops/systemd_20261108/` is a one-off for 2026-11-08, 07:00–23:59 Asia/Jerusalem, three stations. It is not a repeating daily timer. It runs only while WSL stays up.

Nothing in this directory was executed while integrating it into the repo. Do not run the installers or the recording scripts unless you intend to record or to change user systemd units on that machine.
