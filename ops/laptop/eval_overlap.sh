#!/bin/bash
set -euo pipefail
PY=~/talk_show_analyzer/.venv/bin/python
cd ~/tsa_data/ad_tools
echo "=== eval_podlabels ==="
sed -n '1,80p' eval_podlabels.py
echo "=== eval_repeats ==="
sed -n '1,80p' eval_repeats.py
echo "=== spans head ==="
head -20 ~/tsa_data/labels_103fm/2026-11-04/spans.csv
echo "=== try rough overlap ==="
$PY << 'PY'
import csv
from pathlib import Path
from collections import defaultdict

# Build set of ad_candidate second ranges per file from podcast labels
spans = []
with open(Path.home()/ "tsa_data/labels_103fm/2026-11-04/spans.csv", newline="") as f:
    for row in csv.DictReader(f):
        if row.get("label") == "ad_candidate":
            spans.append((row["file"], float(row["start_sec"]), float(row["end_sec"])))
print("ad_candidate spans:", len(spans), "total_min", sum(e-s for _,s,e in spans)/60)

# Load ge3 occurrences for 103fm
occs = []
with open(Path.home()/ "tsa_data/repeats/2026-11-04_103fm/occurrences.csv", newline="") as f:
    for row in csv.DictReader(f):
        if row.get("cluster_id") == "cluster_id": continue
        if int(row["n_occurrences"]) >= 3:
            occs.append((row["file"], float(row["start_sec"]), float(row["end_sec"]), int(row["cluster_id"]), int(row["n_occurrences"])))
print("ge3 occurrences:", len(occs))

def overlap(a0,a1,b0,b1):
    return max(0.0, min(a1,b1)-max(a0,b0))

# For each ge3 occ, how much overlaps ad_candidate
hit_sec = 0.0
tot_sec = 0.0
by_c = defaultdict(lambda: [0.0, 0.0])  # overlap, total
for file, s, e, cid, n in occs:
    dur = e-s
    tot_sec += dur
    ov = 0.0
    for f2, s2, e2 in spans:
        if f2 != file: continue
        ov += overlap(s, e, s2, e2)
    hit_sec += ov
    by_c[cid][0] += ov
    by_c[cid][1] += dur

print(f"ge3 occ seconds overlapping podcast ad_candidate: {hit_sec/60:.1f} / {tot_sec/60:.1f} min ({100*hit_sec/max(tot_sec,1):.1f}%)")
print("Note: podcast labels only cover show windows (~3 programs); most of day is unaligned.")
print("Per checked strong clusters (overlap within show windows only):")
# load classifications of interest
import json
cls = json.loads((Path.home()/"tsa_data/repeats/spotcheck_2026-11-04/classifications.json").read_text(encoding="utf-8"))
for c in cls:
    if c["station"] != "103fm": continue
    cid = c["cluster_id"]
    ov, tot = by_c.get(cid, [0,0])
    print(f"  c{cid} label={c['label']} n={c['n']} overlap_in_shows={ov:.1f}s / occ={tot:.1f}s")
PY
