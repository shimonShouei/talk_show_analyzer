#!/bin/bash
# Historical attempt at a 07:00–10:00 user timer, every day.
# This is not the 2026-11-08 one-off (see ops/systemd_20261108/README.md).
# Laptop sleep stopped recording. Running this enables a user timer.
# It was not run during the repo integration, and it does not wake Windows.
set -e
D=~/.config/systemd/user; mkdir -p $D
cat > ~/tsa_data/daily_rec.sh <<'EOS'
#!/bin/bash
for s in "glz|https://glzwizzlv.bynetcdn.com/glz_mp3|https://glfrp.glz.co.il/" \
         "kan_bet|https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_BET.mp3?dist=coolsite|https://www.kan.org.il/" \
         "103fm|https://cdn.cybercdn.live/103FM/Live/icecast.audio|https://103fm.maariv.co.il/"; do
  IFS="|" read -r n u r <<< "$s"
  bash ~/tsa_data/rec_station.sh "$n" "$u" "$r" 10:00 &
done
wait
EOS
chmod +x ~/tsa_data/daily_rec.sh
cat > $D/tsa-rec.service <<'EOS'
[Unit]
Description=TSA daily radio recording 07:00-10:00
[Service]
Type=simple
ExecStart=/bin/bash %h/tsa_data/daily_rec.sh
EOS
cat > $D/tsa-rec.timer <<'EOS'
[Unit]
Description=Start TSA recording every day at 07:00
[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=false
[Install]
WantedBy=timers.target
EOS
systemctl --user daemon-reload
systemctl --user enable --now tsa-rec.timer
systemctl --user list-timers --no-pager | grep tsa
