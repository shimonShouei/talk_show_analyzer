#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:$PATH"
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/repeats/spotcheck_2026-11-04
cd "$OUT"

# Prefer small for Hebrew quality; fall back to base/tiny if download fails
$PY << 'PY'
import json, time, sys
from pathlib import Path
from faster_whisper import WhisperModel

OUT = Path.home() / "tsa_data/repeats/spotcheck_2026-11-04"
plan = json.loads((OUT / "plan.json").read_text())

model_name = "small"
print(f"Loading WhisperModel({model_name}, device=cpu, compute_type=int8)...", flush=True)
t0 = time.time()
try:
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
except Exception as e:
    print("small failed:", e)
    model_name = "base"
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
print(f"model ready in {time.time()-t0:.1f}s ({model_name})", flush=True)

results = []
for st, items in plan.items():
    for x in items:
        cid = x["cluster_id"]
        mp3 = OUT / st / f"c{cid}.mp3"
        txt = OUT / st / f"c{cid}.txt"
        if not mp3.exists():
            print(f"MISSING {mp3}", flush=True)
            continue
        if txt.exists() and txt.stat().st_size > 10:
            text = txt.read_text(encoding="utf-8").strip()
            print(f"cached {st}/c{cid}: {text[:80]}", flush=True)
        else:
            t1 = time.time()
            segments, info = model.transcribe(
                str(mp3),
                language="he",
                vad_filter=True,
                beam_size=1,
            )
            parts = [s.text.strip() for s in segments if s.text.strip()]
            text = " ".join(parts).strip()
            txt.write_text(text + "\n", encoding="utf-8")
            print(f"ok {st}/c{cid} n={x['n']} med={x['median_dur']}s ({time.time()-t1:.1f}s): {text[:120]}", flush=True)
        results.append({
            **x,
            "transcript": text,
            "model": model_name,
        })

out_json = OUT / "transcripts.json"
out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {out_json} ({len(results)} items)", flush=True)
PY
