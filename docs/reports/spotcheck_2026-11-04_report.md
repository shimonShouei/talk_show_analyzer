# Correction (read this first)

This file is the 2026-11-05 writeup. It is kept as the historical record, including sentences that went further than the check. Those sentences are not a validation result.

- Fingerprint groups were not fully validated. The check transcribed one clip from each selected cluster. That does not show that every member of the cluster is the same segment.
- The 103FM 74× group and the Kan Bet 120× group are dubious. A high count can be over-merging or padding. Do not treat either group as a confirmed commercial.
- `recurring_spot_minutes`, and airtime computed as n × median duration, are repeated audio time. They are not commercial ad minutes.
- The labels in the tables are provisional. They come from one faster-whisper transcript per clip.
- Podcast `ad_candidate` minutes mix ads, news, promos, and jingles, and only inside the shows that had a full podcast that day.

The original notes follow.

---

# Spot-check: repeated-segment clusters — 2026-11-04

**When:** 2026-11-05 morning (Asia/Jerusalem)  
**Data:** `~/tsa_data/repeats/2026-11-04_{103fm,glz,kan_bet}/`  
**Clips + transcripts:** `~/tsa_data/repeats/spotcheck_2026-11-04/{station}/c{id}.mp3|.txt`  
**Classifications JSON:** same folder `classifications.json`  
**Method:** pick strong clusters (n≥5, plus some 15–60s with n=3–4), skip tiny reconnect/end junk files, extract median-length clip (cap 90s), transcribe with faster-whisper `small` CPU Hebrew.

Overnight repeats summary (ge3 = ≥3 occurrences):

| Station | Audio hours | ge3 clusters | Recurring spot-min (tool) |
|---------|-------------|--------------|---------------------------|
| 103FM   | 15.01       | 17           | 136.8                     |
| GLZ     | 15.02       | 55           | 92.7                      |
| Kan Bet | 14.98       | 23           | 117.7                     |

---

## Classification counts (checked clusters only)

| Station | Checked | ad | station_jingle_or_promo | news_or_show | unknown |
|---------|---------|----|-------------------------|--------------|---------|
| 103FM   | 12      | 4  | 4                       | 1            | 3       |
| GLZ     | 28      | 9  | 14                      | 3            | 2       |
| Kan Bet | 15      | 2  | 7                       | 3            | 3       |
| **Total** | **55** | **15** | **25**               | **7**        | **8**   |

Estimated airtime of **checked clusters labeled ad** (n × median_dur):

| Station | Est. ad min (checked AD only) | Notes |
|---------|-------------------------------|-------|
| 103FM   | ~89.5                         | Dominated by c1 Dekel 74×60.7s (~75m) — may over-count if matches are padded |
| GLZ     | ~28.7                         | Mix of commercial + gov/PSA spots |
| Kan Bet | ~2.3                          | Few clear commercial clusters among top repeats |

---

## Top findings / mislabels (jingles vs ads)

### 103FM
| ID | n | med | Label | What it is |
|----|---|-----|-------|------------|
| **1** | **74** | **60.7s** | **ad** | **דקל כמילה** kitchen brand — strongest commercial cluster |
| 9 | 10 | 72.6s | ad | שופרסל promo (כוכבית 583, עד 20k ₪) |
| 5 | 6 | 14.5s | ad | Tourism / hotels |
| 2 | 5 | 13.0s | ad | פדריק restaurant |
| 47 | 5 | 19.1s | jingle/promo | "שירייה הלב" station song |
| 19 | 6 | 8.5s | jingle/promo | Presidential consultation PSA (הרכבת ממשלה) |
| 6 | 3 | 32.0s | news | US election news repeat |

**Takeaway:** The n=74 cluster is a **real ad**, not station ID. Station identity here shows up more as short "תודה רבה" bumpers and the heart song.

### GLZ
| ID | n | med | Label | What it is |
|----|---|-----|-------|------------|
| 21 | 20 | 11.3s | ad | Sponsor **ביטוח ישיר** |
| 4 | 16 | 7.9s | jingle/promo | "עכשיו בגלי צה״ל" program open |
| **1** | **15** | **5.3s** | **jingle/promo** | **"אתם מאזינים לגלי צה״ל"** — station ID |
| 18 | 14 | 11.3s | ad | פריסבי cars |
| 13 | 11 | 36.9s | ad | רלב״ד road safety PSA |
| 2 | 11 | 35.2s | ad | משרד הרווחה 118 |
| 15 | 9 | 11.3s | jingle/promo | News edition bumper |
| many | 7–12 | ~5–10s | jingle/promo | "תודה רבה" thank-you transitions |

**Takeaway:** Highest-frequency short clusters are **station ID / thank-you / program opens**. Real ads exist but are mixed with PSAs and promos. GLZ has the most ge3 clusters (55) but many are short bumpers.

### Kan Bet
| ID | n | med | Label | What it is |
|----|---|-----|-------|------------|
| **1** | **120** | **34.9s** | **jingle/promo** | **Hourly news bumper + Cocident denture sponsor** — dominates the day (~70 min n×med) |
| 6 | 6 | 13.1s | ad | מנוי פייס (*39) |
| 5 | 5 | 11.8s | ad | דקל כמילה |
| 26 | 6 | 29.5s | jingle/promo | Presidential PSA |
| 2 | 4 | 13.5s | jingle/promo | הנצחה חרבות ברזל promo |
| 18/45/10 | 4–7 | ~15–26s | news/show | Political / show fragments |

**Takeaway:** The **top cluster is NOT a pure commercial** — it is station news packaging with an embedded sponsor. Using raw ge3 recurring minutes as "ad minutes" would badly overstate ads on Kan Bet.

---

## Method quality notes

1. **Repeats ≠ ads.** Roughly **half** of checked strong clusters are station jingles/promos/thank-yous, not commercials.
2. **Very high-n short clips** (thank-you, "אתם מאזינים", news bumpers) are the main false friends.
3. **PSAs** (road safety, welfare hotline, breast cancer, fraud) fingerprint like ads — fine for "non-show" labeling, but not commercial revenue ads.
4. **Presidential consultation message** repeated across all 3 stations.
5. **Empty/noisy whisper** on some music beds — still usually jingles when n is high and duration short.
6. Overnight tool `recurring_spot_minutes` counts all ge3 repeats; after spot-check, only a **subset** looks like commercial ads.

---

## 103FM podcast comparison (`label_ads_103fm.py`)

**Status:** attempted 2026-11-05 ~09:03 IST with:
```
~/talk_show_analyzer/.venv/bin/python label_ads_103fm.py label \
  --rec-dir ~/tsa_data/recordings/2026-11-04/103fm \
  --date 2026-11-04 \
  --out ~/tsa_data/labels_103fm/2026-11-04
```
Was still running (building 4 kHz envelopes of the long day files) when this report was drafted. **Update section below when finished.**

### Podcast check result — SUCCESS

Finished 09:11 IST (~8.3 min runtime). Output: `~/tsa_data/labels_103fm/2026-11-04/{summary.json,spans.csv}`.

Programs with full-show podcasts found and aligned:

| programId | Show | Podcast min | Matched min |
|-----------|------|-------------|-------------|
| 9 | איריס קול | 48.7 | 45.8 |
| 12 | חמש בערב | 52.4 | 52.3 |
| 74 | ספורט | 93.3 | 93.1 |

Day totals from aligner:

| Label | Minutes |
|-------|---------|
| content (in show, matches podcast) | 191.2 |
| **ad_candidate** (in show, missing from podcast) | **32.4** |
| unaligned (outside those shows / no podcast) | 676.7 |

**Caveat:** Only ~3 shows have ad-free full podcasts, so most of the 15h day is `unaligned`. The 32.4 ad_candidate minutes are **only inside those show windows** (ads+news+promos+jingles cut from the podcast).

Rough overlap with ge3 repeat occurrences (no gold labels; exploratory only):

- ge3 repeat seconds that fall inside podcast `ad_candidate` windows: **27.8 / 136.8 min (20%)** — low because most repeats are outside the 3 shows.
- Among spot-checked 103FM clusters, commercial ones do hit the show windows: **c1 Dekel ~24.8 min** of its occurrence time overlaps ad_candidate; c9 Shufersal ~2.3 min; c5 tourism ~0.5 min. Station thank-you/jingle clusters checked had **0** overlap with those windows.

No formal precision/recall vs gold (no gold file for 2026-11-04). `eval_podlabels.py` / `eval_repeats.py` need a gold CSV.

---

## Artifacts on laptop

- Clips: `~/tsa_data/repeats/spotcheck_2026-11-04/{103fm,glz,kan_bet}/c*.mp3`
- Transcripts: same `c*.txt`
- `plan.json`, `transcripts.json`, `classifications.json`
- Box copy of report: `/workspace/laptop/spotcheck_2026-11-04_report.md`

## Suggested Hebrew one-liner for Shimon

הקטעים שחוזרים הרבה הם לא רק פרסומות: ב־103FM הפרסומת הכי חזקה היא דקל כמילה (74 פעמים), בגלי צה״ל הרבה מהחזרות הן "אתם מאזינים" ו"תודה רבה", ובכאן ב׳ הקלאסטר הכי חזק (120 פעמים) הוא באמפר של מהדורת חדשות עם ספונסר — לא פרסומת רגילה.
