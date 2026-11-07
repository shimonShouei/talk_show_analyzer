#!/bin/bash
set -euo pipefail
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/repeats/spotcheck_2026-11-04
mkdir -p "$OUT"
$PY << 'PY'
import csv, json, os
from collections import defaultdict
from pathlib import Path

BASE = Path.home() / "tsa_data"
REC = BASE / "recordings" / "2026-11-04"
REP = BASE / "repeats"
OUT = REP / "spotcheck_2026-11-04"
OUT.mkdir(parents=True, exist_ok=True)

JUNK_FILES = {
    "part01_150850.mp3",
    "part02_235841.mp3", "part03_235847.mp3", "part04_235853.mp3",
    "part02_235808.mp3", "part02_235858.mp3",
}

stations = ["103fm", "glz", "kan_bet"]
plan = {}

for st in stations:
    cpath = REP / f"2026-11-04_{st}" / "clusters.csv"
    opath = REP / f"2026-11-04_{st}" / "occurrences.csv"
    clusters = []
    with open(cpath, newline="") as f:
        seen_header = False
        for row in csv.DictReader(f):
            if row.get("cluster_id") == "cluster_id":
                continue
            clusters.append(row)
    occs = defaultdict(list)
    with open(opath, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("cluster_id") == "cluster_id":
                continue
            occs[int(row["cluster_id"])].append(row)

    selected = []
    for c in clusters:
        cid = int(c["cluster_id"])
        n = int(c["n_occurrences"])
        med = float(c["median_dur"])
        kind = c.get("kind", "")
        files = {o["file"] for o in occs[cid]}
        only_junk = files and files.issubset(JUNK_FILES)
        if only_junk:
            continue
        # skip long kind (usually show content replay)
        pick = False
        reason = ""
        if n >= 5 and med <= 90:
            pick = True
            reason = f"n>={n}"
        elif n >= 3 and 15 <= med <= 60:
            pick = True
            reason = f"adlen n={n} med={med}"
        elif n >= 4 and 10 <= med <= 90:
            pick = True
            reason = f"n4+ med={med}"
        if not pick:
            continue
        # pick representative occurrence: closest duration to median, prefer main files
        cands = [o for o in occs[cid] if o["file"] not in JUNK_FILES]
        if not cands:
            cands = occs[cid]
        def score(o):
            d = abs(float(o["duration"]) - med)
            junk_pen = 1000 if o["file"] in JUNK_FILES else 0
            # prefer not-first if first is very long outlier
            return (junk_pen, d)
        best = sorted(cands, key=score)[0]
        start = float(best["start_sec"])
        dur = min(float(best["duration"]), 90.0)
        # if duration much longer than median, clip to median+2
        if float(best["duration"]) > med * 1.5 and med > 5:
            dur = min(med + 2.0, 90.0)
        selected.append({
            "station": st,
            "cluster_id": cid,
            "n": n,
            "median_dur": med,
            "kind": kind,
            "reason": reason,
            "file": best["file"],
            "start": start,
            "dur": round(dur, 2),
            "wall": best.get("wall_start", ""),
            "occ_dur": float(best["duration"]),
            "n_files": len(files),
        })
    # sort by n desc then median
    selected.sort(key=lambda x: (-x["n"], -x["median_dur"]))
    # cap: take all n>=5, then up to 8 more ad-length
    strong = [x for x in selected if x["n"] >= 5]
    extras = [x for x in selected if x["n"] < 5][:8]
    # for glz which has many, keep all n>=5 up to 25 and extras
    if st == "glz" and len(strong) > 25:
        strong = strong[:25]
    final = strong + extras
    plan[st] = final
    print(f"=== {st}: selected {len(final)} of {len(selected)} candidates (ge3 clusters total filtered) ===")
    for x in final:
        print(f"  c{x['cluster_id']:3d} n={x['n']:3d} med={x['median_dur']:6.1f}s clip={x['dur']:5.1f}s from {x['file']}@{x['start']:.1f} ({x['reason']})")

with open(OUT / "plan.json", "w") as f:
    json.dump(plan, f, indent=2, ensure_ascii=False)
print("Wrote", OUT / "plan.json")
print("Total clips:", sum(len(v) for v in plan.values()))
PY
