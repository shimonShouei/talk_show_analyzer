#!/bin/bash
set -euo pipefail
PY=~/talk_show_analyzer/.venv/bin/python
# label_ads may need requests etc from system or ad_tools env
cd ~/tsa_data/ad_tools
python3 label_ads_103fm.py --help 2>&1 || true
echo "===="
python3 label_ads_103fm.py label --help 2>&1 || true
echo "==== discover ===="
python3 label_ads_103fm.py discover --help 2>&1 || true
echo "==== eval_repeats ===="
python3 eval_repeats.py --help 2>&1 || true
echo "==== eval_podlabels ===="
python3 eval_podlabels.py --help 2>&1 || true
