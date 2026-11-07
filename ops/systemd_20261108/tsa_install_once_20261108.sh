#!/bin/bash
# Installs user systemd timers for 2026-11-08 only. See README.md in this directory.
# Running this rewrites units under ~/.config/systemd/user and enables them.
# It was not run during the repo integration. It does not wake Windows.
# $HOME below is the WSL home, not a placeholder.
set -euo pipefail
mkdir -p "$HOME/tsa_data" "$HOME/.config/systemd/user"
cat > "$HOME/tsa_data/record_once_20261108.sh" <<'RUN'
#!/bin/bash
set -euo pipefail
export TZ=Asia/Jerusalem
start=$(date -d '2026-11-08 07:00:00' +%s)
end=$(date -d '2026-11-08 23:59:00' +%s)
now=$(date +%s)
if (( now < start || now >= end )); then
  echo "Outside authorized recording window; not recording: $(date -Is)"
  exit 0
fi
case "${1:-}" in
103fm) url='https://cdn.cybercdn.live/103FM/Live/icecast.audio'; ref='https://103fm.maariv.co.il/' ;;
glz) url='https://glzwizzlv.bynetcdn.com/glz_mp3'; ref='https://glfrp.glz.co.il/' ;;
kan_bet) url='https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_BET.mp3?dist=coolsite'; ref='https://www.kan.org.il/' ;;
*) echo 'Invalid station' >&2; exit 2 ;;
esac
# timeout enforces wall-clock deadline even when stream connection/reconnect hangs.
exec timeout --signal=TERM --kill-after=5 "$((end-now))s" bash "$HOME/tsa_data/rec_station.sh" "$1" "$url" "$ref" 23:59
RUN
chmod 755 "$HOME/tsa_data/record_once_20261108.sh"
cat > "$HOME/.config/systemd/user/tsa-record-20261108@.service" <<'SERVICE'
[Unit]
Description=One-off radio recording 2026-11-08 (%i)
[Service]
Type=simple
Environment=TZ=Asia/Jerusalem
ExecStart=/bin/bash %h/tsa_data/record_once_20261108.sh %i
KillMode=control-group
TimeoutStopSec=5
RuntimeMaxSec=17h
SuccessExitStatus=124 143
SERVICE
cat > "$HOME/.config/systemd/user/tsa-record-20261108@.timer" <<'TIMER'
[Unit]
Description=One-off 2026-11-08 07:00 Asia/Jerusalem recording (%i)
[Timer]
OnCalendar=2026-11-08 07:00:00 Asia/Jerusalem
AccuracySec=1s
RandomizedDelaySec=0
Persistent=true
Unit=tsa-record-20261108@%i.service
[Install]
WantedBy=timers.target
TIMER
bash -n "$HOME/tsa_data/record_once_20261108.sh"
systemd-analyze --user verify "$HOME/.config/systemd/user/tsa-record-20261108@.service" "$HOME/.config/systemd/user/tsa-record-20261108@.timer"
systemctl --user daemon-reload
for station in 103fm glz kan_bet; do
 systemctl --user enable --now "tsa-record-20261108@$station.timer"
done
printf '\nVERIFICATION\n'
date -Is
systemd-analyze calendar '2026-11-08 07:00:00 Asia/Jerusalem'
systemctl --user list-timers --all --no-pager
for station in 103fm glz kan_bet; do
 systemctl --user is-enabled "tsa-record-20261108@$station.timer"
 systemctl --user show "tsa-record-20261108@$station.timer" -p ActiveState -p NextElapseUSecRealtime -p Triggers
 systemctl --user show "tsa-record-20261108@$station.service" -p ActiveState -p ExecStart
 done
printf '\nGUARD TEST: must decline recording before Nov8 07:00\n'
bash "$HOME/tsa_data/record_once_20261108.sh" 103fm
printf '\nLINGER\n'
# Linger is a property of the Linux user. The box account was "administrator".
# Query the current user unless LINUX_USER is set. This does not wake Windows.
LINUX_USER="${LINUX_USER:-${USER:-}}"
if [ -z "$LINUX_USER" ]; then
  echo "LINUX_USER or USER is required to query linger. Refusing an implicit account name." >&2
  exit 1
fi
loginctl show-user "$LINUX_USER" -p Linger || true
printf '\nWSL keepalive processes\n'
ps -eo pid,comm,args | rg 'sleep|wsl' || true
