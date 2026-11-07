#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:$PATH"
PY=~/talk_show_analyzer/.venv/bin/python
OUT=~/tsa_data/repeats/spotcheck_2026-11-04

# Re-transcribe empty clips without VAD (often music/jingles)
$PY << 'PY'
import json, time
from pathlib import Path
from faster_whisper import WhisperModel

OUT = Path.home() / "tsa_data/repeats/spotcheck_2026-11-04"
results = json.loads((OUT / "transcripts.json").read_text(encoding="utf-8"))
empty = [r for r in results if not (r.get("transcript") or "").strip()]
print(f"empty clips: {len(empty)}", flush=True)
if empty:
    model = WhisperModel("small", device="cpu", compute_type="int8")
    for r in empty:
        st, cid = r["station"], r["cluster_id"]
        mp3 = OUT / st / f"c{cid}.mp3"
        t1 = time.time()
        segments, info = model.transcribe(str(mp3), language="he", vad_filter=False, beam_size=1)
        parts = [s.text.strip() for s in segments if s.text.strip()]
        text = " ".join(parts).strip()
        # also try English hint if still empty-ish and short music
        if len(text) < 3:
            segments, info = model.transcribe(str(mp3), vad_filter=False, beam_size=1)
            parts = [s.text.strip() for s in segments if s.text.strip()]
            text = " ".join(parts).strip()
        r["transcript"] = text
        r["retried_no_vad"] = True
        (OUT / st / f"c{cid}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"retry {st}/c{cid}: {text[:140]}", flush=True)
    (OUT / "transcripts.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("updated transcripts.json", flush=True)
PY

$PY << 'PY'
import csv, json
from collections import defaultdict
from pathlib import Path

OUT = Path.home() / "tsa_data/repeats/spotcheck_2026-11-04"
REP = Path.home() / "tsa_data/repeats"
results = json.loads((OUT / "transcripts.json").read_text(encoding="utf-8"))

# Manual/heuristic classification rules (keywords)
# Returns (label, reason)

def classify(r):
    t = (r.get("transcript") or "").strip()
    tl = t.lower()
    n = r["n"]
    med = r["median_dur"]
    st = r["station"]
    cid = r["cluster_id"]

    # Hard overrides from listening to transcripts (spotcheck judgments)
    overrides = {
        ("103fm", 1): ("ad", "דקל כמילה / מטבח — פרסומת מוצר"),
        ("103fm", 9): ("ad", "שופרסל — מבצע עד 20000 שקלים"),
        ("103fm", 5): ("ad", "תיירות/סיורים/מלונות — פרסומת"),
        ("103fm", 19): ("station_jingle_or_promo", "הודעת נשיא/התייעצויות להרכבת ממשלה — תשדיר חוזר"),
        ("103fm", 47): ("station_jingle_or_promo", "שירייה הלב — ג'ינגל/שיר תחנה"),
        ("103fm", 2): ("ad", "פדריק / מסעדה — פרסומת"),
        ("103fm", 6): ("news_or_show", "חדשות על בחירות בארה״ב"),
        ("103fm", 24): ("unknown", "קטע דיבור קצר לא ברור"),
        ("glz", 21): ("ad", "בחסות ביטוח ישיר — פרסומת/ספונסר"),
        ("glz", 4): ("station_jingle_or_promo", "פתיח תוכנית — עכשיו בגלי צה״ל"),
        ("glz", 1): ("station_jingle_or_promo", "אתם מאזינים לגלי צה״ל — זהות תחנה"),
        ("glz", 18): ("ad", "בחסות פריסבי / מכוניות — פרסומת"),
        ("glz", 13): ("ad", "רלב״ד / תאונות דרכים — תשדיר פרסומי/שירות"),
        ("glz", 2): ("ad", "משרד הרווחה 118 — תשדיר ממשלתי"),
        ("glz", 30): ("station_jingle_or_promo", "פתיח תוכנית בגלי צה״ל"),
        ("glz", 15): ("station_jingle_or_promo", "מהדורת החדשות של גלי צה״ל — באמפר"),
        ("glz", 9): ("ad", "אזהרת הונאות / מס״ב — תשדיר שירות"),
        ("glz", 33): ("news_or_show", "יועצת משפטית לממשלה — תוכן חדשותי"),
        ("glz", 28): ("news_or_show", "הודעת תנועה / סגירת כביש — מידע תחנה"),
        ("glz", 22): ("ad", "מופע/קונצרט נונה — פרסומת אירוע"),
        ("glz", 14): ("station_jingle_or_promo", "פרומו לפודקאסט אספארטה"),
        ("glz", 3): ("station_jingle_or_promo", "פרומו ליומן הערב"),
        ("glz", 39): ("station_jingle_or_promo", "פתיח תוכנית שמואל"),
        ("glz", 16): ("news_or_show", "חדשות בחירות ארה״ב"),
        ("glz", 11): ("ad", "סרטן השד / בדיקה — תשדיר בריאות"),
        ("glz", 35): ("station_jingle_or_promo", "הודעת נשיא על הרכבת ממשלה"),
        ("glz", 5): ("ad", "ביחד בשבילך / הסתדרות — פרסומת"),
        ("kan_bet", 1): ("station_jingle_or_promo", "באמפר חדשות כאן ב׳ + ספונסר קוקידנט — זהות תחנה (120×)"),
        ("kan_bet", 18): ("news_or_show", "אזהרה על ערעור תוצאות בחירות — תוכן/PSA"),
        ("kan_bet", 26): ("station_jingle_or_promo", "הודעת נשיא על הרכבת ממשלה"),
        ("kan_bet", 6): ("ad", "מנוי פייס / כוכבית 39 — פרסומת"),
        ("kan_bet", 5): ("ad", "דקל כמילה — פרסומת (או ספונסר)"),
        ("kan_bet", 45): ("news_or_show", "דיון פוליטי על יום השבת"),
        ("kan_bet", 10): ("news_or_show", "קטע שיחה/תוכנית — איליי בן דוד"),
        ("kan_bet", 2): ("station_jingle_or_promo", "פרויקט הנצחה חרבות ברזל — פרומו תחנה"),
    }
    if (st, cid) in overrides:
        return overrides[(st, cid)]

    if not t:
        if med <= 12 and n >= 5:
            return ("station_jingle_or_promo", "בלי דיבור / מוזיקה קצרה חוזרת — כנראה ג'ינגל")
        return ("unknown", "תמלול ריק")

    # keyword heuristics for remaining
    ad_kw = ["בחסות", "כוכבית", "שקלים", "להצטרף", "מבצע", "לחסוך", "הזמינו", "באתר", "www", "פרסומת"]
    station_kw = ["גלי צהל", "גלי צה״ל", "כאן ב", "103", "אתם מאזינים", "מהדורת החדשות", "עכשיו ב"]
    news_kw = ["דמוקרטים", "רפובליקנים", "בחירות", "הכנסת", "צה״ל הודיע"]

    if any(k in t for k in ad_kw) or any(k in tl for k in ["http", "www."]):
        return ("ad", "מילות מפתח פרסומיות: " + t[:80])
    if any(k in t for k in station_kw):
        return ("station_jingle_or_promo", "מילות זהות תחנה: " + t[:80])
    if any(k in t for k in news_kw):
        return ("news_or_show", "תוכן חדשותי: " + t[:80])
    if "make me" in tl or "la la" in tl:
        return ("station_jingle_or_promo", "מוזיקת ג'ינגל: " + t[:80])
    return ("unknown", "לא סווג אוטומטית: " + t[:100])

# load occurrence totals for airtime: sum of durations per cluster (capped? use actual occ durations)
air = {}
for st in ["103fm", "glz", "kan_bet"]:
    opath = REP / f"2026-11-04_{st}" / "occurrences.csv"
    by = defaultdict(float)
    with open(opath, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("cluster_id") == "cluster_id":
                continue
            by[int(row["cluster_id"])] += float(row["duration"])
    air[st] = by

classified = []
for r in results:
    label, reason = classify(r)
    cid = r["cluster_id"]
    st = r["station"]
    # estimated airtime for this cluster = n * median (more stable than sum of variable lengths)
    est_sec = r["n"] * r["median_dur"]
    sum_sec = air[st].get(cid, 0.0)
    classified.append({
        **{k: r[k] for k in ["station","cluster_id","n","median_dur","file","start","dur","wall","transcript"]},
        "label": label,
        "reason": reason,
        "est_airtime_sec_n_x_med": round(est_sec, 1),
        "sum_occ_dur_sec": round(sum_sec, 1),
    })

(OUT / "classifications.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")

# per-station summary
print("\n======== CLASSIFICATIONS ========")
for st in ["103fm", "glz", "kan_bet"]:
    rows = [c for c in classified if c["station"] == st]
    print(f"\n### {st} checked={len(rows)}")
    counts = defaultdict(int)
    ad_air = 0.0
    for c in rows:
        counts[c["label"]] += 1
        flag = {"ad":"AD", "station_jingle_or_promo":"JINGLE/PROMO", "news_or_show":"NEWS", "unknown":"UNK", "reconnect_artifact":"RECONN"}[c["label"]]
        print(f"  c{c['cluster_id']:3d} n={c['n']:3d} med={c['median_dur']:5.1f}s air~{c['est_airtime_sec_n_x_med']/60:5.1f}m  [{flag}] {c['reason'][:70]}")
        print(f"       txt: {(c['transcript'] or '')[:100]}")
        if c["label"] == "ad":
            ad_air += c["est_airtime_sec_n_x_med"]
    print(f"  counts: {dict(counts)}")
    print(f"  estimated ad airtime from checked AD clusters (n*median): {ad_air/60:.1f} min")

# also compute ge3 totals from clusters.csv for context
for st in ["103fm", "glz", "kan_bet"]:
    cpath = REP / f"2026-11-04_{st}" / "clusters.csv"
    ge3 = []
    with open(cpath, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("cluster_id") == "cluster_id": continue
            if int(row["n_occurrences"]) >= 3:
                ge3.append(row)
    total_spot = sum(int(r["n_occurrences"]) * float(r["median_dur"]) for r in ge3) / 60
    print(f"{st} all ge3 clusters: {len(ge3)}, n*median total ~{total_spot:.1f} min")
PY
