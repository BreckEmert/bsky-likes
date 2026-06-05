# -*- coding: utf-8 -*-
"""
plots.py

Loads the captured Bluesky like dataset and produces:
  - Per-liker mainstreaminess scores (4 variants)
  - 9 exploratory plots, one per cell, each designed to be Bluesky-shareable

Run cell by cell in Spyder (# %% markers) or top-to-bottom from a terminal.
Plots are saved to config.PLOTS_DIR.

============================================================================
DATA LIMITATIONS — known and verified. Read before interpreting any plot.
============================================================================
These are certain properties of how the data was collected. Treat them as
ground truth; append newly-confirmed caveats here as we find them (anything
unverified stays out until we've checked it).

1. 200-LIKE CAP -> RECENCY PILE-UP (volume-over-time is an artifact).
   Each user contributes only their most-recent likes in the window (<=200
   originally; some heavy users extended to 300-500 via the backfill run).
   For anyone who hit the cap, older likes are truncated, so captured like
   *volume* climbs steeply toward the present (the most recent week is ~30%
   of all rows). Do NOT read rising volume over calendar time as a real
   surge in activity. The day-of-week and hour-of-day *shape* is unaffected
   by the cap (verified): weekday > weekend and the overnight dip are genuine.

2. 120-DAY WINDOW, FROZEN CUTOFF (2026-01-22).
   Likes older than the cutoff are absent by construction.

3. PARTIAL WEEKS AT BOTH WINDOW EDGES.
   The first and last ISO weeks are incomplete. Week / day-of-week plots must
   restrict to whole Mon-Sun weeks (PLOT 10 does this). Non-week plots are fine.

4. POPULATION = ONE SEED'S FILTERED 2-HOP NEIGHBORHOOD, not Bluesky at large.
   Set A = the seed's followers + follows, dropping followers with >7,000
   followers and follows with >300 follows; Set B = followers of A. "Most
   popular" and the leaderboards reflect THIS neighborhood, not global Bluesky.

5. POPULARITY COUNTS ARE A ONE-TIME SNAPSHOT.
   Each post's like/repost/reply/quote counts were fetched once at enrichment
   time; the extension runs deliberately do NOT re-fetch existing posts. So
   like_count is the post's popularity when enriched, not "now" or at like-time.

6. COVERAGE GAPS (handled by the join below).
   A minority of liked posts are missing from posts.parquet (deleted / blocked
   / private) and a small fraction of users from users.parquet (deactivated).
   The inner join drops those, along with buggy posts (quote_count < 0,
   post_created_at < 2023).

7. TIMESTAMPS ARE UTC.
   The hour-of-day axis is UTC; the user base skews US/Europe, so the
   "overnight" trough is shifted from any single local time.

8. RE-LIKES.
   A few hundred (liker, post) pairs carry multiple timestamps (unlike then
   re-like). The load below dedups on (liker_did, post_uri).
"""

# %% Imports and data loading
import sys
from pathlib import Path

# Make the bsky_likes package importable regardless of the working directory
# (e.g. when running cell-by-cell in Spyder). Falls back to cwd if __file__
# is unavailable in the execution context.
try:
    _ROOT = Path(__file__).resolve().parent
except NameError:
    _ROOT = Path.cwd()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
from matplotlib.colors import LogNorm
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import pandas as pd
import polars as pl

from bsky_likes import config

import os
# When WEB_EXPORT=1, each plot cell also emits a title-suppressed PNG + bounds
# for the website, and per-handle lookups are written at the end. The export
# logic lives in export_web.py; plots.py only carries thin guarded hooks.
WEB_EXPORT = os.environ.get("WEB_EXPORT") == "1"
if WEB_EXPORT:
    import export_web as ew

PROJECT_DIR = config.PROJECT_DIR
PLOTS_DIR   = config.PLOTS_DIR

# Consistent canvas for EVERY web-exported plot, so they all frame identically and
# fill the site's wide plot stage instead of letterboxing at assorted aspects
# (was 9x7, 11x6.5, 10x9, 7x7, 12x7.5, 11x4.81...). ~2.2:1 matches the stage; the
# overlay stays aligned because export_web recomputes bounds from the axes.
WEB_FIGSIZE = (12.5, 5.7)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Visual style — clean modern look that screenshots well on Bluesky
plt.rcParams.update({
    "figure.facecolor":  "#0e1116",
    "axes.facecolor":    "#0e1116",
    "axes.edgecolor":    "#9aa4b1",
    "axes.labelcolor":   "#e6edf3",
    "xtick.color":       "#9aa4b1",
    "ytick.color":       "#9aa4b1",
    "text.color":        "#e6edf3",
    "axes.titlecolor":   "#e6edf3",
    "axes.titlesize":    14,
    "axes.titleweight":  "bold",
    "axes.labelsize":    11,
    "font.family":       "DejaVu Sans",
    "figure.dpi":        110,
    "savefig.dpi":       180,
    "savefig.bbox":      "tight",
    "savefig.facecolor": "#0e1116",
    "axes.grid":         True,
    "grid.color":        "#1f2933",
    "grid.linewidth":    0.6,
})
BSKY_BLUE  = "#1d9bf0"
BSKY_PINK  = "#ec4899"
BSKY_GREEN = "#10b981"
BSKY_GOLD  = "#f59e0b"

# Shared style for the in-graph "quote" annotations. Each plot positions its
# own quote with ax.text(x, y, ..., transform=ax.transAxes, **QUOTE_STYLE);
# positions below are first guesses — tweak x/y/ha/va per plot freely.
QUOTE_STYLE = dict(
    fontfamily="serif",
    fontstyle="italic",
    fontsize=10,
    color="#e6edf3",
    alpha=0.75,
    path_effects=[pe.withStroke(linewidth=3, foreground="#0e1116")],
)

print("Loading data...")

POST_INT = pl.Int32
USER_INT = pl.Int32

likes = pl.scan_parquet(str(PROJECT_DIR / "likes" / "*.parquet"))

posts = (pl.scan_parquet(str(PROJECT_DIR / "posts.parquet"))
    .with_columns([
        pl.col("like_count").cast(POST_INT),
        pl.col("repost_count").cast(POST_INT),
        pl.col("reply_count").cast(POST_INT),
        pl.col("quote_count").cast(POST_INT),
    ]))

users = (pl.scan_parquet(str(PROJECT_DIR / "users.parquet"))
    .with_columns([
        pl.col("followers_count").cast(USER_INT),
        pl.col("follows_count").cast(USER_INT),
        pl.col("posts_count").cast(USER_INT),
    ]))

# Clean and join — drop deleted/buggy posts
posts_clean = (posts
    .filter(pl.col("quote_count") >= 0)
    .filter(pl.col("post_created_at") >= pl.datetime(2023, 1, 1, time_zone="UTC")))

joined = (likes
    .join(posts_clean, on="post_uri", how="inner"))
# NOTE: previously this chained .unique(subset=["liker_did","post_uri"]) to drop
# ~270 re-like dupes. But unique() over 74M string key-pairs (~10 GB of keys)
# triggers a native access-violation in polars 1.40 (both engines) — this is the
# OOM-class crash behind the earlier failures. It's dropped because those
# ~270 / 74M rows are invisible to every aggregate here, and for the event-based
# plots (engagement age, day/hour heatmap) an unlike->relike is a real, distinct
# like event that should count anyway.

# Keep joined lazy — materialize only the columns each plot needs. The full join
# is large, so every joined_lazy collection uses the streaming engine (bounded
# memory, identical results). posts_df/users_df are small enough to collect
# eagerly.
joined_lazy = joined
posts_df = posts_clean.collect()
users_df = users.collect()
n_joined = joined_lazy.select(pl.len()).collect(engine="streaming").item()
print(f"Joined frame: {n_joined:,} rows (lazy)")
print(f"Posts:        {len(posts_df):,} rows")
print(f"Users:        {len(users_df):,} rows")


# %% Build per-liker stats with 4 mainstreaminess scorers
# print("Computing per-liker stats...")

# # Global popularity-percentile mapping computed once on the cleaned posts.
# pop_arr = posts_df["like_count"].to_numpy()
# pop_sorted = np.sort(pop_arr)

# posts_with_pct = posts_df.with_columns(
#     pl.Series(
#         "popularity_percentile",
#         ((np.searchsorted(pop_sorted, pop_arr, side="right") / len(pop_sorted)) * 100)
#             .astype(np.float32),
#     )
# )

# # IDF weight: log(N / (1 + like_count)).  Rare posts get high weight.
# N_posts = len(posts_df)
# posts_with_pct = posts_with_pct.with_columns(
#     (np.log(N_posts / (1 + pl.col("like_count").cast(pl.Float32)))).alias("idf_weight")
# )

# joined_full = (joined_df
#     .join(posts_with_pct.select(["post_uri", "popularity_percentile", "idf_weight"]),
#           on="post_uri", how="inner"))

# per_liker = (joined_full
#     .group_by("liker_did")
#     .agg(
#         pl.len().alias("n_likes").cast(pl.UInt32),
#         pl.col("like_count").mean().alias("mean_post_likes").cast(pl.Float32),
#         pl.col("like_count").median().alias("median_post_likes").cast(pl.Float32),
#         pl.col("like_count").log1p().mean().alias("mean_log_popularity").cast(pl.Float32),
#         pl.col("popularity_percentile").mean().alias("mean_percentile").cast(pl.Float32),
#         pl.col("popularity_percentile").median().alias("median_percentile").cast(pl.Float32),
#         pl.col("idf_weight").mean().alias("mean_idf").cast(pl.Float32),
#     ))

# # Attach handles
# per_liker = per_liker.join(
#     users_df.select(["did", "handle", "followers_count", "follows_count"]),
#     left_on="liker_did", right_on="did", how="left"
# )

# print(per_liker.head())
# print(f"\nReliable subset (n_likes >= 20): "
#       f"{per_liker.filter(pl.col('n_likes') >= 20).height:,} users")

# # Save it for later use
# per_liker.write_parquet(PROJECT_DIR / "per_liker.parquet", compression="zstd")
# print("per_liker.parquet written")
per_liker = pl.read_parquet(PROJECT_DIR / "per_liker.parquet")


# %% PLOT 1 — The Hipster Index
# Each user is a dot.  X/Y = median/mean like-count of posts they like.
print("\n[2/10] The Hipster Index")
sub = (per_liker
       .filter(pl.col("n_likes") >= 20)
       .select(["median_post_likes", "mean_post_likes"])
       .to_pandas())

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
hb = ax.hexbin(sub["median_post_likes"] + 1,
               sub["mean_post_likes"] + 1,
               gridsize=60, xscale="log", yscale="log",
               cmap="magma", mincnt=1, norm=LogNorm())
cb = fig.colorbar(hb, ax=ax, label="users per hex (log)")
cb.outline.set_visible(False)

# Diagonal = "perfectly consistent taste"
lims = [1, 1e5]
ax.plot(lims, lims, "--", color=BSKY_BLUE, alpha=0.6, label="mean = median")
ax.set_xlim(lims); ax.set_ylim(lims)
ax.set_aspect("equal")

ax.set_xlabel("Median like-count of posts they like")
ax.set_ylabel("Mean like-count of posts they like")
fig.suptitle("What's the typical popularity of posts you like?",
             fontsize=14, fontweight="bold", x=0.446, y=0.98)
ax.set_title("Higher y = a few things you've liked blew up\n"
             "Bottom-left = you've literally liked nothing popular",
             fontsize=10, style="italic", color="gray", pad=10)
ax.legend(facecolor="#1f2933", edgecolor="none", loc="upper left")
plt.savefig(PLOTS_DIR / "02_hipster_index.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "typical-popularity", x_log=True, y_log=True)
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% PLOT 3 — The Power Curve (overlaid density)
print("\n[3/10] The Power Curve (overlaid per-user densities)")
from scipy.ndimage import gaussian_filter1d
from matplotlib.collections import LineCollection

# Sample 3,000 users with >= 50 likes
sample_dids = (per_liker
    .filter(pl.col("n_likes") >= 50)
    .select("liker_did")
    .sample(n=3_000, seed=7)["liker_did"])

# Pull their likes in one shot, compute log10(like_count + 1), and assign bins
bin_edges = np.linspace(0, 6, 301)   # 300 bins from log10=0 to log10=6
n_bins = len(bin_edges) - 1

sampled = (joined_lazy
    .join(sample_dids.to_frame().lazy(), on="liker_did", how="inner")
    .select([
        "liker_did",
        ((pl.col("like_count").cast(pl.Float64) + 1).log10()).alias("log_lc"),
    ])
    .filter((pl.col("log_lc") >= 0) & (pl.col("log_lc") < 6))
    .with_columns(
        ((pl.col("log_lc") / 6.0) * n_bins).cast(pl.Int32).alias("bin_idx")
    )
    .collect(engine="streaming"))

# Map liker_did -> small integer row index (0..n_users-1)
unique_dids = sampled.select("liker_did").unique().with_row_index("row_idx")
n_users = unique_dids.height

sampled = sampled.join(unique_dids, on="liker_did")
row_idx = sampled["row_idx"].to_numpy().astype(np.int32)
col_idx = sampled["bin_idx"].to_numpy()

# Build the (n_users x n_bins) histogram matrix with one vectorized scatter-add
hist = np.zeros((n_users, n_bins), dtype=np.float32)
np.add.at(hist, (row_idx, col_idx), 1.0)

# Drop users with fewer than 10 likes within the [0, 6) log range,
# or with no spread (all likes in one bin)
row_sums = hist.sum(axis=1)
nonzero_bins = (hist > 0).sum(axis=1)
keep = (row_sums >= 10) & (nonzero_bins >= 2)
hist = hist[keep]

# Normalize each row to a density (so users contribute equally)
bin_width = bin_edges[1] - bin_edges[0]
hist /= (hist.sum(axis=1, keepdims=True) * bin_width)

# Smooth each row -- gaussian_filter1d is vectorized along an axis
hist_smooth = gaussian_filter1d(hist, sigma=6, axis=1)

x_grid = 0.5 * (bin_edges[:-1] + bin_edges[1:])

# Build LineCollection segments without a Python loop
# Each segment is (n_bins, 2): x repeated, y per user
segments = np.stack(
    [np.broadcast_to(x_grid, hist_smooth.shape), hist_smooth],
    axis=-1
)  # shape (n_users, n_bins, 2)

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
lc = LineCollection(segments, colors=BSKY_BLUE, alpha=0.025, linewidths=0.8)
ax.add_collection(lc)

# Average user curve
stack = gaussian_filter1d(hist_smooth.mean(axis=0), sigma=2.7)
ax.plot(x_grid, stack, color=BSKY_PINK, linewidth=0.6,
        label="average user", zorder=10)

ax.set_xlim(0, 5)
ax.set_ylim(0, 1.5)
ax.set_xticks([0, 1, 2, 3, 4, 5])
ax.set_xticklabels(["0", "10", "100", "1k", "10k", "100k"])
ax.set_xlabel("Like-count of a liked post")
ax.set_yticks([])
ax.set_ylabel("")
ax.set_title("How popular are the posts we like?\n"
             "each blue line = one user's histogram of how popular their liked posts are")
ax.legend(facecolor="#1f2933", edgecolor="none")
# in-graph quote (guessed position: right side, over the empty tail)
ax.text(0.97, 0.62,
        '"All this has happened before,\nand all this will happen again."\n'
        '— the Hybrid, Battlestar Galactica',
        transform=ax.transAxes, ha="right", va="top", **QUOTE_STYLE)
plt.savefig(PLOTS_DIR / "03_power_curve.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "popularity-curve", x_log=False, y_log=False)
plt.show()
plt.close('all')  # free figure memory from the previous cell

print(f"  used {len(hist):,} users")


# %% PLOT 3 — Like-Repost Manifold
# 2D density of (avg likes per post, avg reposts per post) across all authors.
print("\n[5/10] Like-Repost Manifold (per author)")
author_eng = (posts_df
    .group_by("post_author_did")
    .agg(
        pl.col("like_count").mean().alias("avg_likes"),
        pl.col("repost_count").mean().alias("avg_reposts"),
        pl.len().alias("n_posts"),
    )
    .filter(pl.col("n_posts") >= 5)
    .filter((pl.col("avg_likes") >= 1) & (pl.col("avg_reposts") >= 1)))

xx = author_eng["avg_likes"].to_numpy()
yy = author_eng["avg_reposts"].to_numpy()
print(f"  authors with >=5 posts and avg >=1 of each: {len(xx):,}")

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
hb = ax.hexbin(xx, yy, gridsize=80, xscale="log", yscale="log",
               cmap="inferno", mincnt=1, norm=LogNorm())
cb = fig.colorbar(hb, ax=ax, label="authors per hex (log)")
cb.outline.set_visible(False)

ax.set_xlim(1, 1e4)
ax.set_ylim(1, 1e4)
ax.set_aspect("equal", adjustable="box")

# Reference: typical ratios
xs = np.array([1, 1e5])
ax.plot(xs, xs / 10, "--", color=BSKY_BLUE, alpha=0.5, label="10:1 likes:reposts")
ax.plot(xs, xs / 3,  "--", color=BSKY_PINK, alpha=0.6, label="3:1 likes:reposts")

ax.set_xlabel("Avg likes per post (log)")
ax.set_ylabel("Avg reposts per post (log)")
ax.set_title("Your like-to-repost ratios\n"
             "upper-left posts are reposted but not liked")
# legend moved to lower-right; quote takes the upper-left corner (left-aligned)
ax.legend(facecolor="#1f2933", edgecolor="none", loc="lower right")
ax.text(0.03, 0.97,
        '"The fundamental problem of communication is that of\n'
        'reproducing at one point either exactly or approximately\n'
        'a message selected at another point. Frequently the\n'
        'messages have meaning."\n— Claude Shannon (1948)',
        transform=ax.transAxes, ha="left", va="top",
        **{**QUOTE_STYLE, "fontsize": 9})
plt.savefig(PLOTS_DIR / "05b_like_repost_authors.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "like-repost", x_log=True, y_log=True)
plt.show()
plt.close('all')


# %% PLOT 4 — Mainstream vs Hipster Leaderboards
# Two side-by-side bar charts: most-mainstream and most-hipster users (n>=50).
print("\n[6/10] Mainstream vs Hipster Leaderboards")
sub = per_liker.filter(pl.col("n_likes") >= 50)
top_main = sub.sort("mean_log_popularity", descending=True).head(20).to_pandas()
top_hips = sub.sort("mean_log_popularity", descending=False).head(20).to_pandas()

# Left = most obscure (hipster), right = most viral (mainstream)
fig, axes = plt.subplots(1, 2, figsize=(15, 8))
for ax, df_, color, descr in [
    (axes[0], top_hips, BSKY_GREEN, "likes the most obscure posts"),
    (axes[1], top_main, BSKY_GOLD,  "likes the most viral posts"),
]:
    y = np.arange(len(df_))
    vals = df_["mean_log_popularity"].values
    ax.barh(y, vals, color=color, edgecolor="none")
    labels = [f"@{h}" if h else df_['liker_did'].iloc[i][:24] + "…"
              for i, h in enumerate(df_["handle"])]
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    # Scale x to THIS column's value range so the spread is visible (otherwise
    # every bar fills nearly the whole axis).
    lo, hi = float(vals.min()), float(vals.max())
    pad = (hi - lo) * 0.04 or 0.1
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_xlabel("Mean log(post likes + 1)")
    ax.set_title(descr)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

fig.suptitle("Who likes the most (and least) popular posts?",
             fontsize=15, fontweight="bold")
plt.savefig(PLOTS_DIR / "06_leaderboards.png")
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% PLOT 5 — Engagement Half-Life
# For every like, age_at_like = like_created_at - post_created_at.
print("\n[7/10] Engagement Half-Life")

# Bin edges in seconds, log-spaced from 1 minute to 1 year (59 bins).
edges = np.logspace(np.log10(60), np.log10(365*24*3600), 60)
_lo, _hi, _nb = np.log10(60), np.log10(365 * 24 * 3600), len(edges) - 1
_step = (_hi - _lo) / _nb

# Histogram the per-like age INSIDE polars: assign each age to a log-bin and
# count per bin, so only the 59 bin counts come back — never the 73M ages. This
# is identical to ax.hist(ages, bins=edges) but avoids materializing the full
# join output in memory (which OOM/segfaults at this data scale).
_binned = (joined_lazy
    .select(
        ((pl.col("like_created_at") - pl.col("post_created_at"))
         .dt.total_seconds()).alias("age")
    )
    .filter((pl.col("age") > 0) & (pl.col("age") < 365 * 24 * 3600))
    .with_columns(pl.col("age").log10().alias("la"))
    .filter((pl.col("la") >= _lo) & (pl.col("la") < _hi))
    .with_columns(((pl.col("la") - _lo) / _step).floor().cast(pl.Int32).alias("bi"))
    .group_by("bi").agg(pl.len().alias("n"))
    .collect(engine="streaming"))

counts = np.zeros(_nb)
for _r in _binned.iter_rows(named=True):
    if 0 <= _r["bi"] < _nb:
        counts[_r["bi"]] = _r["n"]

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
ax.stairs(counts, edges, fill=True, color=BSKY_BLUE, alpha=0.85)
ax.set_xscale("log")

# Reference vertical lines for human-readable times
markers = [
    (60,             "1 min"),
    (60*5,           "5 min"),
    (60*60,          "1 hr"),
    (60*60*24,       "1 day"),
    (60*60*24*7,     "1 week"),
    (60*60*24*30,    "1 month"),
    (60*60*24*365,   "1 year"),
]
for sec, label in markers:
    ax.axvline(sec, color="#9aa4b1", alpha=0.3, linewidth=0.8)
    ax.text(sec, ax.get_ylim()[1]*0.95, " " + label,
            rotation=90, va="top", fontsize=8, color="#9aa4b1")

ax.set_xlabel("Time between post creation and like")
ax.set_ylabel("Number of likes")
ax.set_title("Engagement Half-Life\n"
             "How fresh is a post when it gets liked?")
# in-graph quote — upper-right, dropped 20% from the top
ax.text(0.97, 0.75,
        '"In the future, everyone will be\nworld-famous for 15 minutes."\n'
        '— attributed to Andy Warhol\n(likely coined by Pontus Hultén, 1968)',
        transform=ax.transAxes, ha="right", va="top",
        **{**QUOTE_STYLE, "fontsize": 9})
plt.savefig(PLOTS_DIR / "07_engagement_half_life.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "half-life", x_log=True, y_log=False)
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% PLOT 6 — Activity vs Mainstreaminess
# Each user: their own popularity (X) vs popularity of posts they like (Y).
sub = (per_liker
       .filter(pl.col("n_likes") >= 20)
       .select(["followers_count", "mean_log_popularity"])
       .with_columns(pl.col("mean_log_popularity").exp().alias("avg_liked_post_likes"))
       .to_pandas())

x = sub["followers_count"].values + 1
y = sub["avg_liked_post_likes"].values

# ---- FACT CHECK: regress log(y) on log(x) ----
mask = (x > 1) & (y > 0)
slope, intercept = np.polyfit(np.log10(x[mask]), np.log10(y[mask]), 1)
corr = np.corrcoef(np.log10(x[mask]), np.log10(y[mask]))[0, 1]
print(f"Slope of log(avg liked popularity) vs log(followers): {slope:+.3f}")
print(f"Pearson correlation (log-log): {corr:+.3f}")
print("Interpretation: a slope of +1 = 'we like content as popular as we are';")
print("                a slope of  0 = 'taste is independent of own popularity';")
print("                a slope of -1 = 'the more popular we are, the more obscure our taste'")

# ---- PLOT ----
fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
hb = ax.hexbin(x, y, gridsize=60,
               xscale="log", yscale="log",
               cmap="magma", mincnt=2, norm=LogNorm())
cb = fig.colorbar(hb, ax=ax, label="users per hex")
cb.outline.set_visible(False)

lims = [1, 1e6]
ax.plot(lims, lims, "--", color="#1d9bf0", alpha=0.5, linewidth=1)
ax.set_xlim(lims); ax.set_ylim(lims)
ax.set_aspect("equal", adjustable="box")

# Fancy annotations
fancy_kwargs = dict(
    fontfamily="serif",
    fontstyle="italic",
    fontsize=13,
    color="#e6edf3",
    alpha=0.60,
    path_effects=[pe.withStroke(linewidth=3, foreground="#0e1116")],
)
ax.text(20, 6e3, "consuming\nabove your level",
        ha="center", va="center", **fancy_kwargs)
ax.text(6e3, 20, "consuming\nbelow your level",
        ha="center", va="center", **fancy_kwargs)

ax.set_xlabel("Your follower count")
ax.set_ylabel("Avg likes on the posts you like")
ax.set_title("Bluesky users are so kind <3\n"
             "the more popular we are\nthe less popular the content we like",
             fontsize=12)
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "activity", x_log=True, y_log=True)
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% PLOT 7 — Punching Above Their Weight
# For top authors: scatter of follower_count vs likes-per-post.
print("\n[9/10] Punching Above Their Weight")

# Compute author_stats once -- reused by 9 and 9.5
author_stats = (posts_df
    .group_by("post_author_did")
    .agg(pl.col("like_count").sum().alias("total_likes"),
         pl.len().alias("n_posts"))
    .filter(pl.col("n_posts") >= 5)
    .join(users_df.select(["did", "handle", "followers_count"]),
          left_on="post_author_did", right_on="did", how="inner"))

author_df_full = author_stats.with_columns(
    (pl.col("total_likes") / pl.col("n_posts")).alias("likes_per_post"),
    (pl.col("total_likes") / pl.col("n_posts") / (pl.col("followers_count") + 1))
        .alias("engagement_ratio")
).to_pandas()

author_df = author_df_full.nlargest(4000, "total_likes")

fig, ax = plt.subplots(figsize=(11, 7.5))
ax.scatter(author_df["followers_count"] + 1,
           author_df["likes_per_post"] + 1,
           s=8, c=author_df["engagement_ratio"], cmap="plasma",
           alpha=0.55, edgecolors="none",
           norm=LogNorm(vmin=author_df["engagement_ratio"].quantile(0.05)+1e-6,
                        vmax=author_df["engagement_ratio"].quantile(0.95)))
ax.set_xscale("log"); ax.set_yscale("log")

# Annotate the highest-engagement-ratio outliers
outliers = author_df.nlargest(8, "engagement_ratio")
for _, r in outliers.iterrows():
    label = f"@{r['handle']}" if r['handle'] else "?"
    ax.annotate(label,
                (r["followers_count"]+1, r["likes_per_post"]+1),
                fontsize=8, color=BSKY_GOLD, alpha=0.9,
                xytext=(4, 4), textcoords="offset points")

ax.set_xlim(1e3, 10**6.5)
ax.set_ylim(10**1.3, None)

cb = fig.colorbar(ax.collections[0], ax=ax, label="engagement ratio (log)")
cb.outline.set_visible(False)
ax.set_xlabel("Follower count")
ax.set_ylabel("Avg likes per post")
# NOTE: per plot_titles.md the Ratatouille quote now lives on PLOT 9.5 only.
# Plot 9 is the plain base scatter; this base title is a guess pending feedback.
ax.set_title("Top 4,000 liked accounts")
plt.savefig(PLOTS_DIR / "09_engagement_ratio.png")
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% PLOT 7.5 — Highlight a custom set of users (gold)
# (reuses author_df from previous)
HIGHLIGHT_HANDLES = {
    "jcsalterego.bsky.social",
    "cee.wtf",
    "avikdey.bsky.social",
    "hankgreen.bsky.social",
    "ceej.online",
    "jefferyharrell.bsky.social",
    "invert.bsky.social",
    "juniorhoncho.bsky.social",
    "lastnpcalex.agency",
    "aly.codes",
    "segyges.bsky.social",
    "moultano.bsky.social",
    "seanmcarroll.bsky.social",
    "sincerely.cam",
    "searyanc.dev",
    "jdp.extropian.net",
    "timkellogg.me",
    "gracekind.net",
    "contrapoints.bsky.social",
    "3blue1brown.com",
    "standupmaths.bsky.social",
    "hern.bsky.social",
    "10x.bsky.social",
    "zswitten.bsky.social",
    "dave.9000ish.uk",
    "phillipcarter.dev",
    "tszzl.bsky.social",
}

# Pre-baked gold highlights are OFF for the web build: the site now lights up
# "15 random accounts you follow" dynamically (client-side) instead. Flip to
# True to bake the static gold rings/labels back into the PNG.
BAKE_HIGHLIGHTS = False
_HL = HIGHLIGHT_HANDLES if BAKE_HIGHLIGHTS else set()

top4000 = author_df_full.nlargest(4000, "total_likes")

# Make sure all highlighted users are in the plotted set, even if outside top 4000
highlighted = author_df_full[author_df_full["handle"].isin(_HL)]
missing = highlighted[~highlighted["handle"].isin(top4000["handle"].values)]
if len(missing) > 0:
    top4000 = pd.concat([top4000, missing], ignore_index=True)
author_df = top4000

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
ax.scatter(author_df["followers_count"] + 1,
           author_df["likes_per_post"] + 1,
           s=8, c=author_df["engagement_ratio"], cmap="plasma",
           alpha=0.55, edgecolors="none",
           norm=LogNorm(vmin=author_df["engagement_ratio"].quantile(0.05)+1e-6,
                        vmax=author_df["engagement_ratio"].quantile(0.95)))
ax.set_xscale("log"); ax.set_yscale("log")

# Highlight: gold outline rings for all selected users (off by default now)
highlight_rows = author_df[author_df["handle"].isin(_HL)]
found_handles = set(highlight_rows["handle"].values)
missing_handles = _HL - found_handles
if missing_handles:
    print(f"WARNING: not found in author_df_full ({len(missing_handles)}):")
    for h in sorted(missing_handles):
        print(f"  {h}")

hx = highlight_rows["followers_count"].values + 1
hy = highlight_rows["likes_per_post"].values + 1
ax.scatter(hx, hy,
           s=70,
           c=highlight_rows["engagement_ratio"].values,
           cmap="plasma",
           norm=LogNorm(vmin=author_df["engagement_ratio"].quantile(0.05)+1e-6,
                        vmax=author_df["engagement_ratio"].quantile(0.95)),
           alpha=1.0,
           edgecolors=BSKY_GOLD,
           linewidths=1.,
           zorder=100)

# Labels for highlighted users with manual offset overrides
manual_offsets = {
    "standupmaths.bsky.social": (6, 8),
    "gracekind.net":              (0, 12),
    "jefferyharrell.bsky.social": (-46, 20),
    "aly.codes": (-28, 36),
    "jdp.extropian.net": (3, -4),
}
DEFAULT_OFFSET = (6, 4)

for _, r in highlight_rows.iterrows():
    handle = r["handle"]
    offset = manual_offsets.get(handle, DEFAULT_OFFSET)
    has_arrow = handle in manual_offsets
    ax.annotate(
        f"@{handle}",
        (r["followers_count"] + 1, r["likes_per_post"] + 1),
        fontsize=8,
        color=BSKY_GOLD,
        alpha=0.9,
        xytext=offset,
        textcoords="offset points",
        zorder=12,
        arrowprops=(dict(arrowstyle="-", color=BSKY_GOLD, alpha=0.4, lw=0.5)
                    if has_arrow else None),
    )

ax.set_xlim(1e2, 10**6.5)   # followers from 10^2
ax.set_ylim(1, None)        # avg likes/post from 10^0

cb = fig.colorbar(ax.collections[0], ax=ax, label="engagement ratio (log)")
cb.outline.set_visible(False)
ax.set_xlabel("Follower count")
ax.set_ylabel("Avg likes per post")
_extra = f" (+ {len(found_handles)} highlighted)" if found_handles else ""
ax.set_title(f"Top 4,000 liked accounts{_extra}", fontsize=18)
ax.text(0.02, 0.98,
        '"Anyone can cook." - Ratatouille',
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10, color="#9aa4b1", alpha=0.9,
        bbox=dict(facecolor="#0e1116", edgecolor="none", alpha=0.7, pad=4))

plt.savefig(PLOTS_DIR / "09_5_highlights.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "punching", x_log=True, y_log=True)
plt.show()
plt.close('all')


# %% PLOT 8 — When Bluesky Wakes Up
# Day-of-week × hour-of-day heatmap of like activity.
# Per-user whole-week trim: for EACH user, keep only likes that fall within
# complete Mon–Sun weeks of their own captured span (first Monday on/after their
# oldest like, last Sunday on/before their newest like). This balances every
# user's day-of-week contribution and removes the capture-window edge skew
# (see limitations #1/#3) without discarding heavy users the way a global trim
# or an uncapped-only subsample would.
print("\n[10/10] When Bluesky Wakes Up")

_bounds = (joined_lazy
    .group_by("liker_did")
    .agg([pl.col("like_created_at").min().alias("mn"),
          pl.col("like_created_at").max().alias("mx")])
    .with_columns([
        # first Monday 00:00 on/after the user's oldest like
        (pl.col("mn").dt.truncate("1d")
         + pl.duration(days=(8 - pl.col("mn").dt.weekday()) % 7)).alias("lo"),
        # 00:00 of the day AFTER the last Sunday on/before the user's newest like
        (pl.col("mx").dt.truncate("1d")
         - pl.duration(days=pl.col("mx").dt.weekday() % 7)
         + pl.duration(days=1)).alias("hi"),
    ])
    .select(["liker_did", "lo", "hi"]))

times = (joined_lazy
    .join(_bounds, on="liker_did", how="inner")
    .filter((pl.col("like_created_at") >= pl.col("lo"))
            & (pl.col("like_created_at") <  pl.col("hi")))
    .with_columns([
        pl.col("like_created_at").dt.weekday().alias("dow"),
        pl.col("like_created_at").dt.hour().alias("hour"),
    ])
    .group_by(["dow", "hour"])
    .agg(pl.len().alias("n"))
    .sort(["dow", "hour"])
    .collect(engine="streaming"))

n_heat = int(times["n"].sum())
print(f"  per-user whole-week trim: {n_heat:,} likes")

mat = np.zeros((7, 24))
for row in times.iter_rows(named=True):
    mat[row["dow"]-1, row["hour"]] = row["n"]

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
im = ax.imshow(mat, aspect="auto", cmap="magma", interpolation="nearest")
ax.set_yticks(range(7))
ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
ax.set_xticks(range(0, 24, 2))
ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 2)])
ax.set_xlabel("Hour of day (UTC)")
ax.set_title("When Bluesky Wakes Up", loc="left", fontsize=16)
# Quote OUTSIDE the axes, in the top margin to the right of the title.
# Shrink the axes' top so the heatmap shifts down and leaves room.
fig.subplots_adjust(top=0.78)
fig.text(0.86, 0.88,
         '"Rise and shine, Mr. Freeman. Rise and... shine."\n— the G-Man, Half-Life 2',
         ha="right", va="top", **QUOTE_STYLE)
cb = fig.colorbar(im, ax=ax, label="likes")
cb.outline.set_visible(False)
plt.savefig(PLOTS_DIR / "10_heatmap.png")
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "wakes-up", x_log=False, y_log=False)
plt.show()
plt.close('all')  # free figure memory from the previous cell

print(f"\nAll plots saved to {PLOTS_DIR}")


# %% PLOT 9 — The Long Tail (Bluesky's power law)
likes_desc = posts_df["like_count"].sort(descending=True).to_numpy()
total = int(likes_desc.sum())
n = len(likes_desc)
print(f"Posts:          {n:,}")
print(f"Total likes:    {total:,}")
print(f"Top 0.1%:       {likes_desc[:n//1000].sum() / total:.1%} of likes")
print(f"Top 1%:         {likes_desc[:n//100].sum()  / total:.1%} of likes")
print(f"Top 10%:        {likes_desc[:n//10].sum()   / total:.1%} of likes")
print(f"Bottom 50%:     {likes_desc[n//2:].sum()    / total:.1%} of likes")
print(f"Median post:    {likes_desc[n//2]} likes")
print(f"Posts w/ 0 likes:  {(likes_desc == 0).sum():,}  ({(likes_desc == 0).mean():.1%})")
print(f"Posts w/ ≤1 likes: {(likes_desc <= 1).sum():,} ({(likes_desc <= 1).mean():.1%})")
print(f"Top post:       {int(likes_desc[0]):,} likes")
print(f"Top post vs sum of ranks 1000-10000: {likes_desc[0] / likes_desc[1000:10000].sum():.3f}")

# Ascending for Lorenz / Gini (Brown formula expects ascending)
likes_asc = likes_desc[::-1].astype(np.float64)
cum = likes_asc.cumsum()
gini = (n + 1 - 2 * (cum.sum() / cum[-1])) / n
print(f"Gini coefficient: {gini:.3f}  (US wealth ≈ 0.85)")

x_bluesky = np.arange(1, n + 1) / n
y_bluesky = cum / cum[-1]

# Reference curves: parametric Lorenz approximation L(p) = p^k where
# k controls inequality. Higher k = more unequal. These are illustrative,
# not exact survey data — useful for visual intuition only.
p = np.linspace(0, 1, 500)
def lorenz_powerlaw(p, gini):
    # closed-form for L(p) = p^a, where gini = (a-1)/(a+1) -> a = (1+gini)/(1-gini)
    a = (1 + gini) / (1 - gini)
    return p ** a

fig, ax = plt.subplots(figsize=WEB_FIGSIZE)
ax.plot([0, 1], [0, 1], "--", color="#9aa4b1", alpha=0.5, label="perfect equality")
ax.plot(p, lorenz_powerlaw(p, 0.48), color="#10b981", linewidth=2,
        label="US income (Gini ≈ 0.48)")
ax.plot(p, lorenz_powerlaw(p, 0.85), color="#f59e0b", linewidth=2,
        label="US wealth (Gini ≈ 0.85)")
ax.plot(x_bluesky, y_bluesky, color="#1d9bf0", linewidth=3,
        label=f"Bluesky likes (Gini = {gini:.3f})", zorder=10)

ax.set_xlabel("Bottom X% of posts (least-liked → most-liked)")
ax.set_ylabel("Share of total likes they receive")
ax.set_title("How unequal is attention on Bluesky?")
ax.set_aspect("equal", adjustable="box")
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.legend(facecolor="#1f2933", edgecolor="none", loc="upper left")
# in-graph quote — middle-left
ax.text(0.03, 0.5,
        '"Greed, for lack of a better word, is good."\n— Gordon Gekko, Wall Street',
        transform=ax.transAxes, ha="left", va="center", **QUOTE_STYLE)
if WEB_EXPORT:
    ew.export_png_and_bounds(fig, ax, "long-tail", x_log=False, y_log=False)
plt.show()
plt.close('all')  # free figure memory from the previous cell


# %% WEB EXPORT — per-handle lookups (only when WEB_EXPORT=1)
if WEB_EXPORT:
    print("\n=== WEB LOOKUP EXPORT ===")
    ew.export_activity(per_liker)
    ew.export_typical_popularity(per_liker)
    ew.export_leaderboards(per_liker, n=50)
    ew.export_punching(author_df)              # Plot 9.5 plotted set (pandas)
    ew.export_like_repost(author_eng, users_df)
    print(f"Web lookups written -> {ew.SITE_PLOTS}")
    # Deferred (design needed): popularity-curve histograms, half-life.
