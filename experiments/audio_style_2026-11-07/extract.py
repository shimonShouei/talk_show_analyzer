"""Stage 1: cut 10s non-overlapping windows, extract handcrafted + PANNs Cnn14 embeddings.

Raw/vol-normalized variants. Writes windows.csv + feats_*.npy. Seedless (deterministic).

The 2026-11-07 pilot already wrote windows.csv. Re-running downloads PANNs Cnn14
when checkpoint_path is None. Audio paths are required environment variables.
The historical box paths under /workspace/tsa_data are not a silent default.
See README.md.
"""
import glob, json, os, sys
OUT=os.path.dirname(os.path.abspath(__file__)); W=10.0; SR=32000
CFG=dict(window_sec=W,hop_sec=W,sr=SR,target_rms_dbfs=-20,
  handcrafted="librosa: rms stats, 20 mfcc mean/std, centroid/bandwidth/rolloff/flatness/zcr/flux mean/std, onset rate, low-energy frac, harmonic ratio, chroma std; computed at 16k",
  embedding="PANNs Cnn14 (AudioSet) 2048-d clip embedding, 32k mono")

def _need(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(
            f"{name} is required. The 2026-11-07 pilot used files under /workspace/tsa_data. "
            "Those paths are not the default. See README.md in this directory."
        )
    return value

hour_mp3 = _need("TSA_HOUR1_MP3")
rec_root = _need("TSA_RECORDINGS_ROOT")
gold_path = _need("TSA_GOLD_CSV")
hour_day = os.environ.get("TSA_HOUR1_DAY", "2026-11-02").strip() or "2026-11-02"
hour_station = os.environ.get("TSA_HOUR1_STATION", "103fm").strip() or "103fm"
style_days = [d.strip() for d in os.environ.get("TSA_STYLE_DAYS", "2026-11-04").split(",") if d.strip()]
style_stations = [s.strip() for s in os.environ.get("TSA_STYLE_STATIONS", "103fm,glz,kan_bet").split(",") if s.strip()]
src = [(hour_day, hour_station, hour_mp3)]
for day in style_days:
    for st in style_stations:
        src += [(day, st, f) for f in sorted(glob.glob(os.path.join(rec_root, day, st, "part*.mp3")))]
# Heavy imports stay below the path check so a missing path does not download PANNs.
import numpy as np, pandas as pd, librosa, torch
gold = pd.read_csv(gold_path)
def gold_label(t0,t1):
    ov={}
    for r in gold.itertuples():
        o=min(t1,r.end)-max(t0,r.start)
        if o>0: ov[(r.label,r.note)]=ov.get((r.label,r.note),0)+o
    if not ov: return "show","show",0.0
    (l,n),o=max(ov.items(),key=lambda x:x[1]); tot=sum(ov.values())
    if tot<5: return "mixed_show","show",tot   # mostly show
    return l,n,o
def hand(y):
    y16=librosa.resample(y,orig_sr=SR,target_sr=16000); sr=16000
    rms=librosa.feature.rms(y=y16)[0]+1e-9; db=20*np.log10(rms)
    mf=librosa.feature.mfcc(y=y16,sr=sr,n_mfcc=20)
    S=np.abs(librosa.stft(y16,n_fft=1024,hop_length=512))
    sp=[librosa.feature.spectral_centroid(S=S,sr=sr)[0],librosa.feature.spectral_bandwidth(S=S,sr=sr)[0],
        librosa.feature.spectral_rolloff(S=S,sr=sr)[0],librosa.feature.spectral_flatness(S=S)[0],
        librosa.feature.zero_crossing_rate(y16)[0],np.r_[0,np.sqrt((np.diff(S,axis=1).clip(0)**2).sum(0))]]
    on=librosa.onset.onset_strength(S=librosa.amplitude_to_db(S),sr=sr)
    nons=len(librosa.onset.onset_detect(onset_envelope=on,sr=sr))/W
    H,P=librosa.decompose.hpss(S); hr=(H**2).sum()/((H**2).sum()+(P**2).sum()+1e-9)
    ch=librosa.feature.chroma_stft(S=S**2,sr=sr)
    f=[db.mean(),db.std(),np.percentile(db,10),np.percentile(db,90),(db<db.mean()-10).mean()]
    f+=list(mf.mean(1))+list(mf.std(1))
    for s in sp: f+=[s.mean(),s.std()]
    f+=[on.mean(),on.std(),nons,hr,ch.std(1).mean(),ch.max(0).mean()]
    return np.array(f,dtype=np.float32)
from panns_inference import AudioTagging
at=AudioTagging(checkpoint_path=None,device="cpu"); torch.set_num_threads(6)
labs=pd.read_csv(os.path.expanduser("~/panns_data/class_labels_indices.csv"))
iM=labs.index[labs.display_name=="Music"][0]; iS=labs.index[labs.display_name=="Speech"][0]
rows=[];FH={"raw":[],"vn":[]};FE={"raw":[],"vn":[]}
for day,st,f in src:
    y,_=librosa.load(f,sr=SR,mono=True); n=int(len(y)//(W*SR))
    for i in range(n):
        w=y[int(i*W*SR):int((i+1)*W*SR)]
        r=np.sqrt((w**2).mean())+1e-9; wv=w*(10**(-20/20)/r)
        t0=i*W; lab,note,ov=gold_label(t0,t0+W) if day==hour_day else ("unlabeled","",0)
        FH["raw"].append(hand(w)); FH["vn"].append(hand(wv))
        rows.append(dict(win_id=len(rows),day=day,station=st,file=f,start=t0,end=t0+W,rms_dbfs=20*np.log10(r),gold=lab,gold_item=note,gold_overlap=ov))
    print(st,f,n,flush=True)
df=pd.DataFrame(rows)
# embeddings in batches
for v in ["raw","vn"]:
    for k in range(0,len(df),32):
        b=[]
        for r in df.iloc[k:k+32].itertuples():
            y,_=librosa.load(r.file,sr=SR,mono=True,offset=r.start,duration=W); y=np.pad(y,(0,int(W*SR)-len(y)))
            if v=="vn": y=y*(10**(-1)/(np.sqrt((y**2).mean())+1e-9))
            b.append(y)
        cw,emb=at.inference(np.stack(b))
        FE[v].append(emb)
        if v=="raw": df.loc[df.index[k:k+32],"p_music"]=cw[:,iM]; df.loc[df.index[k:k+32],"p_speech"]=cw[:,iS]
        print(v,k,flush=True)
for v in FH: np.save(f"{OUT}/feats_hand_{v}.npy",np.stack(FH[v])); np.save(f"{OUT}/feats_panns_{v}.npy",np.concatenate(FE[v]))
df.to_csv(f"{OUT}/windows.csv",index=False); json.dump(CFG,open(f"{OUT}/extract_config.json","w"),indent=1)
