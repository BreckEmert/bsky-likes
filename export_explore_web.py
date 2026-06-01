# -*- coding: utf-8 -*-
"""
export_explore_web.py  —  web data for the deck.gl exploration map

Reads umap_coords.parquet and emits, into site/public/explore/:
  points.bin   Float32 [x0,y0,x1,y1,...]  (UMAP coords, SORTED by followers desc)
  colors.bin   uint8   [r,g,b,...]         (position-continuum color, same order)
  handles.bin  Theo format (count, offsets, utf8)  (same order)
  meta.json    {numPoints, bounds}

Sort-by-followers gives free LOD: the site renders only the first N points when
zoomed out (the most prominent accounts) and more as you zoom in, all from one
GPU buffer.
"""
import json
import struct
import numpy as np
import polars as pl

from bsky_likes import config

OUT = config.PROJECT_DIR.parent / "site" / "public" / "explore"
OUT.mkdir(parents=True, exist_ok=True)

df = pl.read_parquet(config.PROJECT_DIR / "umap_coords.parquet")
# Join on DID (unique). users.parquet has duplicate handles, so joining on
# handle fans the rows out.
users = pl.read_parquet(config.USERS_PATH, columns=["did", "followers_count"]).unique("did")
df = (df.join(users, left_on="liker_did", right_on="did", how="left")
        .with_columns(pl.col("followers_count").fill_null(0))
        .sort("followers_count", descending=True))   # LOD order: prominent first

x = df["x"].to_numpy().astype(np.float32)
y = df["y"].to_numpy().astype(np.float32)
handles = [h.lower() for h in df["handle"].to_list()]
n = len(x)

# Position-continuum color (bilinear blend of 4 corner colors) -> uint8 RGB.
tx = (x - x.min()) / (np.ptp(x) or 1)
ty = (y - y.min()) / (np.ptp(y) or 1)
c00 = np.array([46, 212, 191]); c10 = np.array([59, 130, 246])
c01 = np.array([245, 158, 11]); c11 = np.array([236, 72, 153])
rgb = ((1 - tx)[:, None] * (1 - ty)[:, None] * c00
       + tx[:, None] * (1 - ty)[:, None] * c10
       + (1 - tx)[:, None] * ty[:, None] * c01
       + tx[:, None] * ty[:, None] * c11)
colors = np.clip(rgb, 0, 255).astype(np.uint8)

xy = np.empty(n * 2, dtype=np.float32)
xy[0::2] = x; xy[1::2] = y
xy.tofile(OUT / "points.bin")
colors.reshape(-1).tofile(OUT / "colors.bin")

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
    "bounds": {"xMin": float(x.min()), "xMax": float(x.max()),
               "yMin": float(y.min()), "yMax": float(y.max())},
}))
print(f"[OK] explore web data: {n:,} points -> {OUT}")
print(f"     points.bin {xy.nbytes/1e6:.1f}MB  colors.bin {colors.size/1e6:.1f}MB")
