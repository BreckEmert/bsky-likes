# -*- coding: utf-8 -*-
"""
export_punching_web.py — regenerate ONLY the web "punching" (Likes vs Followers)
assets, without running the whole plots.py pipeline.

Mirrors the WEB punching cell in plots.py: a HEXBIN density of *every* liked
account (n_posts >= 5), x = follower count (log, from 1e2), y = avg likes per
post (log, from 1e0). Also re-exports the full handle/position lookups so the
client's "highlight 15 you follow" overlay still lands on the new axes.

Run:  python export_punching_web.py
Outputs (site/public/plots/): punching.png, punching.bounds.json,
punching.handles.bin, punching.positions.bin
"""
import matplotlib
matplotlib.use("Agg")  # headless

import matplotlib.pyplot as plt
import polars as pl

from bsky_likes import config
import export_web as ew

PROJECT_DIR = config.PROJECT_DIR

# --- load the same frames plots.py uses (posts_df, users_df) -----------------
posts = (
    pl.scan_parquet(str(PROJECT_DIR / "posts.parquet"))
    .with_columns(pl.col("like_count").cast(pl.Int32),
                  pl.col("quote_count").cast(pl.Int32))
    .filter(pl.col("quote_count") >= 0)
    .filter(pl.col("post_created_at") >= pl.datetime(2023, 1, 1, time_zone="UTC"))
)
users = pl.scan_parquet(str(PROJECT_DIR / "users.parquet")).with_columns(
    pl.col("followers_count").cast(pl.Int32)
)
posts_df = posts.collect()
users_df = users.collect()

# --- author_df_full: every author with >= 5 posts ---------------------------
author_stats = (
    posts_df.group_by("post_author_did")
    .agg(pl.col("like_count").sum().alias("total_likes"),
         pl.len().alias("n_posts"))
    .filter(pl.col("n_posts") >= 5)
    .join(users_df.select(["did", "handle", "followers_count"]),
          left_on="post_author_did", right_on="did", how="inner")
)
author_df_full = author_stats.with_columns(
    (pl.col("total_likes") / pl.col("n_posts")).alias("likes_per_post")
).to_pandas()
print(f"author_df_full: {len(author_df_full):,} accounts (n_posts >= 5)")

# --- the hexbin figure (identical params to plots.py WEB punching cell) ------
fig, ax = plt.subplots(figsize=(12, 7.5))
hb = ax.hexbin(
    author_df_full["followers_count"] + 1,
    author_df_full["likes_per_post"] + 1,
    xscale="log", yscale="log",
    gridsize=72, cmap="plasma", mincnt=1, bins="log", linewidths=0.2,
)
ax.set_xlim(1e2, 10 ** 6.5)   # followers from 10^2
ax.set_ylim(1, None)          # avg likes/post from 10^0
cb = fig.colorbar(hb, ax=ax, label="accounts per hex (log)")
cb.outline.set_visible(False)
ax.set_xlabel("Follower count")
ax.set_ylabel("Avg likes per post")
ax.set_title("Likes vs followers — every liked account", fontsize=18)

ew.export_png_and_bounds(fig, ax, "punching", x_log=True, y_log=True)
ew.export_punching(author_df_full)
plt.close("all")
print("[OK] punching web assets regenerated")
