#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:$PATH"
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/repeats/spotcheck_2026-11-04
REC=~/tsa_data/recordings/2026-11-04
mkdir -p "$OUT"

echo "=== rebuilding plan with median-length clips ==="
$PY << 'PY'
import csv, json
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
        if files and files.issubset(JUNK_FILES):
            continue
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
        cands = [o for o in occs[cid] if o["file"] not in JUNK_FILES] or occs[cid]
        def score(o):
            d = abs(float(o["duration"]) - med)
            junk_pen = 1000 if o["file"] in JUNK_FILES else 0
            # prefer occurrences at least 70% of median length
            short_pen = 100 if float(o["duration"]) < med * 0.7 else 0
            return (junk_pen, short_pen, d)
        best = sorted(cands, key=score)[0]
        start = float(best["start_sec"])
        # extract median length (capped), not the sometimes-short tagged duration
        dur = min(max(med, 4.0), 90.0)
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
        })
    selected.sort(key=lambda x: (-x["n"], -x["median_dur"]))
    strong = [x for x in selected if x["n"] >= 5]
    extras = [x for x in selected if x["n"] < 5][:8]
    if st == "glz":
        # keep strong up to 20 + ad-length extras (med>=15)
        strong = strong[:20]
        extras = [x for x in extras if x["median_dur"] >= 12][:8]
    final = strong + extras
    plan[st] = final
    print(f"=== {st}: {len(final)} clips ===")
    for x in final:
        print(f"  c{x['cluster_id']:3d} n={x['n']:3d} med={x['median_dur']:6.1f}s")

with open(OUT / "plan.json", "w") as f:
    json.dump(plan, f, indent=2, ensure_ascii=False)
print("Total:", sum(len(v) for v in plan.values()))
PY

echo "=== extracting clips with ffmpeg ==="
$PY << 'PY'
import json, subprocess
from pathlib import Path

OUT = Path.home() / "tsa_data/repeats/spotcheck_2026-11-04"
REC = Path.home() / "tsa_data/recordings/2026-11-04"
plan = json.loads((OUT / "plan.json").read_text())
for st, items in plan.items():
    sdir = OUT / st
    sdir.mkdir(parents=True, exist_ok=True)
    for x in items:
        src = REC / st / x["file"]
        dst = sdir / f"c{x['cluster_id']}.mp3"
        if dst.exists() and dst.stat().st_size > 1000:
            print(f"skip exists {dst.name}")
            continue
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(x["start"]), "-t", str(x["dur"]),
            "-i", str(src),
            "-acodec", "libmp3lame", "-q:a", "4",
            str(dst),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL {st} c{x['cluster_id']}: {r.stderr[:200]}")
        else:
            sz = dst.stat().st_size
            print(f"ok {st}/c{x['cluster_id']}.mp3 {sz}B start={x['start']} dur={x['dur']}")
print("extract done")
PY

echo "=== listing clips ==="
find "$OUT" -name 'c*.mp3' | sort | while read f; do
  ls -lh "$f"
done
echo "count: $(find "$OUT" -name 'c*.mp3' | wc -l)"
