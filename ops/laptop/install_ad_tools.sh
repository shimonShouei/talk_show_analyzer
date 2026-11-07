#!/bin/bash
# Historical laptop helper, not a production installer.
# Enables a 00:15 user timer. On the WSL box, sleep stopped this work.
# Does not wake Windows. Not run during the repo integration.
set -e
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for _c in "$_d/../require_win_user.sh" "$_d/../../ops/require_win_user.sh"; do
  if [ -f "$_c" ]; then
    # shellcheck disable=SC1090
    . "$_c"
    break
  fi
done
if [ -z "${TSA_WIN_USER_CHECKED:-}" ]; then
  echo "Refusing to run: ops/require_win_user.sh was not found, so WIN_USER cannot be checked." >&2
  exit 1
fi
mkdir -p ~/tsa_data/ad_tools ~/tsa_data/repeats
tar -xzf "/mnt/c/Users/${WIN_USER}/ad_tools.tgz" -C ~/tsa_data/ad_tools
~/talk_show_analyzer/.venv/bin/python -c "import numpy, scipy, requests; print('DEPS_OK')"
D=~/.config/systemd/user; mkdir -p $D
printf '[Unit]\nDescription=TSA nightly repeats\n[Service]\nType=oneshot\nExecStart=/bin/bash %%h/tsa_data/ad_tools/run_repeats_night.sh\n' > $D/tsa-repeats.service
printf '[Unit]\nDescription=TSA nightly repeats 00:15\n[Timer]\nOnCalendar=*-*-* 00:15:00\n[Install]\nWantedBy=timers.target\n' > $D/tsa-repeats.timer
systemctl --user daemon-reload
systemctl --user enable --now tsa-repeats.timer
systemctl --user list-timers --no-pager | grep tsa
