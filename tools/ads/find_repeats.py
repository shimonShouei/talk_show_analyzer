#!/usr/bin/env python3
"""find_repeats.py - find audio segments (ads, promos, jingles, station IDs) that recur
several times across one or more days of a station's recording. Works for any station.

Clusters are not validated commercials. A high occurrence count (the 74x and 120x
groups from the Nov 2026 run) can be over-merging. recurring_spot_minutes is
repeated audio time, including padding, jingles, and bumpers. It is not ad minutes.

Method: landmark audio fingerprints (spectrogram peak pairs, Shazam-style) for every file,
match every hash against all other occurrences, vote on (time, time-offset) pairs, keep runs
of >= MIN_LEN seconds that line up at a constant offset, then cluster the matched intervals.

Deps: Python 3.10+, numpy, scipy   (pip install numpy scipy) ; ffmpeg on PATH.
Files named partNN_HHMMSS.mp3 inside a folder named YYYY-MM-DD (or its parent) get wall-clock times.

Usage:
  python find_repeats.py --out OUT  FILE_OR_DIR [FILE_OR_DIR ...]
      [--min-occ 3] [--min-len 4] [--max-len 120]
  e.g. python find_repeats.py --out ~/tsa_data/repeats/2026-11-04_glz ~/tsa_data/recordings/2026-11-04/glz
Outputs:
  occurrences.csv  file,start_sec,end_sec,duration,cluster_id,n_occurrences,wall_start,kind
  clusters.csv     cluster_id,n_occurrences,median_dur,first_file,first_start,kind,example_wall
  summary.json
kind: spot (median length <= --max-len: ads/promos/jingles/IDs) | long (songs, repeated shows)
Tip: feed several days of the same station: ads recur across days, talk content doesn't.
"""
import argparse, csv, datetime as dt, json, re, subprocess, sys, time
from pathlib import Path
import numpy as np
from scipy.ndimage import maximum_filter

SR, NFFT, HOP = 8000, 512, 256          # 31.25 frames/s
FPS = SR / HOP
FMIN, FMAX = 8, 200                      # bins ~125 Hz .. 3.1 kHz
FANOUT, DTMAX, DFMAX = 5, 40, 40        # peak pairing
NBR_T, NBR_F = 13, 13                    # peak neighbourhood (~0.4 s x 200 Hz)

def log(*a): print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)

def peaks_for_file(path, cache=None):
    path = Path(path)
    if cache:
        c = Path(cache) / f"{path.parent.name}_{path.stem}_{path.stat().st_size}_pk.npy"
        if c.exists(): return np.load(c)
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], stdout=subprocess.PIPE)
    win = np.hanning(NFFT).astype(np.float32)
    chunk_frames, pad = 4000, NBR_T            # ~2 min per chunk
    need = (chunk_frames + 2 * pad) * HOP + NFFT
    buf = np.zeros(0, np.float32); f0 = 0; out = []; eof = False
    while not eof or len(buf) >= NFFT:
        while not eof and len(buf) < need:
            b = p.stdout.read(need * 2)
            if not b: eof = True; break
            buf = np.concatenate([buf, np.frombuffer(b, np.int16).astype(np.float32)])
        n = (len(buf) - NFFT) // HOP + 1
        if n <= 0: break
        idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
        S = np.log1p(np.abs(np.fft.rfft(buf[idx] * win, axis=1))[:, FMIN:FMAX])
        mx = maximum_filter(S, size=(NBR_T, NBR_F), mode="constant")
        thr = np.median(S, axis=1, keepdims=True) + 1.0
        t, f = np.nonzero((S == mx) & (S > thr) & (S > 0.5))
        lo = 0 if f0 == 0 else pad
        hi = n if eof else n - pad
        keep = (t >= lo) & (t < hi)
        out.append(np.stack([t[keep] + f0, f[keep]], 1).astype(np.int32))
        if eof: break
        adv = hi - pad if hi - pad > 0 else hi
        buf = buf[adv * HOP:]; f0 += adv
    p.wait()
    pk = np.concatenate(out) if out else np.zeros((0, 2), np.int32)
    pk = pk[np.lexsort((pk[:, 1], pk[:, 0]))]
    pk = np.unique(pk, axis=0)
    if cache:
        Path(cache).mkdir(parents=True, exist_ok=True); np.save(c, pk)
    return pk

def hashes(pk):
    """(hash, anchor_time) for peak pairs."""
    t, f = pk[:, 0].astype(np.int64), pk[:, 1].astype(np.int64)
    H, T = [], []
    n = len(t)
    for k in range(1, 4 * FANOUT):              # look ahead in time-sorted peaks
        if k >= n: break
        dtt = t[k:] - t[:-k]; dff = f[k:] - f[:-k]
        ok = (dtt > 0) & (dtt <= DTMAX) & (np.abs(dff) <= DFMAX)
        H.append((f[:-k][ok] << 14) | ((dff[ok] + DFMAX) << 6) | dtt[ok]); T.append(t[:-k][ok])
    H = np.concatenate(H); T = np.concatenate(T)
    return H, T

def find_pairs(H, T, min_delta, max_bucket=300):
    o = np.lexsort((T, H)); H, T = H[o], T[o]
    # drop very common hashes (silence / tones)
    u, inv, cnt = np.unique(H, return_inverse=True, return_counts=True)
    good = cnt[inv] <= max_bucket
    H, T = H[good], T[good]
    A, D = [], []
    for k in range(1, max_bucket):
        if k >= len(H): break
        eq = H[k:] == H[:-k]
        if not eq.any(): break
        d = T[k:][eq] - T[:-k][eq]
        ok = d >= min_delta
        A.append(T[:-k][eq][ok]); D.append(d[ok])
    return np.concatenate(A), np.concatenate(D)

def detect_runs(A, D, min_len_s, votes_per_s=4, dq=3):
    """runs of seconds where many hash pairs agree on the same offset."""
    sec = (A / FPS).astype(np.int64); dqv = D // dq
    key = dqv * 10_000_000 + sec
    k, c = np.unique(key, return_counts=True)
    # let neighbouring offset bins vote together
    dd, ss = k // 10_000_000, k % 10_000_000
    sel = c >= votes_per_s
    dd, ss, c = dd[sel], ss[sel], c[sel]
    runs = []
    o = np.lexsort((ss, dd)); dd, ss = dd[o], ss[o]
    i = 0
    while i < len(dd):
        j = i
        while j + 1 < len(dd) and dd[j + 1] == dd[i] and ss[j + 1] - ss[j] <= 2: j += 1
        if ss[j] - ss[i] + 1 >= min_len_s:
            runs.append((float(ss[i]), float(ss[j] + 1), float(dd[i] * dq / FPS)))
        i = j + 1
    return runs

class DSU:
    def __init__(s, n): s.p = list(range(n))
    def f(s, x):
        while s.p[x] != x: s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def u(s, a, b): s.p[s.f(a)] = s.f(b)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+"); ap.add_argument("--out", required=True)
    ap.add_argument("--min-occ", type=int, default=3); ap.add_argument("--min-len", type=float, default=4)
    ap.add_argument("--max-len", type=float, default=120); ap.add_argument("--min-delta", type=float, default=5)
    a = ap.parse_args(); t0 = time.time()
    files = []
    for x in a.inputs:
        x = Path(x).expanduser()
        files += sorted(x.glob("*.mp3")) if x.is_dir() else [x]
    out = Path(a.out).expanduser(); out.mkdir(parents=True, exist_ok=True)
    # global timeline (frames) with 60 s gaps between files so no run crosses a file boundary
    starts, lens, allpk = [], [], []
    off = 0
    for f in files:
        pk = peaks_for_file(f, out / "cache"); n = int(pk[:, 0].max()) + 1 if len(pk) else 0
        log(f"{f.name}: {n / FPS / 60:.1f} min, {len(pk) / max(n / FPS, 1):.0f} peaks/s")
        allpk.append(pk + np.array([off, 0], np.int32)); starts.append(off); lens.append(n)
        off += n + int(60 * FPS)
    pk = np.concatenate(allpk); total_audio = sum(lens) / FPS
    H, T = hashes(pk); log(f"{len(H)} hashes")
    A, D = find_pairs(H, T, int(a.min_delta * FPS)); log(f"{len(A)} hash pairs")
    runs = detect_runs(A, D, a.min_len)
    log(f"{len(runs)} offset-runs")
    iv = []
    for s, e, d in runs: iv += [(s, e), (s + d, e + d)]
    # cluster: link the two sides of each run, and intervals overlapping >=50% of the shorter
    n = len(iv); dsu = DSU(n)
    for i in range(0, n, 2): dsu.u(i, i + 1)
    order = sorted(range(n), key=lambda i: iv[i][0]); active = []
    for i in order:
        s, e = iv[i]; active = [j for j in active if iv[j][1] > s]
        for j in active:
            ov = min(e, iv[j][1]) - max(s, iv[j][0])
            if ov >= 0.5 * min(e - s, iv[j][1] - iv[j][0]): dsu.u(i, j)
        active.append(i)
    groups = {}
    for i in range(n): groups.setdefault(dsu.f(i), []).append(iv[i])
    def wall(f, s):
        m = re.search(r"_(\d{6})$", f.stem)
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", str(f.parent))
        if not (m and dm): return ""
        w0 = dt.datetime.strptime(dm.group(1) + m.group(1), "%Y-%m-%d%H%M%S")
        return (w0 + dt.timedelta(seconds=s)).strftime("%Y-%m-%d %H:%M:%S")
    occ_rows, cl_rows, cid = [], [], 0
    for g in sorted(groups.values(), key=lambda g: min(x[0] for x in g)):
        g = sorted(g); merged = []
        for s, e in g:
            if merged and s <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)
            else: merged.append([s, e])
        if len(merged) < 2: continue
        cid += 1; durs = [e - s for s, e in merged]; md = float(np.median(durs))
        kind = "spot" if md <= a.max_len else "long"
        first = None
        for s, e in merged:
            fr = s * FPS; fi = int(np.searchsorted(starts, fr, side="right") - 1)
            f = files[fi]; fs = s - starts[fi] / FPS
            row = [f.name, round(fs, 1), round(fs + e - s, 1), round(e - s, 1), cid, len(merged), wall(f, fs), kind]
            occ_rows.append(row); first = first or row
        cl_rows.append([cid, len(merged), round(md, 1), first[0], first[1], kind, first[6]])
    with open(out / "occurrences.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["file", "start_sec", "end_sec", "duration", "cluster_id", "n_occurrences", "wall_start", "kind"])
        w.writerows(occ_rows)
    with open(out / "clusters.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["cluster_id", "n_occurrences", "median_dur", "first_file", "first_start", "kind", "example_wall"])
        w.writerows(cl_rows)
    rec = [r for r in cl_rows if r[1] >= a.min_occ]
    secs = sum(r[3] for r in occ_rows if r[5] >= a.min_occ and r[7] == "spot")
    summ = {"files": [str(f) for f in files], "audio_hours": round(total_audio / 3600, 2),
            "clusters_total": len(cl_rows), f"clusters_ge_{a.min_occ}": len(rec),
            "recurring_spot_minutes": round(secs / 60, 1),
            "recurring_spot_minutes_note": (
                "Repeated spot audio (count of matched seconds), not validated "
                "commercial ad time. Large clusters may be over-merged."
            ),
            "runtime_sec": round(time.time() - t0, 1),
            "params": vars(a)}
    (out / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    log("done", summ)

if __name__ == "__main__": main()
