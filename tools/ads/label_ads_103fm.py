#!/usr/bin/env python3
"""label_ads_103fm.py - (secondary check) label a day of 103FM live recording by aligning the
station's ad-free "full show" podcasts (התוכנית המלאה) against it. Live audio missing from the
podcast inside a show's time window = ad_candidate (ads + news + promos + jingles).

Deps: numpy, scipy, requests ; ffmpeg on PATH.   Live files: partNN_HHMMSS.mp3
Usage:
  python label_ads_103fm.py label --rec-dir DIR --date 2026-11-04 [--out OUT] [--programs 12,18]
  python label_ads_103fm.py discover [--max-id 150]      # list RSS programIds with full shows
Out: spans.csv (file,start_sec,end_sec,duration,label,program,wall_start), summary.json
"""
import argparse, csv, datetime as dt, email.utils, json, os, re, subprocess, sys, time
from pathlib import Path
import numpy as np, requests
from scipy.signal import fftconvolve
from scipy.fft import rfft, irfft, next_fast_len

RSS = "https://103fm.maariv.co.il/rss/mediarss.aspx?programId={}"
UA = {"User-Agent": "Mozilla/5.0"}
SR, HOP = 4000, 40; FPS = SR // HOP; BLOCK, STEP, THR = 10 * FPS, 5 * FPS, 0.80
HEB = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
PROGRAMS = {5:"שיחות לילה",8:"איציק הליצן",9:"איריס קול",10:'סג"ל עצבני',11:"גבי גזית",12:"חמש בערב",
 13:"דידי לוקאלי",14:"ורדה רזיאל ז'קונט",18:"רון קופמן ואריה אלדד",19:"זהבי עצבני",21:"פנינה בת צבי",
 22:"פרופ' רפי קרסו",23:"רבקה מיכאלי",24:"מועדון ארוחת הבוקר",25:"בראייה אחרת",29:"אדוני ראש העיר",
 35:"עדנה לב",59:"מיכל דליות",74:"ספורט",78:"יורם שפטל"}
def log(*a): print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)

def envelope(path, cache):
    path = Path(path); c = Path(cache) / f"{path.parent.name}_{path.stem}_{path.stat().st_size}_env.npy"
    if c.exists(): return np.load(c)
    p = subprocess.Popen(["ffmpeg","-nostdin","-v","error","-i",str(path),"-ac","1","-ar",str(SR),"-f","s16le","-"], stdout=subprocess.PIPE)
    out, buf = [], b""
    while True:
        b = p.stdout.read(HOP * 2 * 6000)
        if not b: break
        buf += b; n = len(buf) // (HOP * 2) * (HOP * 2)
        out.append(np.abs(np.frombuffer(buf[:n], np.int16).astype(np.float32)).reshape(-1, HOP).mean(1)); buf = buf[n:]
    p.wait(); e = np.concatenate(out) if out else np.zeros(0, np.float32)
    c.parent.mkdir(parents=True, exist_ok=True); np.save(c, e); return e

class Live:
    def __init__(s, files, cache):
        envs = [envelope(f, cache) for f in files]; s.lens = [len(e) for e in envs]
        s.starts = np.cumsum([0] + s.lens[:-1]); s.L = np.concatenate(envs).astype(np.float64)
        c1 = np.concatenate([[0], np.cumsum(s.L)]); c2 = np.concatenate([[0], np.cumsum(s.L ** 2)])
        m = (c1[BLOCK:] - c1[:-BLOCK]) / BLOCK
        s.sd = np.sqrt(np.maximum((c2[BLOCK:] - c2[:-BLOCK]) / BLOCK - m * m, 1e-6)); s.F = None
    @staticmethod
    def nz(w):
        w = w - w.mean(); sd = w.std(); return None if sd < 1e-6 else w / sd
    def glob(s, w):
        w = s.nz(w)
        if w is None: return -1, 0.0
        if s.F is None: s.n = next_fast_len(len(s.L) + BLOCK); s.F = rfft(s.L, s.n)
        c = irfft(s.F * np.conj(rfft(w, s.n)), s.n)[:len(s.sd)] / (BLOCK * s.sd); k = int(np.argmax(c)); return k, float(c[k])
    def local(s, w, lo, hi):
        lo, hi = max(0, lo), min(len(s.sd), hi); w = s.nz(w)
        if w is None or hi <= lo: return -1, 0.0
        c = fftconvolve(s.L[lo:hi + BLOCK - 1], w[::-1], "valid") / (BLOCK * s.sd[lo:hi]); k = int(np.argmax(c)); return lo + k, float(c[k])

def align(P, live):
    hits, pred = [], None
    for ps in range(0, len(P) - BLOCK, STEP):
        w = P[ps:ps + BLOCK]; k, c = -1, 0.0
        if pred is not None: k, c = live.local(w, pred - 3 * FPS, pred + 20 * 60 * FPS)
        if c < THR: k, c = live.glob(w)
        if c >= THR: hits.append((ps, k - ps)); pred = k + STEP
        elif pred is not None: pred += STEP
    runs, cur = [], []
    for ps, d in hits:
        if cur and abs(d - cur[-1][1]) <= 30 and ps - cur[-1][0] <= STEP: cur.append((ps, d))
        else:
            if len(cur) >= 3: runs.append(cur)
            cur = [(ps, d)]
    if len(cur) >= 3: runs.append(cur)
    return [(r[0][0], r[-1][0] + BLOCK, int(np.median([x[1] for x in r]))) for r in runs]

def episodes(pid, date):
    r0 = requests.get(RSS.format(pid), headers=UA, timeout=30); x = r0.content.decode("utf-8-sig", "replace"); res = []
    d2, d3 = date.strftime("%d.%m.%y"), f"{date.day} ב{HEB[date.month-1]} {date.year}"
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        t = re.search(r"<title>(.*?)</title>", it, re.S); u = re.search(r'url="([^"]+\.mp3)"', it); p = re.search(r"<pubDate>(.*?)<", it)
        if not (t and u) or "המלאה" not in t.group(1): continue
        try: pd = email.utils.parsedate_to_datetime(p.group(1)).date()
        except Exception: pd = None
        if pd == date or d2 in t.group(1) or d3 in t.group(1): res.append((t.group(1).strip(), u.group(1)))
    return res

def label(a):
    t0 = time.time(); date = dt.date.fromisoformat(a.date); rec = Path(a.rec_dir)
    out = Path(a.out or rec.parent / "labels_103fm"); out.mkdir(parents=True, exist_ok=True)
    files = sorted(rec.glob("part*_*.mp3")); live = Live(files, out / "cache"); N = len(live.L)
    progs = {int(p): PROGRAMS.get(int(p), p) for p in a.programs.split(",")} if a.programs else PROGRAMS
    lab = np.zeros(N, np.int8); prog = np.full(N, -1, np.int16); names, summ = [], []
    for pid, nm in progs.items():
        try: eps = episodes(pid, date)
        except Exception as e: log("rss", pid, e); continue
        for title, url in eps:
            fn = out / "podcasts" / Path(url).name
            if not fn.exists():
                fn.parent.mkdir(parents=True, exist_ok=True); r = requests.get(url, headers=UA, timeout=120); r.raise_for_status(); fn.write_bytes(r.content)
            P = envelope(fn, out / "cache").astype(np.float64); runs = align(P, live); got = sum(b - x for x, b, _ in runs)
            log(f"{nm}: {title}: {got/FPS/60:.1f}/{len(P)/FPS/60:.1f} min matched, {len(runs)} runs")
            summ.append({"program_id": pid, "program": nm, "title": title, "podcast_min": round(len(P)/FPS/60, 1), "matched_min": round(got/FPS/60, 1)})
            if got < 3 * 60 * FPS: continue   # need >=3 min matched
            names.append(nm); iv = [(x + d, b + d) for x, b, d in runs]; ws, we = max(min(s for s, _ in iv), 0), min(max(e for _, e in iv), N)
            lab[ws:we] = np.maximum(lab[ws:we], 1); prog[ws:we] = len(names) - 1
            for s, e in iv: lab[max(s, 0):min(e, N)] = 2
    # gaps (<15 min) between two aligned shows = top-of-hour news/ad breaks -> ad_candidate
    nz = np.flatnonzero(lab > 0)
    if len(nz):
        idx0 = np.flatnonzero(np.diff(nz) > 1)
        for i in idx0:
            a0, b0 = nz[i] + 1, nz[i + 1]
            if b0 - a0 < 15 * 60 * FPS: lab[a0:b0] = 1; prog[a0:b0] = prog[a0 - 1]
    LN = {0: "unaligned", 1: "ad_candidate", 2: "content"}; key = lab.astype(np.int32) * 1000 + prog
    idx = np.flatnonzero(np.diff(key)) + 1; rows = []
    for s, e in zip(np.r_[0, idx], np.r_[idx, N]):
        while s < e:
            fi = int(np.searchsorted(live.starts, s, side="right") - 1); ee = min(e, live.starts[fi] + live.lens[fi]); f = files[fi]
            fs = (s - live.starts[fi]) / FPS; m = re.search(r"_(\d{6})$", f.stem)
            wall = (dt.datetime.combine(date, dt.datetime.strptime(m.group(1), "%H%M%S").time()) + dt.timedelta(seconds=fs)).strftime("%Y-%m-%d %H:%M:%S") if m else ""
            rows.append([f.name, round(fs, 2), round((ee - live.starts[fi]) / FPS, 2), round((ee - s) / FPS, 2), LN[int(lab[s])], names[prog[s]] if prog[s] >= 0 else "", wall]); s = ee
    with open(out / "spans.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["file","start_sec","end_sec","duration","label","program","wall_start"]); w.writerows(rows)
    res = {"date": a.date, "programs": summ, "minutes": {LN[k]: round(float((lab == k).sum())/FPS/60, 1) for k in LN}, "runtime_sec": round(time.time()-t0, 1)}
    (out / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1)); log("done", res["minutes"], res["runtime_sec"], "s")

def discover(a):
    for pid in range(1, a.max_id + 1):
        try: x = requests.get(RSS.format(pid), headers=UA, timeout=15).content.decode("utf-8-sig", "replace")
        except Exception: continue
        t = re.search(r"<title>(.*?)</title>", x)
        if t and "המלאה" in x: print(pid, t.group(1).strip(), x.count("המלאה"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("discover"); d.add_argument("--max-id", type=int, default=150)
    l = sp.add_parser("label"); l.add_argument("--rec-dir", required=True); l.add_argument("--date", required=True); l.add_argument("--out"); l.add_argument("--programs")
    a = ap.parse_args(); discover(a) if a.cmd == "discover" else label(a)
