# -*- coding: utf-8 -*-
"""Investigate: does HDBSCAN on the TF-IDF embedding isolate the non-English
outer islands (incl. the user's 5 seeds) as distinct clusters, leaving the
English core as noise? Prints per-cluster size, seed membership, and bio-lang."""
import json, time, urllib.parse, urllib.request
import numpy as np, polars as pl
from collections import Counter
from sklearn.cluster import HDBSCAN
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0
from bsky_likes import config

Z = np.load(config.PROJECT_DIR / "umap_tfidf_Z.npy")
dids = json.loads((config.PROJECT_DIR / "umap_tfidf_dids.json").read_text())
en = set(json.loads((config.PROJECT_DIR / "english_dids.json").read_text()))
mask = np.array([d in en for d in dids])
Zi = Z[mask]; idx = np.where(mask)[0]
pl_df = pl.read_parquet(config.PER_LIKER_PATH).select(["liker_did", "handle"])
h_of = dict(zip(pl_df["liker_did"].to_list(), pl_df["handle"].to_list()))
seeds = {h.lower() for h in ['wickedwookie.bsky.social','egbertl.bsky.social',
        'crbelottilm.bsky.social','hunosp.bsky.social','lukree.bsky.social']}

print(f"HDBSCAN on {Zi.shape[0]:,} English-set users...", flush=True)
t=time.time()
lab = HDBSCAN(min_cluster_size=80, min_samples=5, n_jobs=-1).fit_predict(Zi)
nC = len(set(lab[lab>=0])); noise=(lab<0).sum()
print(f"  {nC} clusters, noise={noise:,} ({noise/len(lab)*100:.0f}%), {time.time()-t:.0f}s\n", flush=True)

APP='https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles'
cache={}
def fetch(hs):
    todo=[h for h in set(hs) if h and h.lower() not in cache]
    for i in range(0,len(todo),25):
        b=todo[i:i+25]; url=APP+'?'+'&'.join('actors='+urllib.parse.quote(h) for h in b)
        try:
            r=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'x'}),timeout=30)
            for p in json.load(r).get('profiles',[]):
                cache[(p.get('handle') or '').lower()]=((p.get('description') or '')+' '+(p.get('displayName') or '')).strip()
        except Exception: pass
        time.sleep(0.1)

# sample handles per cluster
rng=np.random.default_rng(0)
samp={}
for c in range(nC):
    members=idx[lab==c]
    pick=rng.choice(members,size=min(18,len(members)),replace=False)
    samp[c]=[h_of.get(dids[j],'') for j in pick]
fetch([h for hs in samp.values() for h in hs])

def langs_of(hs):
    L=[]
    for h in hs:
        t=cache.get(h.lower(),'')
        if len(t)>=8:
            try:L.append(detect(t))
            except:pass
    return L

# which cluster has each seed
seed_cluster={}
for c in range(nC):
    for j in idx[lab==c]:
        if (h_of.get(dids[j]) or '').lower() in seeds:
            seed_cluster[(h_of.get(dids[j]) or '').lower()]=c

rows=[]
for c in range(nC):
    L=langs_of(samp[c]); cnt=Counter(L)
    enf = cnt.get('en',0)/len(L) if L else 1.0
    sd=[s for s,cc in seed_cluster.items() if cc==c]
    rows.append((c,int((lab==c).sum()),round(enf,2),cnt.most_common(3),sd))
rows.sort(key=lambda r:r[2])  # least-English first
print("cluster size en_frac top_langs seeds")
for r in rows:
    print(f"  c{r[0]:>3} n={r[1]:>5} en={r[2]:.2f} {r[3]} {r[4] if r[4] else ''}")
print("\nseed -> cluster:", seed_cluster)
EOF_GUARD = None
