#!/bin/bash
set -euo pipefail
echo "=== which pythons ==="
which -a python3 python 2>/dev/null || true
echo "=== talk_show venv ==="
~/talk_show_analyzer/.venv/bin/python -c "import numpy,requests,scipy; print('venv ok', numpy.__version__)"
echo "=== pip user ==="
python3 -c "import numpy; print(numpy.__version__)" 2>&1 || true
echo "=== find site packages ==="
ls ~/tsa_data/ 2>/dev/null
ls ~/tsa_data/ad_venv 2>/dev/null || true
ls ~/tsa_data/.venv 2>/dev/null || true
# how did overnight run work?
head -40 ~/tsa_data/ad_tools/run_repeats_night.sh
echo "===="
head -5 ~/tsa_data/repeats/2026-11-04_103fm.log
# check systemd unit
systemctl --user cat tsa-repeats.service 2>/dev/null | head -40 || true
ls ~/.config/systemd/user/ 2>/dev/null
