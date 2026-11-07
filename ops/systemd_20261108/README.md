# One-off recording timers for 2026-11-08

Historical example, not a daily schedule.

- Window: 2026-11-08 07:00 through 23:59, timezone Asia/Jerusalem.
- Stations: `103fm`, `glz`, `kan_bet` (systemd instances of `tsa-record-20261108@.timer`).
- `record_once_20261108.sh` exits without recording outside that window. It then calls `$HOME/tsa_data/rec_station.sh`. `$HOME` is the WSL Linux home where that script lived. It is not a generic placeholder and it does not wake Windows.
- `tsa_install_once_20261108.sh` writes user systemd units and enables those three timers. Running it changes the user systemd configuration. This repository integration did not run it.
- `Persistent=true` only catches up a missed timer while the user systemd instance is already up. It does not wake a sleeping laptop, and it does not start WSL.

The unit files are the units that installer wrote. They are examples of that one date.
