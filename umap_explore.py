# -*- coding: utf-8 -*-
"""
umap_explore.py  —  shared-liked-posts embedding (static preview to tune)

Builds a user x liked-post sparse matrix and runs UMAP (the scalable cousin of
t-SNE: neighbors stay neighbors) to lay every active user out in 2D, so people
who like the same posts land near each other -> visual communities. Saves a
static matplotlib PNG to eyeball + tune, and a parquet of coords for later web
export.

DEPENDENCY (one-time): pip install umap-learn
  (pulls numba + pynndescent; scipy is already installed.)

HEADS-UP: this is the heaviest compute in the project. ~250k users x ~1-2M
co-likeable posts. Expect several minutes + a few GB RAM. If it's too heavy,
raise MIN_USER_LIKES (fewer users) or MIN_POST_LIKERS (fewer columns).

Run:  python umap_explore.py
Tune: edit the knobs below, re-run.
"""
import time
import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
import matplotlib.pyplot as plt

from bsky_likes import config

# ---------------------------------------------------------------- knobs ----
MIN_USER_LIKES = 50      # keep users with MORE than this many likes
MIN_POST_LIKERS = 4      # keep posts liked by AT LEAST this many of our users
N_NEIGHBORS = 15         # UMAP: smaller = more local clusters, larger = global
MIN_DIST = 0.1           # UMAP: smaller = tighter clumps
METRIC = "cosine"        # cosine fits "overlap of liked sets" well
SEED = 42
OUT_PNG = config.PLOTS_DIR / "umap_explore.png"
OUT_COORDS = config.PROJECT_DIR / "umap_coords.parquet"
# ---------------------------------------------------------------------------

t0 = time.time()


def el():
    return f"{time.time()-t0:.1f}s"


print("[1] eligible users from per_liker...", flush=True)
per_liker = pl.read_parquet(config.PER_LIKER_PATH)
eu = per_liker.filter(
    (pl.col("n_likes") > MIN_USER_LIKES) & pl.col("handle").is_not_null()
).select(["liker_did", "handle", "mean_log_popularity"])
print(f"    {len(eu):,} eligible users ({el()})", flush=True)

print("[2] eligible posts (>= %d likers, streaming)..." % MIN_POST_LIKERS, flush=True)
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(
    ["liker_did", "post_uri"]
)
post_counts = (likes.group_by("post_uri").agg(pl.len().alias("c"))
               .filter(pl.col("c") >= MIN_POST_LIKERS)
               .collect(engine="streaming"))
print(f"    {len(post_counts):,} co-likeable posts ({el()})", flush=True)

print("[3] edges = eligible user x eligible post (streaming join)...", flush=True)
edges = (likes
    .join(eu.lazy().select("liker_did"), on="liker_did", how="inner")
    .join(post_counts.lazy().select("post_uri"), on="post_uri", how="inner")
    .collect(engine="streaming"))
print(f"    {len(edges):,} edges ({el()})", flush=True)

print("[4] building sparse user x post matrix...", flush=True)
# Stable user ordering = eu's order (so coords line up with handles/colors).
user_ids = eu["liker_did"].to_list()
user_row = {d: i for i, d in enumerate(user_ids)}
post_ids = post_counts["post_uri"].to_list()
post_col = {p: j for j, p in enumerate(post_ids)}

rows = np.fromiter((user_row[d] for d in edges["liker_did"].to_list()),
                   dtype=np.int32, count=len(edges))
cols = np.fromiter((post_col[p] for p in edges["post_uri"].to_list()),
                   dtype=np.int32, count=len(edges))
data = np.ones(len(edges), dtype=np.float32)
X = csr_matrix((data, (rows, cols)), shape=(len(user_ids), len(post_ids)))
# Drop users with no eligible-post likes (all-zero rows would embed nonsensically)
nnz_per_user = np.asarray((X != 0).sum(axis=1)).ravel()
keep = nnz_per_user >= 3
X = X[keep]
handles = [h for h, k in zip(eu["handle"].to_list(), keep) if k]
colors = np.array(eu["mean_log_popularity"].to_list(), dtype=np.float32)[keep]
kept_dids = [d for d, k in zip(user_ids, keep) if k]
print(f"    matrix {X.shape[0]:,} users x {X.shape[1]:,} posts, "
      f"{X.nnz:,} nonzeros ({el()})", flush=True)

print("[5] UMAP (this is the slow part)...", flush=True)
import umap  # imported here so steps 1-4 fail fast if deps/data are off
reducer = umap.UMAP(n_neighbors=N_NEIGHBORS, min_dist=MIN_DIST, metric=METRIC,
                    random_state=SEED, verbose=True)
emb = reducer.fit_transform(X)
print(f"    embedded {emb.shape[0]:,} users ({el()})", flush=True)

print("[6] saving coords + static preview...", flush=True)
pl.DataFrame({
    "liker_did": kept_dids,
    "handle": handles,
    "x": emb[:, 0].astype(np.float32),
    "y": emb[:, 1].astype(np.float32),
    "mean_log_popularity": colors,
}).write_parquet(OUT_COORDS, compression="zstd")

plt.rcParams.update({"figure.facecolor": "#0e1116", "axes.facecolor": "#0e1116"})
fig, ax = plt.subplots(figsize=(12, 12))
sc = ax.scatter(emb[:, 0], emb[:, 1], c=colors, cmap="magma", s=2,
                alpha=0.25, linewidths=0)
ax.set_xticks([]); ax.set_yticks([])
ax.set_title(f"Shared-liked-posts UMAP — {X.shape[0]:,} users\n"
             f"users>{MIN_USER_LIKES} likes, posts>={MIN_POST_LIKERS} likers, "
             f"n_neighbors={N_NEIGHBORS}, min_dist={MIN_DIST}",
             color="#e6edf3")
cb = fig.colorbar(sc, ax=ax, shrink=0.6, label="mean log popularity of liked posts")
cb.outline.set_visible(False)
fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight", facecolor="#0e1116")
print(f"[OK] preview -> {OUT_PNG}", flush=True)
print(f"     coords  -> {OUT_COORDS}  ({el()} total)", flush=True)
