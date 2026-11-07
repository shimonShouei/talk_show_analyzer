"""Collect weak labels plus the hand-checked 103FM hour, and write CSVs.

The committed copies live in data/ads/. See data/ads/PROVENANCE.md.
Re-running needs SQLite databases and transcripts that are not in git.

TSA_DATA_ROOT is required. The historical box used /workspace/tsa_data.
There is no default path.
"""
import csv, json, os, re, sqlite3, sys
from pathlib import Path

B = os.environ.get("TSA_DATA_ROOT", "").strip()
if not B:
    sys.exit(
        "TSA_DATA_ROOT is required (directory with tsa_*.db, runs/, and ad_labels/raw/). "
        "The historical box used /workspace/tsa_data. Unset is refused."
    )
REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if not (REPO_SRC / "talk_show_analyzer").is_dir():
    sys.exit(f"Cannot find package source at {REPO_SRC}")
sys.path.insert(0, str(REPO_SRC))
from talk_show_analyzer.analysis.utils import extract_fenced_json
OUT = f"{B}/ad_labels"
HOUR_TX = f"{B}/runs/hour1/hour_transcript.json"
TX = {"hour1": HOUR_TX, "hour2": HOUR_TX, "gold_hour1": HOUR_TX,
      "full1": f"{B}/runs/full1/sample_transcript.json", "full2": f"{B}/runs/full2/sample_transcript.json",
      "haiku5": f"{B}/runs/haiku5/sample_transcript.json", "haiku5b": f"{B}/runs/haiku5b/sample_transcript.json",
      "haiku5c": f"{B}/runs/haiku5c/sample_transcript.json"}
DBS = {"hour1": "tsa_hour.db", "hour2": "tsa_hour2.db", "full1": "tsa_full.db", "full2": "tsa_full2.db",
       "haiku5": "tsa_haiku5.db", "haiku5b": "tsa_haiku5b.db", "haiku5c": "tsa_haiku5c.db"}
HOUR2_MERGE = {"GLOBAL_24": "GLOBAL_28", "GLOBAL_13": "GLOBAL_00", "GLOBAL_32": "GLOBAL_31"}

import functools
@functools.lru_cache(None)
def segs(run):
    try: return json.load(open(TX[run]))["segments"]
    except FileNotFoundError: return []

def snippet(run, a, b, n=120):
    t = " ".join(s["text"].strip() for s in segs(run) if s["end"] > a and s["start"] < b)
    return t[:n]

def title_label(t):
    if re.search(r"פרסומ|בלוק פרסומות|קטע פרסומי", t): return "ad"
    if re.search(r"זיהוי תחנה|הודעות שידור|מעבר", t): return "station_id"
    if re.search(r"חדשות", t): return "news"
    if re.search(r"מזג אוויר|תחזית", t): return "news"   # weather is part of the news block
    if re.search(r"סיום התוכנית|קרדיטים", t): return "content"  # host outro = show content
    return None

PART_MAP = {"news": "news", "commercial": "ad", "jingle": "jingle"}
rows = []
def add(run, src_file, a, b, label, source, conf="", raw=""):
    rows.append(dict(run=run, source_file=src_file, start=round(a, 2), end=round(b, 2),
                     duration=round(b - a, 2), label=label, label_source=source,
                     confidence=conf, raw_label=raw, text_snippet=snippet(run, a, b)))

# 1) raw per-chunk outputs from the Anthropic batch results (hour1, hour2, haiku5c)
for run in ("hour1", "hour2", "haiku5c"):
    for o in json.load(open(f"{OUT}/raw/{run}_chunks.json")):
        try: d = extract_fenced_json(o["text"])
        except Exception: continue
        src = f"batch:{run}:{o['custom_id']}"
        tops = d.get("topics", [])
        if d.get("part_type") in PART_MAP and tops:
            add(run, src, min(t["start"] for t in tops), max(t["end"] for t in tops),
                PART_MAP[d["part_type"]], "chunk.part_type", "", d["part_type"])
        for t in tops:
            lab = title_label(t.get("tentative_title_he", ""))
            if lab and lab != "content":
                add(run, src, t["start"], t["end"], lab, "chunk.topic_title", "", t.get("tentative_title_he"))

# 2) DB: parts table, merged topics (category other), speakers with role media_clip
for run, db in DBS.items():
    c = sqlite3.connect(f"{B}/{db}")
    for typ, a, b in c.execute("select type,start_seconds,end_seconds from parts"):
        if typ in PART_MAP: add(run, f"{db}:parts", a, b, PART_MAP[typ], "parts.type", "", typ)
    for title, cat, spans in c.execute("select merged_title_he,category,time_spans from merged_topics"):
        lab = title_label(title)
        if cat == "other" or lab not in (None, "content"):
            for a, b in json.loads(spans):
                add(run, f"{db}:merged_topics", a, b, lab or "other", "merged_topics.title", "", f"{title} [{cat}]")
    mc = {lab: conf for lab, conf in c.execute(
        "select speaker_label,confidence from speaker_identities where role='media_clip'")}
    for s in segs(run):
        lab = HOUR2_MERGE.get(s["speaker"], s["speaker"]) if run == "hour2" else s["speaker"]
        if lab in mc:
            add(run, f"{db}:speaker_identities", s["start"], s["end"], "media_clip",
                "speaker_role=media_clip", round(mc[lab], 2), lab)

# 3) hand-checked reference for hour1 (read from the transcript, snapped to segment times)
GOLD = [
 (0, 14, "ad", "Maccabi app (stream pre-roll on connect)"),
 (268, 278, "station_id", "'אתם מאזינים לחמש בערב... ובשש ספורט ב-103FM'"),
 (279, 287, "ad", "Asaf Granit / Dekel kitchen"),
 (287, 338, "ad", "'Dubale' – Welfare ministry campaign"),
 (339, 363, "ad", "Rabin Center museum"),
 (363, 399, "ad", "Duty Free / James Richardson"),
 (399, 415, "ad", "Black November"),
 (416, 431, "ad", "Melisron apartments"),
 (431, 456, "ad", "Pandor doors"),
 (457, 461, "promo", "'ובשש ספורט ב-103FM'"),
 (786, 811, "promo", "'ספורט עם משה פרימו, יוני היללי ויניב תוכמן'"),
 (812, 814, "jingle", "'מאה ושלוש'"),
 (816, 841, "ad", "Sport 1 channels"),
 (841, 894, "ad", "'חצי חינם' supermarket"),
 (894, 911, "ad", "Beko"),
 (912, 919, "ad", "Richard Clayderman concert"),
 (922, 936, "ad", "Partner phones"),
 (936, 961, "ad", "Egg council"),
 (961, 982, "ad", "China shopping month"),
 (982, 990, "ad", "Gulliver travel"),
 (991, 1089, "news", "news bulletin"),
 (1089, 1116, "ad", "Shufersal loan (part 1)"),
 (1116, 1132, "news", "weather"),
 (1132, 1145, "ad", "Shufersal loan (part 2)"),
 (1145, 1157, "ad", "TV series package"),
 (1158, 1190, "promo", "news credit + 'ב-103FM ספורט עם...'"),
 (1951, 1965, "ad", "Maccabi app (stream pre-roll on reconnect)"),
 (2847, 2860, "ad", "Maccabi app (stream pre-roll on reconnect)"),
 (2895, 2908, "ad", "Maccabi app (stream pre-roll on reconnect)"),
 (3097, 3099, "jingle", "'מאה ושלוש' (at a reconnect)"),
 (3195, 3208, "ad", "Maccabi app (stream pre-roll on reconnect)"),
 (3239, 3252, "ad", "Maccabi app (stream pre-roll on reconnect)"),
 (3273, 3286, "ad", "Maccabi app (stream pre-roll on reconnect)"),
]
DUR = 3294.36
with open(f"{OUT}/gold_hour1.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["start", "end", "duration", "label", "note", "text_snippet"])
    for a, b, l, n in GOLD: w.writerow([a, b, b - a, l, n, snippet("hour1", a, b)])
for a, b, l, n in GOLD:
    add("gold_hour1", "manual (transcript read)", a, b, l, "manual_reference", "", n)

with open(f"{OUT}/labels.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

# 4) stats + per-second agreement of each Claude source with the reference (hour runs)
def secs(spans):
    s = set()
    for a, b in spans: s.update(range(int(a), int(b + 0.999)))
    return s
nc = {"ad", "jingle", "station_id", "promo", "news"}
gold_nc = secs((a, b) for a, b, l, _ in GOLD)
stats = {"gold": {}}
for l in sorted({g[2] for g in GOLD}):
    sp = [(a, b) for a, b, ll, _ in GOLD if ll == l]
    stats["gold"][l] = {"count": len(sp), "minutes": round(sum(b - a for a, b in sp) / 60, 2)}
stats["gold"]["non_content_minutes"] = round(len(gold_nc) / 60, 2)
stats["gold"]["non_content_pct"] = round(100 * len(gold_nc) / DUR, 1)
stats["agreement"] = {}
for run in ("hour1", "hour2"):
    for src in ("chunk.part_type", "chunk.topic_title", "parts.type", "merged_topics.title", "speaker_role=media_clip"):
        sp = [(r["start"], r["end"]) for r in rows if r["run"] == run and r["label_source"] == src
              and (r["label"] in nc or r["label"] in ("other", "media_clip"))]
        if src == "merged_topics.title":
            sp = [(r["start"], r["end"]) for r in rows if r["run"] == run and r["label_source"] == src and r["label"] != "content"]
        p = secs(sp)
        if not p: continue
        tp = len(p & gold_nc)
        stats["agreement"][f"{run}:{src}"] = {
            "spans": len(sp), "labeled_sec": len(p), "precision": round(tp / len(p), 2),
            "recall": round(tp / len(gold_nc), 2)}
    allp = secs([(r["start"], r["end"]) for r in rows if r["run"] == run and r["label"] != "content"
                 and r["label_source"] != "speaker_role=media_clip"])
    tp = len(allp & gold_nc)
    stats["agreement"][f"{run}:ALL_except_media_clip"] = {"labeled_sec": len(allp), "precision": round(tp / len(allp), 2), "recall": round(tp / len(gold_nc), 2)}
json.dump(stats, open(f"{OUT}/stats.json", "w"), ensure_ascii=False, indent=1)
print(len(rows), "rows"); print(json.dumps(stats, ensure_ascii=False, indent=1))
