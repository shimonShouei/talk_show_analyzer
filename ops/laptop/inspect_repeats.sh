#!/bin/bash
set -euo pipefail
echo "=== DATE ==="
date
echo "=== RECORDINGS ==="
for s in 103fm glz kan_bet; do
  echo "--- $s ---"
  ls -lah ~/tsa_data/recordings/2026-11-04/$s/ 2>/dev/null || echo missing
done
echo "=== REPEATS DIRS ==="
ls -lah ~/tsa_data/repeats/ 2>/dev/null
echo "=== SUMMARIES ==="
for s in 103fm glz kan_bet; do
  echo "--- $s summary ---"
  cat ~/tsa_data/repeats/2026-11-04_$s/summary.json 2>/dev/null || echo missing
done
echo "=== CLUSTERS HEAD (ge3) ==="
for s in 103fm glz kan_bet; do
  echo "--- $s clusters.csv ---"
  head -1 ~/tsa_data/repeats/2026-11-04_$s/clusters.csv
  # show all, typically not huge
  cat ~/tsa_data/repeats/2026-11-04_$s/clusters.csv
  echo
done
echo "=== OCCURRENCES HEAD ==="
for s in 103fm glz kan_bet; do
  echo "--- $s occurrences cols ---"
  head -3 ~/tsa_data/repeats/2026-11-04_$s/occurrences.csv
  echo "rows: $(wc -l < ~/tsa_data/repeats/2026-11-04_$s/occurrences.csv)"
done
echo "=== AD TOOLS ==="
ls -lah ~/tsa_data/ad_tools/
echo "=== WHISPER VENV ==="
ls ~/talk_show_analyzer/.venv/bin/ 2>/dev/null | head -30
~/talk_show_analyzer/.venv/bin/python -c "import faster_whisper; print('faster_whisper', faster_whisper.__version__)" 2>&1 || echo no faster_whisper
which ffmpeg; ffmpeg -version 2>&1 | head -1
