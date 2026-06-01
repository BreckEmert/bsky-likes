# -*- coding: utf-8 -*-
"""
english_subtopics.py  —  tier-2 sub-topics (nested under the 10 tier-1 topics)

Reads the cached TF-IDF embedding + the tier-1 topic assignment
(cluster_members_en.parquet from english_regions.py) and subdivides EACH tier-1
topic into a few sub-clusters (count proportional to size). Nested by
construction, so the tier-1 labels stay valid. Exports centroids/sizes on the
existing 2D layout + 30 sampled bios per sub-cluster for naming.

Run:  python english_subtopics.py
"""
import json
import time
import urllib.parse
import urllib.request
import numpy as np
import polars as pl
from sklearn.cluster import KMeans

from bsky_likes import config

TOTAL_SUBS = 29       # ~ total tier-2 clusters across all tier-1 topics
TOPIC_SAMPLE = 30
SEED = 0
APPVIEW = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"
Z_CACHE = config.PROJECT_DIR / "umap_tfidf_Z.npy"
DID_CACHE = config.PROJECT_DIR / "umap_tfidf_dids.json"
MEMBERS = config.PROJECT_DIR / "cluster_members_en.parquet"
COORDS = config.PROJECT_DIR / "umap_coords.parquet"
SUB_RAW = config.PROJECT_DIR.parent / "umap_subtopics_raw.json"
SUB_BIOS = config.PROJECT_DIR.parent / "cluster_bios_sub.json"

t0 = time.time()
Z = np.load(Z_CACHE)
dids = json.loads(DID_CACHE.read_text())
row_of = {d: i for i, d in enumerate(dids)}

mem = pl.read_parquet(MEMBERS)
coords = pl.read_parquet(COORDS)
cmap = {d: (x, y) for d, x, y in zip(coords["liker_did"].to_list(),
                                     coords["x"].to_list(), coords["y"].to_list())}

# tier-1 topic -> member rows / handles
topics = sorted(mem["topic"].unique().to_list())
sizes = {t: mem.filter(pl.col("topic") == t).height for t in topics}
total = sum(sizes.values())

rng = np.random.default_rng(SEED)
prof_cache = {}

def fetch_bios(hs):
    todo = [h for h in set(hs) if h and h.lower() not in prof_cache]
    for i in range(0, len(todo), 25):
        batch = todo[i:i+25]
        url = APPVIEW + "?" + "&".join("actors=" + urllib.parse.quote(h) for h in batch)
        req = urllib.request.Request(url, headers={"User-Agent": "bsky-likes-analysis/1.0"})
        got = []
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    got = json.load(r).get("profiles", []); break
            except Exception:
                time.sleep(1.0 * (attempt + 1))
        for p in got:
            prof_cache[(p.get("handle") or "").lower()] = (
                (p.get("description") or "") + " " + (p.get("displayName") or "")).strip()
        time.sleep(0.1)

sub_id = 0
regions = []
bios_out = []
for t in topics:
    sub = mem.filter(pl.col("topic") == t)
    sdids = sub["liker_did"].to_list(); shandles = sub["handle"].to_list()
    n_sub = max(2, round(TOTAL_SUBS * sizes[t] / total))
    rows = np.array([row_of[d] for d in sdids])
    lab = KMeans(n_clusters=n_sub, n_init=4, random_state=SEED).fit_predict(Z[rows])
    for c in range(n_sub):
        m = lab == c
        cdids = [sdids[i] for i in np.where(m)[0]]
        chandles = [shandles[i] for i in np.where(m)[0]]
        pts = np.array([cmap[d] for d in cdids if d in cmap])
        pick = [chandles[i] for i in rng.choice(len(chandles),
                size=min(TOPIC_SAMPLE, len(chandles)), replace=False) if chandles[i]]
        regions.append({"tier": 2, "id": sub_id, "parent": int(t),
                        "x": float(pts[:, 0].mean()), "y": float(pts[:, 1].mean()),
                        "size": int(m.sum()), "sample": pick})
        bios_out.append({"id": sub_id, "parent": int(t), "size": int(m.sum()),
                         "handles": pick})
        sub_id += 1

print(f"[i] {sub_id} sub-topics; fetching bios...", flush=True)
fetch_bios([h for b in bios_out for h in b["handles"]])
for b in bios_out:
    b["bios"] = [{"handle": h, "desc": prof_cache.get(h.lower(), "")} for h in b["handles"]
                 if prof_cache.get(h.lower(), "").strip()]
    del b["handles"]
for r in regions:
    del r["sample"]

SUB_RAW.write_text(json.dumps(regions), encoding="utf-8")
SUB_BIOS.write_text(json.dumps(bios_out, ensure_ascii=False), encoding="utf-8")
print(f"[OK] {SUB_RAW.name} + {SUB_BIOS.name} ({sub_id} subs, {time.time()-t0:.1f}s)", flush=True)
