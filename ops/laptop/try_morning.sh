#!/bin/bash
cd ~/tsa_data/ad_tools
for s in 103fm glz kan_bet; do
  /usr/bin/time -f "%e sec %M KB" ~/talk_show_analyzer/.venv/bin/python find_repeats.py --out ~/tsa_data/repeats/morning_$s ~/tsa_data/recordings/2026-11-04/$s > /tmp/rep_$s.log 2>&1
  echo "== $s"; tail -1 /tmp/rep_$s.log; head -c 900 ~/tsa_data/repeats/morning_$s/summary.json; echo
done
