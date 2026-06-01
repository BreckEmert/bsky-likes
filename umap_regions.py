# -*- coding: utf-8 -*-
"""
umap_regions.py  —  hierarchical TF-IDF regions for the map's zoom-tier labels

Decision (after cluster_experiments.py): cluster in the HIGH-D, TF-IDF-weighted
like-space (not the 2D projection, not binary weights), then carve nested tiers
so the map can reveal coarse regions when zoomed out and finer ones when zoomed
in -- while keeping the existing nebula layout (umap_coords.parquet) unchanged.

Pipeline:
  build user x liked-post matrix  ->  TF-IDF  ->  TruncatedSVD(50)
  KMeans(K_FINE) = finest tier (leaves)
  ward linkage on the leaf centroids, cut at the tier sizes  -> NESTED tiers
  (a leaf belongs to exactly one tier-2 and one tier-1 group; tiers are cuts of
   the same tree, so they nest cleanly).

Outputs (for the bio-naming step + web):
  cluster_members.parquet   liker_did, handle, t1, t2, t3   (per user)
  regions_raw.json          [{tier, id, x, y, size}]        (centroids on the
                            EXISTING 2D coords + member counts; names added later)

Run:  python umap_regions.py
"""
import json
import time
import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
from scipy.cluster.hierarchy import linkage, fcluster
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.cluster import KMeans

from bsky_likes import config

MIN_USER_LIKES = 50
MIN_POST_LIKERS = 4
SVD_DIM = 50
K_FINE = 60            # finest tier (leaves)
TIERS = [8, 24, 60]    # tier-1 (coarse) .. tier-3 (= leaves); cuts of one tree
SEED = 0
COORDS = config.PROJECT_DIR / "umap_coords.parquet"
MEMBERS_OUT = config.PROJECT_DIR / "cluster_members.parquet"
REGIONS_RAW = config.PROJECT_DIR.parent / "umap_regions_raw.json"

t0 = time.time()
def el(): return f"{time.time()-t0:.1f}s"

print("[1] eligible users + matrix...", flush=True)
per_liker = pl.read_parquet(config.PER_LIKER_PATH)
eu = per_liker.filter(
    (pl.col("n_likes") > MIN_USER_LIKES) & pl.col("handle").is_not_null()
).select(["liker_did", "handle"])
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(
    ["liker_did", "post_uri"])
post_counts = (likes.group_by("post_uri").agg(pl.len().alias("c"))
               .filter(pl.col("c") >= MIN_POST_LIKERS).collect(engine="streaming"))
edges = (likes
    .join(eu.lazy().select("liker_did"), on="liker_did", how="inner")
    .join(post_counts.lazy().select("post_uri"), on="post_uri", how="inner")
    .collect(engine="streaming"))
user_ids = eu["liker_did"].to_list()
user_handle = dict(zip(user_ids, eu["handle"].to_list()))
user_row = {d: i for i, d in enumerate(user_ids)}
post_col = {p: j for j, p in enumerate(post_counts["post_uri"].to_list())}
rows = np.fromiter((user_row[d] for d in edges["liker_did"].to_list()), dtype=np.int32, count=len(edges))
cols = np.fromiter((post_col[p] for p in edges["post_uri"].to_list()), dtype=np.int32, count=len(edges))
X = csr_matrix((np.ones(len(edges), np.float32), (rows, cols)), shape=(len(user_ids), len(post_col)))
keep = np.asarray((X != 0).sum(axis=1)).ravel() >= 3
X = X[keep]
kept_dids = [d for d, k in zip(user_ids, keep) if k]
print(f"    matrix {X.shape[0]:,} x {X.shape[1]:,} ({el()})", flush=True)

print("[2] align to existing 2D coords...", flush=True)
coords = pl.read_parquet(COORDS)
cmap = {d: (x, y) for d, x, y in zip(coords["liker_did"].to_list(),
                                     coords["x"].to_list(), coords["y"].to_list())}
have = np.array([d in cmap for d in kept_dids])
X = X[have]
dids = [d for d, h in zip(kept_dids, have) if h]
xy = np.array([cmap[d] for d in dids], dtype=np.float64)
print(f"    {X.shape[0]:,} users ({el()})", flush=True)

print("[3] TF-IDF + SVD...", flush=True)
Z = normalize(TruncatedSVD(SVD_DIM, random_state=SEED).fit_transform(
    TfidfTransformer().fit_transform(X)))
print(f"    Z {Z.shape} ({el()})", flush=True)

print(f"[4] KMeans({K_FINE}) leaves + ward nesting...", flush=True)
leaf = KMeans(n_clusters=K_FINE, n_init=4, random_state=SEED).fit_predict(Z)
cent = np.array([Z[leaf == c].mean(0) for c in range(K_FINE)])
link = linkage(cent, method="ward")
# cuts of the same tree => nested; map leaf -> tier group id (1-based -> 0-based)
tier_of_leaf = {}
for ti, k in enumerate(TIERS):
    if k >= K_FINE:
        tier_of_leaf[ti] = np.arange(K_FINE)            # tier == leaves
    else:
        tier_of_leaf[ti] = fcluster(link, k, "maxclust") - 1
# per-user tier labels
t_cols = {}
for ti in range(len(TIERS)):
    t_cols[ti] = tier_of_leaf[ti][leaf]
print(f"    tiers: {[len(set(t_cols[ti].tolist())) for ti in range(len(TIERS))]} "
      f"clusters ({el()})", flush=True)

print("[5] writing members + regions_raw...", flush=True)
pl.DataFrame({
    "liker_did": dids,
    "handle": [user_handle[d] for d in dids],
    "t1": t_cols[0], "t2": t_cols[1], "t3": t_cols[2],
}).write_parquet(MEMBERS_OUT, compression="zstd")

regions = []
for ti in range(len(TIERS)):
    lab = t_cols[ti]
    for c in sorted(set(lab.tolist())):
        m = lab == c
        regions.append({
            "tier": ti + 1, "id": int(c),
            "x": float(xy[m, 0].mean()), "y": float(xy[m, 1].mean()),
            "size": int(m.sum()),
        })
REGIONS_RAW.write_text(json.dumps(regions), encoding="utf-8")
print(f"[OK] {MEMBERS_OUT.name} + {REGIONS_RAW.name}  "
      f"({len(regions)} regions over {len(TIERS)} tiers, {el()} total)", flush=True)
