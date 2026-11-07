#!/bin/bash
set -e
echo "== date"; date; uptime
echo "== units"
systemctl --user list-units 'rec-*' --no-legend --all | cat
systemctl --user list-timers --no-legend | grep tsa | cat
echo "== done.log"
cat ~/tsa_data/repeats/done.log 2>/dev/null || echo "(no done.log)"
echo "== repeats dirs"
ls -la ~/tsa_data/repeats/ 2>/dev/null | cat
echo "== recordings 2026-11-04"
for s in 103fm glz kan_bet; do
  echo "-- $s"
  ls -la ~/tsa_data/recordings/2026-11-04/$s/ | cat
  for f in ~/tsa_data/recordings/2026-11-04/$s/*.mp3; do
    [ -f "$f" ] || continue
    sz=$(stat -c %s "$f"); age=$(( $(date +%s) - $(stat -c %Y "$f") ))
    echo "$(basename $f) $((sz/1024/1024))MB mtime ${age}s ago"
  done
  echo "rec.log tail:"; tail -n 5 ~/tsa_data/recordings/2026-11-04/$s/rec.log 2>/dev/null
done
echo "== repeats 2026-11-04 outputs"
for s in 103fm glz kan_bet; do
  d=~/tsa_data/repeats/2026-11-04_$s
  echo "-- $d"
  if [ -d "$d" ]; then
    ls -la "$d" | cat
    for f in summary.txt groups.csv report.txt clusters.csv; do
      [ -f "$d/$f" ] && echo "--- $f ---" && head -n 40 "$d/$f"
    done
    for f in "$d"/*.log "$d"/run.log; do
      [ -f "$f" ] && echo "--- $(basename $f) ---" && tail -n 30 "$f"
    done
  else
    echo missing
  fi
done
echo "== night log if any"
ls -la ~/tsa_data/repeats/*.log 2>/dev/null | cat
find ~/tsa_data/repeats -name '*.log' -mtime -1 2>/dev/null | head
