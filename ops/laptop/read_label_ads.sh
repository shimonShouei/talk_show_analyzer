#!/bin/bash
set -euo pipefail
PY=~/talk_show_analyzer/.venv/bin/python
cd ~/tsa_data/ad_tools
$PY label_ads_103fm.py --help 2>&1
echo "===="
$PY label_ads_103fm.py label --help 2>&1 || true
echo "==== file head ===="
head -80 label_ads_103fm.py
