# -*- coding: utf-8 -*-
"""Quick sanity check: how close are two handles in the UMAP map, and does the
proximity reflect genuinely shared liked-posts (the embedding basis)?"""
import sys
import numpy as np
import polars as pl
from bsky_likes import config

A = (sys.argv[1] if len(sys.argv) > 1 else "gracekind.net").lower()
B = (sys.argv[2] if len(sys.argv) > 2 else "cee.wtf").lower()

df = pl.read_parquet(config.PROJECT_DIR / "umap_coords.parquet")
hl = df["handle"].str.to_lowercase()
df = df.with_columns(hl.alias("h"))

def row(handle):
    r = df.filter(pl.col("h") == handle)
    if r.height == 0:
        sys.exit(f"[!] {handle} not in umap_coords (needs >=50 likes to embed)")
    return r.row(0, named=True)

ra, rb = row(A), row(B)
xa, ya = ra["x"], ra["y"]
xb, yb = rb["x"], rb["y"]

xs = df["x"].to_numpy(); ys = df["y"].to_numpy()
d_all = np.hypot(xs - xs.mean(), ys - ys.mean())  # placeholder, not used
# distance from A to everyone
dA = np.hypot(xs - xa, ys - ya)
dAB = float(np.hypot(xb - xa, yb - ya))
# rank of B among A's nearest neighbours (1 = closest other point)
order = np.argsort(dA)
rank_B = int(np.where(df["h"].to_numpy()[order] == B)[0][0])  # 0 = A itself
# typical nearest-neighbour distance across the map (sample)
rng = np.random.default_rng(0)
samp = rng.choice(len(xs), size=min(4000, len(xs)), replace=False)
nn = []
for i in samp:
    dd = np.hypot(xs - xs[i], ys - ys[i]); dd[i] = np.inf
    nn.append(dd.min())
nn_med = float(np.median(nn))

# overall map scale
span = float(np.hypot(xs.max() - xs.min(), ys.max() - ys.min()))

print(f"=== {A}  vs  {B} ===")
print(f"{A:>16}: x={xa:8.3f} y={ya:8.3f}  ({ra['handle']})")
print(f"{B:>16}: x={xb:8.3f} y={yb:8.3f}  ({rb['handle']})")
print(f"\ndistance A->B            : {dAB:.4f}")
print(f"map diagonal span        : {span:.2f}   (A->B is {dAB/span*100:.3f}% of it)")
print(f"median nearest-nbr dist  : {nn_med:.4f}   (A->B is {dAB/nn_med:.2f}x that)")
print(f"\nB is A's #{rank_B} nearest neighbour out of {len(xs):,} embedded users")
print("A's 8 nearest neighbours:")
for j in order[1:9]:
    print(f"   {dA[j]:7.4f}  @{df['handle'].to_numpy()[j]}")
