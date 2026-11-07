#!/bin/bash
# Historical spot-check refine step, then a copy onto the Windows profile.
# Labels it writes are provisional transcription labels. Not run during integration.
set -euo pipefail
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$_d/../require_win_user.sh"
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/repeats/spotcheck_2026-11-04
$PY << 'PY'
import json
from pathlib import Path
from collections import defaultdict
OUT = Path.home() / "tsa_data/repeats/spotcheck_2026-11-04"
rows = json.loads((OUT / "classifications.json").read_text(encoding="utf-8"))
# refinements
fixes = {
    ("103fm", 21): ("station_jingle_or_promo", "תודה רבה — מעבר/ג'ינגל קצר"),
    ("103fm", 41): ("station_jingle_or_promo", "תודה רבה — מעבר/ג'ינגל קצר"),
    ("103fm", 25): ("unknown", "תמלול רועש/לא ברור"),
    ("glz", 63): ("station_jingle_or_promo", "תודה רבה — מעבר תחנה"),
    ("glz", 78): ("station_jingle_or_promo", "תודה רבה — מעבר תחנה"),
    ("glz", 66): ("station_jingle_or_promo", "תודה — מעבר תחנה"),
    ("glz", 77): ("station_jingle_or_promo", "תודה רבה — מעבר תחנה"),
    ("glz", 65): ("station_jingle_or_promo", "תודה — מעבר תחנה"),
    ("glz", 60): ("ad", "פרסומת נדלן / כל דירה גו"),
    ("kan_bet", 41): ("station_jingle_or_promo", "תודה — מעבר תחנה"),
    ("kan_bet", 78): ("station_jingle_or_promo", "מוזיקת ג'ינגל באנגלית"),
    ("kan_bet", 84): ("station_jingle_or_promo", "מוזיקת ג'ינגל באנגלית"),
}
for r in rows:
    key = (r["station"], r["cluster_id"])
    if key in fixes:
        r["label"], r["reason"] = fixes[key]
(OUT / "classifications.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
for st in ["103fm","glz","kan_bet"]:
    rs = [r for r in rows if r["station"]==st]
    counts = defaultdict(int)
    ad_air = 0.0
    j_air = 0.0
    for r in rs:
        counts[r["label"]] += 1
        if r["label"]=="ad":
            ad_air += r["est_airtime_sec_n_x_med"]
        if r["label"]=="station_jingle_or_promo":
            j_air += r["est_airtime_sec_n_x_med"]
    print(st, dict(counts), f"ad_min={ad_air/60:.1f}", f"jingle_min={j_air/60:.1f}")
PY
# pack key outputs to Windows path for CopyToBox from parent... we'll cat to a shareable place
cp "$OUT/classifications.json" "/mnt/c/Users/${WIN_USER}/spotcheck_classifications.json"
cp "$OUT/transcripts.json" "/mnt/c/Users/${WIN_USER}/spotcheck_transcripts.json"
cp "$OUT/plan.json" "/mnt/c/Users/${WIN_USER}/spotcheck_plan.json"
ls -lah "/mnt/c/Users/${WIN_USER}/spotcheck_"*.json
