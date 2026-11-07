"""eval_repeats.py OCC_CSV GOLD_CSV FILE_NAME [MIN_OCC] - per-second agreement of repeat occurrences with gold spans."""
import csv, sys, numpy as np
occ, gold, fname = sys.argv[1:4]; mo = int(sys.argv[4]) if len(sys.argv) > 4 else 2
G = list(csv.DictReader(open(gold, encoding="utf-8")))
T = int(max(float(g["end"]) for g in G)) + 600
lab = np.full(T, "", object)
for g in G: lab[int(float(g["start"])):int(float(g["end"]))] = g["label"]
rep = np.zeros(T, bool)
for r in csv.DictReader(open(occ, encoding="utf-8")):
    if r["file"] == fname and int(r["n_occurrences"]) >= mo and r["kind"] == "spot":
        rep[int(float(r["start_sec"])):min(T, int(float(r["end_sec"])))] = True
print(f"min_occ={mo}: repeated seconds={rep.sum()}")
for L in sorted(set(lab) - {""}):
    m = lab == L; print(f"  gold {L:11s} {m.sum():5d}s  covered by repeats {100*(rep&m).sum()/m.sum():5.1f}%")
nc = lab != ""; print(f"  ALL non-content gold covered: {100*(rep&nc).sum()/nc.sum():.1f}%  | precision (repeat secs inside gold non-content): {100*(rep&nc).sum()/max(rep.sum(),1):.1f}%")
# span-level: gold ad spans with >=50% covered
ads = [g for g in G if g["label"] == "ad"]
hit = [g for g in ads if rep[int(float(g['start'])):int(float(g['end']))].mean() >= .5]
print(f"  gold ad spans >=50% covered: {len(hit)}/{len(ads)}; distinct ads hit: {len(set(g['note'] for g in hit))}/{len(set(g['note'] for g in ads))}")
