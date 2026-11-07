#!/bin/bash
D=~/tsa_data/recordings/2026-11-04
DUP=~/tsa_data/recordings/dup_2026-11-04
mkdir -p "$DUP"
for s in 103fm glz kan_bet; do
  f="$D/$s/part01_080904.mp3"
  [ -f "$f" ] && mv "$f" "$DUP/${s}_part01_080904.mp3" && echo "moved dup $s"
done
echo "== units"; systemctl --user list-units 'rec-*' --no-legend --all | cat
systemctl --user list-timers --no-legend | grep tsa | cat
echo "== files"
for s in 103fm glz kan_bet; do
  echo "-- $s"; ls -la "$D/$s" | cat
  for m in "$D/$s"/*.mp3; do
    sz=$(stat -c %s "$m"); age=$(( $(date +%s) - $(stat -c %Y "$m") ))
    echo "$(basename $m) $((sz/1024/1024))MB lastwrite ${age}s ago"
  done
  tail -n 3 "$D/$s/rec.log"
done
echo "== disk"; df -h ~ | tail -1; date
