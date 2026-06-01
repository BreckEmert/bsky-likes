# -*- coding: utf-8 -*-
"""
umap_plot.py  —  cluster + high-res render of an existing UMAP embedding

Reads umap_coords.parquet (written by umap_explore.py) so it's INSTANT — no
re-embedding. Clusters the 2D layout, colors by cluster so separation shows,
saves a big zoomable PNG, and dumps each cluster's most-prominent accounts to a
text file so we can name the regions (Theo-style).

Run:  python umap_plot.py
Tune: MIN_CLUSTER_SIZE (bigger = fewer, broader regions), DPI/FIGSIZE for res.
"""
import time
import numpy as np
import polars as pl
import matplotlib.pyplot as plt

from bsky_likes import config

# ---- knobs ----
MIN_CLUSTER_SIZE = 400     # HDBSCAN: min users to count as a cluster
TOP_PER_CLUSTER = 15       # prominent accounts listed per cluster (for naming)
FIGSIZE = 26               # inches; with DPI -> pixels (26*220 ~ 5700px)
DPI = 220
OUT_PNG = config.PLOTS_DIR / "umap_clusters.png"
OUT_TXT = config.PROJECT_DIR.parent / "umap_clusters.txt"   # repo root, easy to read
COORDS = config.PROJECT_DIR / "umap_coords.parquet"

t0 = time.time()
print("[1] loading coords + follower counts...", flush=True)
df = pl.read_parquet(COORDS)
users = pl.read_parquet(config.USERS_PATH, columns=["handle", "followers_count"])
df = df.join(users, on="handle", how="left")
xy = np.column_stack([df["x"].to_numpy(), df["y"].to_numpy()]).astype(np.float32)
print(f"    {len(df):,} users ({time.time()-t0:.1f}s)", flush=True)

print("[2] clustering...", flush=True)
labels = None
try:
    from sklearn.cluster import HDBSCAN
    labels = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=10,
                     core_dist_n_jobs=-1).fit_predict(xy)
    algo = "HDBSCAN"
except Exception as e:
    print(f"    HDBSCAN unavailable ({e}); falling back to KMeans(50)", flush=True)
    from sklearn.cluster import KMeans
    labels = KMeans(n_clusters=50, n_init=4, random_state=42).fit_predict(xy)
    algo = "KMeans50"
df = df.with_columns(pl.Series("cluster", labels))
n_clusters = len({c for c in labels if c >= 0})
n_noise = int((labels < 0).sum())
print(f"    {algo}: {n_clusters} clusters, {n_noise:,} noise ({time.time()-t0:.1f}s)",
      flush=True)

print("[3] high-res render (colored by cluster)...", flush=True)
plt.rcParams.update({"figure.facecolor": "#0e1116", "axes.facecolor": "#0e1116"})
fig, ax = plt.subplots(figsize=(FIGSIZE, FIGSIZE))
rng = np.random.default_rng(1)
palette = plt.get_cmap("tab20")(np.linspace(0, 1, 20))
# noise = dim gray; each cluster a cycled palette color
col = np.tile([0.4, 0.4, 0.45, 0.25], (len(labels), 1))
for c in range(n_clusters):
    m = labels == c
    col[m] = palette[c % 20]
    col[m, 3] = 0.35
ax.scatter(xy[:, 0], xy[:, 1], c=col, s=2, linewidths=0)
# cluster-id numbers at centroids (match to the txt dump)
for c in range(n_clusters):
    m = labels == c
    cx, cy = xy[m, 0].mean(), xy[m, 1].mean()
    ax.text(cx, cy, str(c), color="white", fontsize=9, ha="center", va="center",
            fontweight="bold", alpha=0.8)
ax.set_xticks([]); ax.set_yticks([])
ax.set_title(f"UMAP clusters ({algo}, {n_clusters} regions) — numbers match "
             f"umap_clusters.txt", color="#e6edf3")
fig.savefig(OUT_PNG, dpi=DPI, bbox_inches="tight", facecolor="#0e1116")
print(f"    -> {OUT_PNG} ({time.time()-t0:.1f}s)", flush=True)

print("[4] per-cluster top accounts (by followers) -> txt...", flush=True)
lines = [f"UMAP clusters ({algo}), {n_clusters} regions, {len(df):,} users",
         "Cluster id matches the number on the PNG. Top accounts by follower "
         "count (a proxy for what the cluster is about).", ""]
for c in range(n_clusters):
    cl = df.filter(pl.col("cluster") == c)
    top = (cl.sort("followers_count", descending=True)
             .head(TOP_PER_CLUSTER))
    handles = [f"@{h}" for h in top["handle"].to_list()]
    lines.append(f"--- cluster {c}  ({len(cl):,} users) ---")
    lines.append("  " + ", ".join(handles))
    lines.append("")
OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
print(f"[OK] wrote {OUT_TXT}  ({time.time()-t0:.1f}s total)", flush=True)
print("    Paste umap_clusters.txt to me and I'll name the regions.", flush=True)
