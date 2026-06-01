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
GRID = 640         # density image resolution
BLUR = 5.0         # gaussian sigma (in cells) for a smooth field

df = pl.read_parquet(config.PROJECT_DIR / "umap_coords.parquet")
x = df["x"].to_numpy().astype(np.float64)
y = df["y"].to_numpy().astype(np.float64)
handles_all = [h.lower() for h in df["handle"].to_list()]
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
alpha = (np.flipud(Dn.T) ** 0.55)         # Dn is [x,y] -> .T [y,x] -> flip so row0=yMax
rgba = np.dstack([rgb_img, alpha * 255.0]).clip(0, 255).astype(np.uint8)
plt.imsave(OUT / "density.png", rgba)

# --- per-point density -> sort cores first --------------------------------
xb = np.clip(((x - xMin) / (xMax - xMin) * (GRID - 1)).astype(int), 0, GRID - 1)
yb = np.clip(((y - yMin) / (yMax - yMin) * (GRID - 1)).astype(int), 0, GRID - 1)
pt_density = D[xb, yb]
order = np.argsort(-pt_density)           # densest first

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
