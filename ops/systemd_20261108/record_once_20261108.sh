#!/bin/bash
# One calendar day only: 2026-11-08 07:00–23:59 Asia/Jerusalem.
# Outside that window this script exits 0 and does not record.
# $HOME is the WSL Linux home (the rec_station.sh location on that box).
# Staying inside the window still requires WSL to be up. This does not wake Windows.
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
