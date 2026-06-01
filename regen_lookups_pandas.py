# -*- coding: utf-8 -*-
"""
regen_lookups_pandas.py  (polars-free fallback)

Regenerates ONLY the like-repost + punching binary lookups using pandas +
pyarrow, avoiding `import polars` (which is currently hanging on this machine
while numpy/pyarrow import fine). Produces results identical to export_web's
polars exporters. activity/typical-popularity/leaderboards already exist.

Outputs: like-repost.{handles,positions}.bin, punching.{handles,positions}.bin
"""
import struct
import time
import numpy as np
import pandas as pd

print("[0] start", flush=True)
_t = time.time()
ROOT = "F:/GitHub/bsky-likes-analysis"
DATA = ROOT + "/bsky_data"
OUT = ROOT + "/site/public/plots"


# --- binary writers (copied from export_web; pure python/numpy, no polars) ---
def write_handles_bin(handles, path):
    enc = [h.encode("utf-8") for h in handles]
    n = len(enc)
    offsets = [0]
    for b in enc:
        offsets.append(offsets[-1] + len(b))
    with open(path, "wb") as f:
        f.write(struct.pack("<I", n))
        f.write(struct.pack(f"<{n+1}I", *offsets))
        for b in enc:
            f.write(b)
    import os
    print(f"[OK] {os.path.basename(path)}: {n:,} handles "
          f"({os.path.getsize(path)/1e6:.1f} MB)", flush=True)


def write_positions_bin(xy, path):
    arr = np.asarray(xy, dtype=np.float32).reshape(-1)
    arr.tofile(path)
    import os
    print(f"[OK] {os.path.basename(path)}: {len(arr)//2:,} positions "
          f"({os.path.getsize(path)/1e6:.1f} MB)", flush=True)


print("[1] reading posts.parquet (5 cols) via pyarrow...", flush=True)
posts = pd.read_parquet(
    DATA + "/posts.parquet",
    columns=["post_author_did", "like_count", "repost_count",
             "quote_count", "post_created_at"],
)
print(f"[2] posts read: {len(posts):,} rows ({time.time()-_t:.1f}s)", flush=True)

# Clean filter (matches plots.py / export): quote_count >= 0, post >= 2023.
cutoff = pd.Timestamp("2023-01-01", tz="UTC")
posts = posts[(posts["quote_count"] >= 0) & (posts["post_created_at"] >= cutoff)]
print(f"[3] after clean filter: {len(posts):,} rows ({time.time()-_t:.1f}s)", flush=True)

print("[4] groupby author (mean like/repost, sum like, count)...", flush=True)
g = posts.groupby("post_author_did", sort=False).agg(
    avg_likes=("like_count", "mean"),
    avg_reposts=("repost_count", "mean"),
    total_likes=("like_count", "sum"),
    n_posts=("like_count", "size"),
)
print(f"[5] grouped: {len(g):,} authors ({time.time()-_t:.1f}s)", flush=True)

users = pd.read_parquet(DATA + "/users.parquet", columns=["did", "handle", "followers_count"])
print(f"[6] users read: {len(users):,} ({time.time()-_t:.1f}s)", flush=True)

# --- like-repost (Plot 5 axes/filters; no +1, filter ensures avg >= 1) ------
lr = g[(g["n_posts"] >= 5) & (g["avg_likes"] >= 1) & (g["avg_reposts"] >= 1)].reset_index()
lr = lr.merge(users[["did", "handle"]], left_on="post_author_did", right_on="did", how="inner")
lr = lr[lr["handle"].notna()]
handles = lr["handle"].str.lower().tolist()
xy = np.column_stack([lr["avg_likes"].to_numpy(np.float32),
                      lr["avg_reposts"].to_numpy(np.float32)])
write_handles_bin(handles, OUT + "/like-repost.handles.bin")
write_positions_bin(xy, OUT + "/like-repost.positions.bin")
print(f"[7] like-repost done ({time.time()-_t:.1f}s)", flush=True)

# --- punching (top-4000 by total_likes + highlighted; +1 offsets) -----------
HIGHLIGHT = {
    "jcsalterego.bsky.social", "cee.wtf", "avikdey.bsky.social",
    "hankgreen.bsky.social", "ceej.online", "jefferyharrell.bsky.social",
    "invert.bsky.social", "juniorhoncho.bsky.social", "lastnpcalex.agency",
    "aly.codes", "segyges.bsky.social", "moultano.bsky.social",
    "seanmcarroll.bsky.social", "sincerely.cam", "searyanc.dev",
    "jdp.extropian.net", "timkellogg.me", "gracekind.net",
    "contrapoints.bsky.social", "3blue1brown.com", "standupmaths.bsky.social",
    "hern.bsky.social", "10x.bsky.social", "zswitten.bsky.social",
    "dave.9000ish.uk", "phillipcarter.dev", "tszzl.bsky.social",
}
pu = g[g["n_posts"] >= 5].reset_index()
pu = pu.merge(users, left_on="post_author_did", right_on="did", how="inner")
pu = pu[pu["handle"].notna()]
pu["likes_per_post"] = pu["total_likes"] / pu["n_posts"]
top4000 = pu.nlargest(4000, "total_likes")
missing = pu[pu["handle"].isin(HIGHLIGHT) & ~pu["handle"].isin(top4000["handle"])]
author_df = pd.concat([top4000, missing], ignore_index=True) if len(missing) else top4000
handles = author_df["handle"].str.lower().tolist()
xy = np.column_stack([(author_df["followers_count"].to_numpy(np.float64) + 1).astype(np.float32),
                      (author_df["likes_per_post"].to_numpy(np.float64) + 1).astype(np.float32)])
write_handles_bin(handles, OUT + "/punching.handles.bin")
write_positions_bin(xy, OUT + "/punching.positions.bin")
print(f"[8] punching done. ALL DONE ({time.time()-_t:.1f}s)", flush=True)
