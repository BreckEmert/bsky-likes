# -*- coding: utf-8 -*-
"""
export_curve_hist.py

Per-user histograms for the Popularity Curve svg-line highlight: for each
eligible liker (>=50 likes, matching the plot), the distribution of
log10(liked-post like_count + 1) over BINS bins in [0, 6], smoothed to a density
and quantized to uint8 (~9MB total instead of ~36MB float32).

Outputs (site/public/plots/):
  popularity-curve.handles.bin       eligible handles (lowercased)
  popularity-curve.histograms.bin    uint8 [N x BINS] row-major, parallel to handles
  popularity-curve.histmeta.json     {bins, xMinLog, xMaxLog, densityMax}

The site de-quantizes density = q/255 * densityMax and draws the polyline over
the faint PNG mass, mapping bin-center (log value) -> x and density -> y via the
plot's bounds (xMin 0, xMax 5, yMin 0, yMax 1.5).
"""
import json
import struct
import time

import numpy as np
import polars as pl
from scipy.ndimage import gaussian_filter1d

from bsky_likes import config

BINS = 64
LO, HI = 0.0, 6.0
SMOOTH_SIGMA = 1.8           # bins; matches the PNG's smoothed look
DENSITY_MAX = 4.0            # quantization ceiling (site bounds clip at 1.5)
MIN_LIKES = 50
OUT = config.PROJECT_DIR.parent / "site" / "public" / "plots"

t0 = time.time()
print("[1] eligible likers from per_liker (n_likes>=50)...", flush=True)
per_liker = pl.read_parquet(config.PER_LIKER_PATH)
elig = per_liker.filter(
    (pl.col("n_likes") >= MIN_LIKES) & pl.col("handle").is_not_null()
).select(["liker_did", "handle"])
print(f"    {len(elig):,} eligible ({time.time()-t0:.1f}s)", flush=True)

print("[2] streaming join + per-(liker,bin) counts...", flush=True)
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet"))
posts = (pl.scan_parquet(str(config.POSTS_PATH))
    .filter(pl.col("quote_count") >= 0)
    .filter(pl.col("post_created_at") >= pl.datetime(2023, 1, 1, time_zone="UTC"))
    .select(["post_uri", "like_count"]))
step = (HI - LO) / BINS
sparse = (likes.join(posts, on="post_uri", how="inner")
    .with_columns(((pl.col("like_count").cast(pl.Float64) + 1).log10()).alias("lv"))
    .filter((pl.col("lv") >= LO) & (pl.col("lv") < HI))
    .with_columns(((pl.col("lv") - LO) / step).floor().cast(pl.Int32).alias("bin"))
    .join(elig.lazy().select("liker_did"), on="liker_did", how="inner")
    .group_by(["liker_did", "bin"]).agg(pl.len().alias("c"))
    .collect(engine="streaming"))
print(f"    sparse rows: {len(sparse):,} ({time.time()-t0:.1f}s)", flush=True)

print("[3] pivot to dense matrix + normalize + smooth + quantize...", flush=True)
# Map liker_did -> row index over the eligible set (keep handle order stable).
dids = elig["liker_did"].to_list()
handles = [h.lower() for h in elig["handle"].to_list()]
row_of = {d: i for i, d in enumerate(dids)}
N = len(dids)
mat = np.zeros((N, BINS), dtype=np.float64)
rd = sparse["liker_did"].to_list()
rb = sparse["bin"].to_numpy()
rc = sparse["c"].to_numpy()
for d, b, c in zip(rd, rb, rc):
    r = row_of.get(d)
    if r is not None and 0 <= b < BINS:
        mat[r, b] = c

# Drop users with too few in-range likes (need a real distribution).
totals = mat.sum(axis=1)
keep = totals >= MIN_LIKES
mat = mat[keep]
handles = [h for h, k in zip(handles, keep) if k]
totals = totals[keep]
print(f"    kept {len(handles):,} users with >= {MIN_LIKES} in-range likes", flush=True)

# Normalize each row to a density, smooth (matches the PNG), quantize to uint8.
dens = mat / (totals[:, None] * step)
dens = gaussian_filter1d(dens, sigma=SMOOTH_SIGMA, axis=1)
q = np.clip(np.round(dens / DENSITY_MAX * 255.0), 0, 255).astype(np.uint8)

print("[4] writing...", flush=True)
# handles.bin (Theo format)
enc = [h.encode("utf-8") for h in handles]
offsets = [0]
for b in enc:
    offsets.append(offsets[-1] + len(b))
with open(OUT / "popularity-curve.handles.bin", "wb") as f:
    f.write(struct.pack("<I", len(enc)))
    f.write(struct.pack(f"<{len(enc)+1}I", *offsets))
    for b in enc:
        f.write(b)
q.tofile(OUT / "popularity-curve.histograms.bin")
(OUT / "popularity-curve.histmeta.json").write_text(json.dumps({
    "bins": BINS, "xMinLog": LO, "xMaxLog": HI, "densityMax": DENSITY_MAX,
}))
print(f"[OK] {len(handles):,} histograms x {BINS} bins "
      f"({q.nbytes/1e6:.1f} MB)  done in {time.time()-t0:.1f}s", flush=True)
