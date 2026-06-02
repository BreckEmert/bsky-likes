# -*- coding: utf-8 -*-
"""
export_liketiming.py  —  per-AUTHOR "like-timing fingerprint" for the
half-life plot's svg-line highlight.

For every collected like:  age = like_created_at - post_created_at  (seconds).
Per author, the distribution of log10(age) over BINS bins -> how fast that
person's posts get liked. Mirrors export_curve_hist.py exactly (so the existing
SvgLine + useHistograms + bounds machinery just works), but the metric is
log10(age-seconds) instead of log10(post popularity), grouped by author.

Outputs (site/public/plots/):
  half-life.png / half-life.bounds.json   faint mass of author curves + bounds
  half-life.handles.bin                   author handles (lowercased)
  half-life.histograms.bin                uint8 [N x BINS] densities, parallel
  half-life.histmeta.json                 {bins, xMinLog, xMaxLog, densityMax}
"""
import json
import struct
import time
import numpy as np
import polars as pl
from scipy.ndimage import gaussian_filter1d
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from bsky_likes import config
import export_web as ew

BINS = 64
LO, HI = 0.0, 8.0            # log10(seconds): 1s -> 10^8 s (~3.2 yr)
SMOOTH_SIGMA = 1.8
DENSITY_MAX = 6.0
MIN_LIKES = 50               # authors need >= this many collected likes received
SEED = 0
OUT = config.PROJECT_DIR.parent / "site" / "public" / "plots"
step = (HI - LO) / BINS

t0 = time.time()
print("[1] streaming join likes->posts, per-(author,bin) age counts...", flush=True)
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(
    ["post_uri", "like_created_at"])
posts = pl.scan_parquet(str(config.POSTS_PATH)).select(
    ["post_uri", "post_author_did", "post_created_at"])
sparse = (likes.join(posts, on="post_uri", how="inner")
    .with_columns(((pl.col("like_created_at") - pl.col("post_created_at"))
                   .dt.total_seconds().cast(pl.Float64)).alias("age"))
    .filter(pl.col("age") >= 1.0)
    .with_columns(pl.col("age").log10().alias("lv"))
    .filter((pl.col("lv") >= LO) & (pl.col("lv") < HI))
    .with_columns(((pl.col("lv") - LO) / step).floor().cast(pl.Int32).alias("bin"))
    .group_by(["post_author_did", "bin"]).agg(pl.len().alias("c"))
    .collect(engine="streaming"))
print(f"    sparse rows: {len(sparse):,} ({time.time()-t0:.1f}s)", flush=True)

print("[2] author -> handle, dense matrix, filter, normalize, smooth...", flush=True)
users = pl.read_parquet(config.USERS_PATH, columns=["did", "handle"]).unique("did")
hmap = dict(zip(users["did"].to_list(), users["handle"].to_list()))

authors = sparse["post_author_did"].unique().to_list()
row_of = {d: i for i, d in enumerate(authors)}
N = len(authors)
mat = np.zeros((N, BINS), dtype=np.float64)
for d, b, c in zip(sparse["post_author_did"].to_list(),
                   sparse["bin"].to_numpy(), sparse["c"].to_numpy()):
    if 0 <= b < BINS:
        mat[row_of[d], b] = c

totals = mat.sum(axis=1)
keep = totals >= MIN_LIKES
handles = [(hmap.get(authors[i]) or "").lower() for i in range(N)]
keep &= np.array([bool(handles[i]) for i in range(N)])
mat = mat[keep]
handles = [h for h, k in zip(handles, keep) if k]
totals = totals[keep]
print(f"    {len(handles):,} authors with >= {MIN_LIKES} likes + a handle", flush=True)

dens = mat / (totals[:, None] * step)
dens = gaussian_filter1d(dens, sigma=SMOOTH_SIGMA, axis=1)
q = np.clip(np.round(dens / DENSITY_MAX * 255.0), 0, 255).astype(np.uint8)

print("[3] faint-mass PNG + bounds...", flush=True)
xc = LO + (np.arange(BINS) + 0.5) * step
plt.rcParams.update({"axes.facecolor": "#0e1116"})
fig, ax = plt.subplots(figsize=(11, 6.5))
rng = np.random.default_rng(SEED)
samp = rng.choice(len(dens), size=min(7000, len(dens)), replace=False)
for r in samp:
    ax.plot(xc, dens[r], color="#1d9bf0", alpha=0.012, linewidth=0.7)
ax.set_xlim(LO, HI); ax.set_ylim(0, 2.0)
# human time ticks at their log10(second) positions
ticks = {"1s": 0, "1m": np.log10(60), "1h": np.log10(3600), "1d": np.log10(86400),
         "1wk": np.log10(604800), "1mo": np.log10(2.63e6), "1yr": np.log10(3.15e7)}
ax.set_xticks(list(ticks.values())); ax.set_xticklabels(list(ticks.keys()))
ax.set_xlabel("post age when liked"); ax.set_ylabel("share of likes (density)")
ax.tick_params(colors="#9aa4b1"); ax.xaxis.label.set_color("#9aa4b1"); ax.yaxis.label.set_color("#9aa4b1")
for s in ax.spines.values(): s.set_color("#1f2933")
ew.export_png_and_bounds(fig, ax, "half-life", x_log=False, y_log=False)

print("[4] writing histograms...", flush=True)
enc = [h.encode("utf-8") for h in handles]
offs = [0]
for b in enc:
    offs.append(offs[-1] + len(b))
with open(OUT / "half-life.handles.bin", "wb") as f:
    f.write(struct.pack("<I", len(enc)))
    f.write(struct.pack(f"<{len(enc)+1}I", *offs))
    for b in enc:
        f.write(b)
q.tofile(OUT / "half-life.histograms.bin")
(OUT / "half-life.histmeta.json").write_text(json.dumps({
    "bins": BINS, "xMinLog": LO, "xMaxLog": HI, "densityMax": DENSITY_MAX}))
print(f"[OK] {len(handles):,} author histograms x {BINS} bins "
      f"({q.nbytes/1e6:.1f} MB) in {time.time()-t0:.1f}s", flush=True)
