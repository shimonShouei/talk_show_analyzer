#!/bin/bash
# Historical "start three stations now" helper. It calls systemd-run.
# It does not wake Windows and it is not the Nov 8 timer. Not run during integration.
END=${1:-10:00}
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$_d/../require_win_user.sh"
cp "/mnt/c/Users/${WIN_USER}/rec_station.sh" ~/tsa_data/rec_station.sh; chmod +x ~/tsa_data/rec_station.sh
T=$(date +%H%M)
systemd-run --user --unit=rec-glz-$T bash ~/tsa_data/rec_station.sh glz "https://glzwizzlv.bynetcdn.com/glz_mp3" "https://glfrp.glz.co.il/" $END
systemd-run --user --unit=rec-kanbet-$T bash ~/tsa_data/rec_station.sh kan_bet "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_BET.mp3?dist=coolsite" "https://www.kan.org.il/" $END
systemd-run --user --unit=rec-103fm-$T bash ~/tsa_data/rec_station.sh 103fm "https://cdn.cybercdn.live/103FM/Live/icecast.audio" "https://103fm.maariv.co.il/" $END
sleep 40
ls -la ~/tsa_data/recordings/$(date +%F)/*/
tail -n3 ~/tsa_data/recordings/$(date +%F)/*/rec.log
