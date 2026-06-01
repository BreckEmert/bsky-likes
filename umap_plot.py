# -*- coding: utf-8 -*-
"""
umap_plot.py  —  blended-continuum render + cluster naming data

Reads umap_coords.parquet (from umap_explore.py). Renders a smooth, pretty
continuum (color flows by 2D position, so neighbors blend — no hard cluster
edges), while still clustering under the hood to produce naming data: per
cluster, the top accounts by followers AND the authors the cluster most likes
(the real theme signal). Paste umap_clusters.txt back to name the regions.

Run:  python umap_plot.py
"""
import time
import numpy as np
import polars as pl
import matplotlib.pyplot as plt

from bsky_likes import config

# ---- knobs ----
COLOR_MODE = "position"    # "position" (blended rainbow) or "popularity" (magma)
MIN_CLUSTER_SIZE = 400     # HDBSCAN min cluster size
TOP_MEMBERS = 12           # top accounts per cluster by followers
TOP_AUTHORS = 15           # top liked-authors per cluster (theme signal)
SHOW_NUMBERS = True        # faint cluster-id numbers (to match the txt)
FIGSIZE = 26
DPI = 220
OUT_PNG = config.PLOTS_DIR / "umap_continuum.png"
OUT_TXT = config.PROJECT_DIR.parent / "umap_clusters.txt"
COORDS = config.PROJECT_DIR / "umap_coords.parquet"

t0 = time.time()


def el():
    return f"{time.time()-t0:.1f}s"


print("[1] loading coords + followers...", flush=True)
df = pl.read_parquet(COORDS)
# Join on DID (unique) — users.parquet has duplicate handles which would fan out.
users = pl.read_parquet(config.USERS_PATH, columns=["did", "followers_count"]).unique("did")
df = df.join(users, left_on="liker_did", right_on="did", how="left")
xy = np.column_stack([df["x"].to_numpy(), df["y"].to_numpy()]).astype(np.float64)
print(f"    {len(df):,} users ({el()})", flush=True)

print("[2] clustering (for naming only; not shown as hard colors)...", flush=True)
try:
    from sklearn.cluster import HDBSCAN
    labels = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=10,
                     core_dist_n_jobs=-1).fit_predict(xy)
    algo = "HDBSCAN"
except Exception as e:
    print(f"    HDBSCAN unavailable ({e}); KMeans(50)", flush=True)
    from sklearn.cluster import KMeans
    labels = KMeans(n_clusters=50, n_init=4, random_state=42).fit_predict(xy)
    algo = "KMeans50"
df = df.with_columns(pl.Series("cluster", labels))
n_clusters = len({c for c in labels if c >= 0})
print(f"    {algo}: {n_clusters} clusters ({el()})", flush=True)

print("[3] blended-continuum render...", flush=True)
if COLOR_MODE == "position":
    # Bilinear blend of 4 corner colors -> smooth field; neighbors share color.
    tx = (xy[:, 0] - xy[:, 0].min()) / (np.ptp(xy[:, 0]) or 1)
    ty = (xy[:, 1] - xy[:, 1].min()) / (np.ptp(xy[:, 1]) or 1)
    c00 = np.array([0.18, 0.83, 0.75])  # teal   (bottom-left)
    c10 = np.array([0.23, 0.51, 0.96])  # blue   (bottom-right)
    c01 = np.array([0.96, 0.62, 0.04])  # amber  (top-left)
    c11 = np.array([0.93, 0.28, 0.60])  # pink   (top-right)
    rgb = ((1 - tx)[:, None] * (1 - ty)[:, None] * c00
           + tx[:, None] * (1 - ty)[:, None] * c10
           + (1 - tx)[:, None] * ty[:, None] * c01
           + tx[:, None] * ty[:, None] * c11)
    col = np.column_stack([rgb, np.full(len(rgb), 0.35)])
    cmap = None
else:
    col = df["mean_log_popularity"].to_numpy()
    cmap = "magma"

plt.rcParams.update({"figure.facecolor": "#0e1116", "axes.facecolor": "#0e1116"})
fig, ax = plt.subplots(figsize=(FIGSIZE, FIGSIZE))
ax.scatter(xy[:, 0], xy[:, 1], c=col, cmap=cmap, s=2, alpha=0.35, linewidths=0)
if SHOW_NUMBERS:
    for c in range(n_clusters):
        m = labels == c
        ax.text(xy[m, 0].mean(), xy[m, 1].mean(), str(c), color="white",
                fontsize=8, ha="center", va="center", alpha=0.55)
ax.set_xticks([]); ax.set_yticks([])
fig.savefig(OUT_PNG, dpi=DPI, bbox_inches="tight", facecolor="#0e1116")
print(f"    -> {OUT_PNG} ({el()})", flush=True)

print("[4] naming data: top liked-authors per cluster (streaming join)...", flush=True)
cluster_map = df.select(["liker_did", "cluster"]).filter(pl.col("cluster") >= 0)
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(
    ["liker_did", "post_uri"])
posts = pl.scan_parquet(str(config.POSTS_PATH)).select(["post_uri", "post_author_did"])
ca = (likes
      .join(cluster_map.lazy(), on="liker_did", how="inner")
      .join(posts, on="post_uri", how="inner")
      .group_by(["cluster", "post_author_did"]).agg(pl.len().alias("c"))
      .collect(engine="streaming"))
# author did -> handle
au = pl.read_parquet(config.USERS_PATH, columns=["did", "handle"])
ca = ca.join(au, left_on="post_author_did", right_on="did", how="left")
print(f"    aggregated ({el()})", flush=True)

print("[5] writing umap_clusters.txt...", flush=True)
lines = [f"UMAP clusters ({algo}), {n_clusters} regions, {len(df):,} users.",
         "Numbers match umap_continuum.png. For each region: prominent members "
         "(by followers) + the authors that region most likes (the theme).", ""]
for c in range(n_clusters):
    cl = df.filter(pl.col("cluster") == c)
    members = (cl.sort("followers_count", descending=True)
                 .head(TOP_MEMBERS)["handle"].to_list())
    authors = (ca.filter((pl.col("cluster") == c) & pl.col("handle").is_not_null())
                 .sort("c", descending=True).head(TOP_AUTHORS)["handle"].to_list())
    lines.append(f"=== cluster {c}  ({len(cl):,} users) ===")
    lines.append("  members: " + ", ".join("@" + h for h in members))
    lines.append("  likes:   " + ", ".join("@" + h for h in authors))
    lines.append("")
OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
print(f"[OK] {OUT_TXT}  ({el()} total) — paste it to me to name the regions.",
      flush=True)
