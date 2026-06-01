# -*- coding: utf-8 -*-
"""
cluster_experiments.py  —  objective comparison of grouping strategies

Question: is "HDBSCAN on the 2D UMAP coords" the best way to find regions, or
do we get cleaner / more granular communities by clustering in the HIGH-D
like-vector space and/or down-weighting ubiquitous posts (TF-IDF)?

Builds the same user x liked-post matrix as umap_explore.py, then clusters a
subsample under 4 schemes and renders them on the EXISTING 2D layout so they're
directly comparable. Prints objective metrics. Re-embedding is NOT redone; only
the grouping changes, which is the variable under test.

Run:  python cluster_experiments.py
"""
import time
import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.cluster import HDBSCAN, KMeans
import matplotlib.pyplot as plt

from bsky_likes import config

MIN_USER_LIKES = 50
MIN_POST_LIKERS = 4
SVD_DIM = 50
SUBSAMPLE = 60000          # cluster on a representative subsample for speed
SEED = 0
OUT_PNG = config.PLOTS_DIR / "cluster_experiments.png"
COORDS = config.PROJECT_DIR / "umap_coords.parquet"

t0 = time.time()
def el(): return f"{time.time()-t0:.1f}s"

print("[1] eligible users + matrix (same recipe as umap_explore)...", flush=True)
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
print(f"    {len(edges):,} edges ({el()})", flush=True)

user_ids = eu["liker_did"].to_list()
user_row = {d: i for i, d in enumerate(user_ids)}
post_ids = post_counts["post_uri"].to_list()
post_col = {p: j for j, p in enumerate(post_ids)}
rows = np.fromiter((user_row[d] for d in edges["liker_did"].to_list()), dtype=np.int32, count=len(edges))
cols = np.fromiter((post_col[p] for p in edges["post_uri"].to_list()), dtype=np.int32, count=len(edges))
X = csr_matrix((np.ones(len(edges), np.float32), (rows, cols)), shape=(len(user_ids), len(post_ids)))
nnz = np.asarray((X != 0).sum(axis=1)).ravel()
keep = nnz >= 3
X = X[keep]
kept_dids = [d for d, k in zip(user_ids, keep) if k]
print(f"    matrix {X.shape[0]:,} x {X.shape[1]:,}, {X.nnz:,} nnz ({el()})", flush=True)

print("[2] align existing 2D coords...", flush=True)
coords = pl.read_parquet(COORDS)
cmap = {d: (x, y) for d, x, y in zip(coords["liker_did"].to_list(),
                                     coords["x"].to_list(), coords["y"].to_list())}
have = np.array([d in cmap for d in kept_dids])
X = X[have]
dids = [d for d, h in zip(kept_dids, have) if h]
xy = np.array([cmap[d] for d in dids], dtype=np.float64)
print(f"    {X.shape[0]:,} users aligned to coords ({el()})", flush=True)

rng = np.random.default_rng(SEED)
idx = rng.choice(X.shape[0], size=min(SUBSAMPLE, X.shape[0]), replace=False)
Xs = X[idx]; xys = xy[idx]
# subsample-scaled min cluster size (~ keep proportional to the 400/243k baseline)
frac = Xs.shape[0] / X.shape[0]

print("[3] embeddings for clustering...", flush=True)
svd = TruncatedSVD(SVD_DIM, random_state=SEED)
Zbin = normalize(svd.fit_transform(Xs))                       # high-D binary
svd2 = TruncatedSVD(SVD_DIM, random_state=SEED)
Ztfidf = normalize(svd2.fit_transform(TfidfTransformer().fit_transform(Xs)))  # high-D TF-IDF
print(f"    SVD x2 done ({el()})", flush=True)

print("[4] clustering 4 schemes...", flush=True)
schemes = {}
schemes["A: 2D + HDBSCAN\n(current approach)"] = HDBSCAN(
    min_cluster_size=max(40, int(400 * frac)), min_samples=10, n_jobs=-1).fit_predict(xys)
print(f"    A done ({el()})", flush=True)
schemes["B: highD binary + HDBSCAN"] = HDBSCAN(
    min_cluster_size=50, min_samples=5, n_jobs=-1).fit_predict(Zbin)
print(f"    B done ({el()})", flush=True)
schemes["C: highD TF-IDF + HDBSCAN"] = HDBSCAN(
    min_cluster_size=50, min_samples=5, n_jobs=-1).fit_predict(Ztfidf)
print(f"    C done ({el()})", flush=True)
schemes["D: highD TF-IDF + KMeans-40"] = KMeans(
    n_clusters=40, n_init=4, random_state=SEED).fit_predict(Ztfidf)
print(f"    D done ({el()})", flush=True)

def metrics(lab):
    lab = np.asarray(lab)
    pos = lab[lab >= 0]
    nclust = len(set(pos.tolist()))
    clustered = len(pos) / len(lab)
    sizes = np.bincount(pos) if len(pos) else np.array([0])
    sizes = sizes[sizes > 0]
    biggest = sizes.max() / len(lab) if len(sizes) else 0
    med = int(np.median(sizes)) if len(sizes) else 0
    return nclust, clustered, biggest, med

print("\n=== OBJECTIVE METRICS (subsample n=%d) ===" % Xs.shape[0])
print(f"{'scheme':36} {'#clusters':>9} {'%clustered':>11} {'biggest%':>9} {'medsize':>8}")
for name, lab in schemes.items():
    nclust, clustered, biggest, med = metrics(lab)
    print(f"{name.splitlines()[0]:36} {nclust:>9} {clustered*100:>10.1f}% {biggest*100:>8.1f}% {med:>8}")

print("\n[5] rendering comparison PNG...", flush=True)
plt.rcParams.update({"figure.facecolor": "#0e1116", "axes.facecolor": "#0e1116"})
fig, axes = plt.subplots(2, 2, figsize=(20, 20))
for ax, (name, lab) in zip(axes.ravel(), schemes.items()):
    lab = np.asarray(lab)
    noise = lab < 0
    # color non-noise by cluster via tab20 cycling; noise = dim gray
    col = np.full((len(lab), 4), [0.35, 0.35, 0.35, 0.25])
    pal = plt.get_cmap("tab20")(np.arange(20))
    for i, c in enumerate(sorted(set(lab[~noise].tolist()))):
        m = lab == c
        col[m] = pal[i % 20]; col[m, 3] = 0.5
    ax.scatter(xys[:, 0], xys[:, 1], c=col, s=2, linewidths=0)
    nclust, clustered, biggest, med = metrics(lab)
    ax.set_title(f"{name}\n{nclust} clusters · {clustered*100:.0f}% clustered · "
                 f"biggest {biggest*100:.0f}% · med {med}",
                 color="#e6edf3", fontsize=14)
    ax.set_xticks([]); ax.set_yticks([])
fig.tight_layout()
fig.savefig(OUT_PNG, dpi=110, facecolor="#0e1116")
print(f"[OK] {OUT_PNG}  ({el()} total)", flush=True)
