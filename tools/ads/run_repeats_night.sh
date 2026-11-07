#!/bin/bash
# run after recording day ends: repeats for each station
DAY=${1:-$(date -d yesterday +%F)}
cd ~/tsa_data/ad_tools
for s in 103fm glz kan_bet; do
  ~/talk_show_analyzer/.venv/bin/python find_repeats.py --out ~/tsa_data/repeats/${DAY}_$s ~/tsa_data/recordings/$DAY/$s > ~/tsa_data/repeats/${DAY}_$s.log 2>&1
done
echo REPEATS_DONE $DAY >> ~/tsa_data/repeats/done.log
