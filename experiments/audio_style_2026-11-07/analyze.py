"""Stage 2: unsupervised clustering on the 2026-11-07 pilot windows.

Cross-fit scores use the single gold 103FM hour only. They are not cross-station
accuracy. PANNs clusters here mainly separate music from speech. See README.md.
Needs feats_*.npy, which are not in git.
"""
import numpy as np, pandas as pd, json, hashlib
from sklearn.preprocessing import StandardScaler; from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, HDBSCAN; from sklearn.metrics import normalized_mutual_info_score as nmi, silhouette_score
SEED=0; df=pd.read_csv("windows.csv"); res=[]; A=df[["win_id","station","day","start","gold","gold_item"]].copy()
G=df.day=="2026-11-02"; isad=(df.gold=="ad").values; brk=df.gold.isin(["ad","promo","jingle","station_id"]).values
# groups: ad identity for labeled items; show windows in 120s contiguous blocks
grp=np.where(df.gold_item.fillna("show")!="show",df.gold_item.fillna("").str.replace(r"\s*\(.*\)","",regex=True),"show_blk"+(df.start//120).astype(int).astype(str))
fold=np.array([int(hashlib.md5((g+str(SEED)).encode()).hexdigest(),16)%2 for g in grp]); A["eval_group"]=grp; A["fold"]=fold
music=(df.p_music>0.5).values
def prep(X,stationwise=False,nc=20):
    X=np.nan_to_num(X.astype(np.float64))
    if stationwise:
        X=X.copy()
        for s in df.station.unique(): m=(df.station==s).values; X[m]=StandardScaler().fit_transform(X[m])
    else: X=StandardScaler().fit_transform(X)
    return PCA(nc,random_state=SEED).fit_transform(X)
def crossfit(lab,target):
    tp=fp=fn=0
    for c in (0,1):
        cal=G.values&(fold==c); ev=G.values&(fold!=c); adc=set()
        for k in np.unique(lab[cal]):
            m=cal&(lab==k)
            if m.sum()>=3 and target[m].mean()>0.5: adc.add(k)
        pred=np.isin(lab,list(adc))
        tp+=(pred&target&ev).sum(); fp+=(pred&~target&ev).sum(); fn+=(~pred&target&ev).sum()
    return tp/(tp+fp) if tp+fp else np.nan, tp/(tp+fn) if tp+fn else np.nan
def row(name,lab,Z):
    ok=lab>=0
    p,r=crossfit(lab,isad); pb,rb=crossfit(lab,brk)
    best=max(((lab[G.values]==k).sum(),k) for k in np.unique(lab[G.values])) if True else None
    # most-ad cluster on gold
    fr=pd.Series(isad[G.values]).groupby(lab[G.values]).agg(["mean","size"])
    return dict(run=name,n_clusters=len(set(lab[ok])),noise_frac=round(1-ok.mean(),3),
      silhouette=round(silhouette_score(Z[ok],lab[ok]),3) if len(set(lab[ok]))>1 else np.nan,
      NMI_station=round(nmi(df.station[ok],lab[ok]),3),NMI_music=round(nmi(music[ok],lab[ok]),3),
      NMI_gold_ad=round(nmi(isad[G.values&ok],lab[G.values&ok]),3),
      max_ad_frac_cluster=round(fr[fr["size"]>=3]["mean"].max(),2),
      cf_ad_prec=round(p,2),cf_ad_rec=round(r,2),cf_break_prec=round(pb,2),cf_break_rec=round(rb,2))
for rep in ["hand","panns"]:
  for v in ["raw","vn"]:
    X=np.load(f"feats_{rep}_{v}.npy")
    for sw in [False,True]:
      Z=prep(X,sw,20 if rep=="hand" else 32); tag=f"{rep}_{v}_{'stz' if sw else 'gz'}"
      for k in [2,3,4,6,8,10]:
        lab=KMeans(k,n_init=10,random_state=SEED).fit_predict(Z); res.append(row(f"{tag}_km{k}",lab,Z)); A[f"{tag}_km{k}"]=lab
      lab=HDBSCAN(min_cluster_size=15,min_samples=5).fit_predict(Z); res.append(row(f"{tag}_hdb",lab,Z)); A[f"{tag}_hdb"]=lab
# baseline: music-prob threshold only (confound check)
for nm,lab in [("baseline_pmusic>0.5",music.astype(int)),("baseline_station_only",pd.factorize(df.station)[0])]:
    res.append(row(nm,lab,np.c_[df.p_music.values,df.p_speech.values]))
R=pd.DataFrame(res); R.to_csv("results_summary.csv",index=False); A.to_csv("assignments.csv",index=False)
pd.set_option("display.width",250); print(R.to_string(index=False))
print("gold windows:",G.sum(),df[G].gold.value_counts().to_dict(),"groups ad:",len(set(grp[isad])),"fold sizes ad:",np.bincount(fold[isad]))
print("windows per station/day:",df.groupby(["day","station"]).size().to_dict())
json.dump(dict(seed=SEED,pca_hand=20,pca_panns=32,kmeans_k=[2,3,4,6,8,10],hdbscan=dict(min_cluster_size=15,min_samples=5),
 cluster_meaning="cluster tagged ad if >50% ad among >=3 calibration-fold gold windows; evaluated on other fold; folds by ad identity / 120s show blocks (md5 hash)"),open("analysis_config.json","w"),indent=1)
