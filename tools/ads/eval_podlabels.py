"""eval_podlabels.py SPANS_CSV GOLD_CSV FILE - per-second agreement of podcast-diff labels with gold (aligned windows only)."""
import csv, sys, numpy as np
sp, gold, fn = sys.argv[1:4]
G = list(csv.DictReader(open(gold, encoding="utf-8"))); S = [r for r in csv.DictReader(open(sp, encoding="utf-8")) if r["file"] == fn]
T = int(max(float(r["end_sec"]) for r in S)) + 1
g = np.zeros(T, bool); gl = np.full(T, "", object)
for x in G: g[int(float(x["start"])):int(float(x["end"]))] = True; gl[int(float(x["start"])):int(float(x["end"]))] = x["label"]
pred = np.zeros(T, bool); win = np.zeros(T, bool)
for r in S:
    s, e = int(float(r["start_sec"])), int(float(r["end_sec"]))
    if r["label"] != "unaligned": win[s:e] = True
    if r["label"] == "ad_candidate": pred[s:e] = True
tp = (pred & g & win).sum(); print(f"aligned window {win.sum()}s; gold non-content in window {(g&win).sum()}s")
print(f"precision {100*tp/max((pred&win).sum(),1):.1f}%  recall {100*tp/max((g&win).sum(),1):.1f}%")
for L in sorted(set(gl[win]) - {""}): m = (gl == L) & win; print(f"  {L:10s} {m.sum():4d}s caught {100*(pred&m).sum()/m.sum():.0f}%")
