#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:$PATH"
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/labels_103fm/2026-11-04
mkdir -p "$OUT"
cd ~/tsa_data/ad_tools
echo "=== starting label_ads_103fm $(date) ==="
$PY label_ads_103fm.py label \
  --rec-dir ~/tsa_data/recordings/2026-11-04/103fm \
  --date 2026-11-04 \
  --out "$OUT" 2>&1 | tee "$OUT/run.log"
echo "=== done $(date) ==="
ls -lah "$OUT"
if [ -f "$OUT/summary.json" ]; then cat "$OUT/summary.json"; fi
