#!/bin/bash
for s in 103fm glz kan_bet; do
  echo "== $s"
  cat ~/tsa_data/repeats/2026-11-04_$s/summary.json
  echo
  python3 - "$s" <<'PY'
import csv, sys
from pathlib import Path
s = sys.argv[1]
p = Path.home()/f"tsa_data/repeats/2026-11-04_{s}/clusters.csv"
rows = list(csv.DictReader(p.open()))
g3 = [r for r in rows if int(r["n_occurrences"]) >= 3]
g2 = [r for r in rows if int(r["n_occurrences"]) == 2]
air = sum(float(r["median_dur"]) * int(r["n_occurrences"]) for r in g3) / 60
print(f"clusters={len(rows)} ge3={len(g3)} eq2={len(g2)} ge3_air_min={air:.1f}")
print("top ge3:")
for r in sorted(g3, key=lambda x: -int(x["n_occurrences"]))[:10]:
    print(r["cluster_id"], r["n_occurrences"], r["median_dur"]+"s", r["kind"], r["example_wall"])
PY
  echo "--- log ---"
  cat ~/tsa_data/repeats/2026-11-04_$s.log
  echo
done
