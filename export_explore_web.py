# -*- coding: utf-8 -*-
"""
export_explore_web.py  —  web data for the deck.gl exploration map (Theo model)

Reads umap_coords.parquet and emits, into site/public/explore/:
  density.png  RGBA continuum-colored density field (the smooth background that
               carries the map at zoom-out and fades as you zoom in)
  points.bin   Float32 [x0,y0,...]  SORTED BY LOCAL DENSITY desc (so the overview
               LOD shows the dense cluster cores; sparser zones reveal on zoom-in)
  colors.bin   uint8 [r,g,b,...]    position-continuum color, same order
  handles.bin  Theo format, same order
  meta.json    {numPoints, bounds}
"""
import json
import struct
import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

from bsky_likes import config

OUT = config.PROJECT_DIR.parent / "site" / "public" / "explore"
OUT.mkdir(parents=True, exist_ok=True)
GRID = 1024        # density image resolution (higher = crisper)
BLUR = 2.6         # gaussian sigma (in cells); lower = crisper, less bloom

df = pl.read_parquet(config.PROJECT_DIR / "umap_coords.parquet")
# Restrict the plotted dots to the English-only user set (same set the topical
# labels are built on), so the non-English language islands don't show as
# unlabeled blobs. Falls back to all users if the filter file is absent.
en_path = config.PROJECT_DIR / "english_dids.json"
if en_path.exists():
    en = set(json.loads(en_path.read_text()))
    before = df.height
    df = df.filter(pl.col("liker_did").is_in(list(en)))
    print(f"[i] filtered to English set: {df.height:,} of {before:,} users")

x = df["x"].to_numpy().astype(np.float64)
y = df["y"].to_numpy().astype(np.float64)
handles_all = [h.lower() for h in df["handle"].to_list()]
dids_all = df["liker_did"].to_list()
xMin, xMax, yMin, yMax = x.min(), x.max(), y.min(), y.max()

# --- density grid (2D histogram, blurred) ---------------------------------
H, _, _ = np.histogram2d(x, y, bins=GRID, range=[[xMin, xMax], [yMin, yMax]])  # [xbin, ybin]
D = gaussian_filter(H, sigma=BLUR)
Dn = D / (D.max() or 1)

# --- position-continuum color (shared by background + points) -------------
c00 = np.array([46, 212, 191]); c10 = np.array([59, 130, 246])
c01 = np.array([245, 158, 11]); c11 = np.array([236, 72, 153])


def continuum(tx, ty):
    return ((1 - tx)[..., None] * (1 - ty)[..., None] * c00
            + tx[..., None] * (1 - ty)[..., None] * c10
            + (1 - tx)[..., None] * ty[..., None] * c01
            + tx[..., None] * ty[..., None] * c11)


# --- density background image (RGBA, row 0 = yMax = top) -------------------
rows, cols = np.mgrid[0:GRID, 0:GRID]
tx_img = cols / (GRID - 1)
ty_img = 1.0 - rows / (GRID - 1)          # row 0 -> ty 1 -> yMax (top)
rgb_img = continuum(tx_img, ty_img)
alpha = (np.flipud(Dn.T) ** 1.1)          # Dn is [x,y] -> .T [y,x] -> flip so row0=yMax
# exponent >1 DIMS low densities so sparse/isolated points stop punching colored
# speckles into the smooth field (was 0.5, which brightened them); higher = cleaner
rgba = np.dstack([rgb_img, alpha * 255.0]).clip(0, 255).astype(np.uint8)
plt.imsave(OUT / "density.png", rgba)

# --- per-point density (for color/secondary ordering) ---------------------
xb = np.clip(((x - xMin) / (xMax - xMin) * (GRID - 1)).astype(int), 0, GRID - 1)
yb = np.clip(((y - yMin) / (yMax - yMin) * (GRID - 1)).astype(int), 0, GRID - 1)
pt_density = D[xb, yb]

# --- STRATIFIED ("blue-noise") ordering ------------------------------------
# Instead of densest-first (which makes the overview LOD show ONLY the dense
# cores, not matching the color field), order so any prefix is spread evenly
# across space: take the 1st point of every occupied cell, then the 2nd of
# each, etc. The visible subset then traces the whole footprint at every zoom
# (Theo's "constant density per zoom" feel) and fills in proportionally as the
# LOD count grows. Within each rank-tier, denser cells come first so the cores
# still brighten faster -- accentuating, not replacing, the color layer.
SGRID = 256                                # stratification cells per axis
sxb = np.clip(((x - xMin) / (xMax - xMin) * (SGRID - 1)).astype(int), 0, SGRID - 1)
syb = np.clip(((y - yMin) / (yMax - yMin) * (SGRID - 1)).astype(int), 0, SGRID - 1)
cell = sxb.astype(np.int64) * SGRID + syb

n = len(x)
rng = np.random.default_rng(0)             # deterministic shuffle for tie-break
shuf = rng.permutation(n)
by_cell = np.argsort(cell[shuf], kind="stable")     # group shuffled pts by cell
sorted_cells = cell[shuf][by_cell]
_, start_idx, counts = np.unique(sorted_cells, return_index=True, return_counts=True)
within = np.arange(n) - np.repeat(start_idx, counts)  # rank within each cell
cnt = np.repeat(counts, counts)                       # cell size (sorted order)
orig = shuf[by_cell]                                  # -> original indices
ranks = np.empty(n, dtype=np.int64); ranks[orig] = within
cell_cnt = np.empty(n, dtype=np.int64); cell_cnt[orig] = cnt

# Density-biased stratification key. ALPHA in [0,1]:
#   0 -> pure even (one point per cell per tier; can look too uniform)
#   1 -> proportional to cell density (full clustering, matches color field)
# A small ALPHA pulls a few extra points into dense cells and fewer into sparse
# cells for any LOD prefix, so the layer reads less uniform / more clustered.
ALPHA = 0.6
key = (ranks + 0.5) / np.power(cell_cnt, ALPHA)
# primary: biased key asc; secondary: density desc (cores first within ties)
order = np.lexsort((-pt_density, key))
print(f"[i] {len(start_idx):,} occupied cells (SGRID={SGRID}, ALPHA={ALPHA}); "
      f"rank-0 layer = {int((ranks == 0).sum()):,} seed points")

xs = x[order].astype(np.float32)
ys = y[order].astype(np.float32)
handles = [handles_all[i] for i in order]
tx = (xs - xs.min()) / (np.ptp(xs) or 1)
ty = (ys - ys.min()) / (np.ptp(ys) or 1)
colors = continuum(tx, ty).clip(0, 255).astype(np.uint8)

n = len(xs)
xy = np.empty(n * 2, dtype=np.float32)
xy[0::2] = xs; xy[1::2] = ys
xy.tofile(OUT / "points.bin")
colors.tofile(OUT / "colors.bin")

# --- topic colors (2nd color layer): each point by its tier-1 topic, aligned
#     to the point order. Drives the 'Topics' color mode + legend on the site.
leg_path = OUT / "topic_legend.json"
mem_path = config.PROJECT_DIR / "cluster_members_en.parquet"
if leg_path.exists() and mem_path.exists():
    legend = {int(L["id"]): L["color"] for L in json.loads(leg_path.read_text())}
    mem = pl.read_parquet(mem_path)
    d2t = dict(zip(mem["liker_did"].to_list(), mem["topic"].to_list()))
    GRAY = [70, 80, 92]
    dids_sorted = [dids_all[i] for i in order]
    ctop = np.array([legend.get(int(d2t[d]), GRAY) if d in d2t else GRAY
                     for d in dids_sorted], dtype=np.uint8)
    ctop.tofile(OUT / "colors_topic.bin")
    print(f"[i] colors_topic.bin ({ctop.shape[0]:,} pts, {len(legend)} topics)")

enc = [h.encode("utf-8") for h in handles]
offs = [0]
for b in enc:
    offs.append(offs[-1] + len(b))
with open(OUT / "handles.bin", "wb") as f:
    f.write(struct.pack("<I", n))
    f.write(struct.pack(f"<{n+1}I", *offs))
    for b in enc:
        f.write(b)

(OUT / "meta.json").write_text(json.dumps({
    "numPoints": n,
    "bounds": {"xMin": float(xMin), "xMax": float(xMax),
               "yMin": float(yMin), "yMax": float(yMax)},
}))
print(f"[OK] {n:,} points (density-sorted) + density.png ({GRID}x{GRID}) -> {OUT}")
