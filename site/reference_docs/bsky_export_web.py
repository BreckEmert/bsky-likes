# -*- coding: utf-8 -*-
"""
bsky_export_web.py

Bridge between the matplotlib analysis (bsky_analyze.py) and the interactive
website.  For each plot, emits:
  - <plot>.png            transparent background, title/subtitle suppressed,
                          in-plot quotes KEPT, tight axes
  - <plot>.bounds.json    data extent + log flags + pixel rect of the axes
  - lookup files          per-plot, mapping handle -> data coords
                          (binary for large, JSON for small)

This module is reference scaffolding.  The exact column names / metric
computations should be wired to match bsky_analyze.py.  Functions are written
to be called from inside (or just after) the corresponding plot cell, where the
figure `fig` and axes `ax` still exist, OR standalone from per_liker.parquet.

ASCII-only stdout (Windows cp1252 safe).
"""

import json
import struct
from pathlib import Path

import numpy as np
import polars as pl
import matplotlib.pyplot as plt

OUT_DIR = Path(r"F:/GitHub/bsky-likes-analysis/site/public/plots")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# PNG + BOUNDS EXPORT
# ===========================================================================
def export_png_and_bounds(fig, ax, plot_id, x_log=False, y_log=False,
                          suppress_title=True, dpi=200):
    """Save a transparent PNG and a bounds.json describing the axes pixel rect.

    Call this AFTER drawing the plot (quotes/annotations included) but the
    function will strip the title/subtitle so they can be rendered as HTML.

    The bounds.json plotArea is the pixel rectangle (in the saved PNG's pixel
    space) where data lives, so the website can map data coords -> pixels.
    """
    if suppress_title:
        ax.set_title("")
        if fig._suptitle is not None:
            fig._suptitle.set_text("")

    # Data limits (in data units, pre-log if the axis is log-scaled matplotlib
    # returns the raw data values, which is what we want to compare against).
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()

    # Figure pixel size
    fig.canvas.draw()  # ensure layout is finalized
    fig_w_px = fig.get_figwidth() * dpi
    fig_h_px = fig.get_figheight() * dpi

    # Axes position in figure fraction -> pixels.  Note matplotlib y-fraction
    # is bottom-up; PNG pixel y is top-down, so flip.
    pos = ax.get_position()  # Bbox in figure fraction (x0,y0,x1,y1)
    left_px = pos.x0 * fig_w_px
    right_px = pos.x1 * fig_w_px
    top_px = (1.0 - pos.y1) * fig_h_px
    bottom_px = (1.0 - pos.y0) * fig_h_px

    png_path = OUT_DIR / f"{plot_id}.png"
    fig.savefig(png_path, dpi=dpi, transparent=True,
                bbox_inches=None, pad_inches=0)
    # IMPORTANT: do NOT use bbox_inches='tight' here -- it changes the figure
    # extent and would invalidate the pixel math above.  Keep the full figure.

    bounds = {
        "xMin": float(x_min), "xMax": float(x_max),
        "yMin": float(y_min), "yMax": float(y_max),
        "xLog": bool(x_log), "yLog": bool(y_log),
        "imgWidth": int(round(fig_w_px)), "imgHeight": int(round(fig_h_px)),
        "plotArea": {
            "left": float(left_px), "top": float(top_px),
            "right": float(right_px), "bottom": float(bottom_px),
        },
    }
    bounds_path = OUT_DIR / f"{plot_id}.bounds.json"
    bounds_path.write_text(json.dumps(bounds, indent=2))
    print(f"[OK] {plot_id}: png ({png_path.stat().st_size/1e3:.0f} KB) + bounds")
    return bounds


# ===========================================================================
# BINARY LOOKUP WRITERS (Theo-format)
# ===========================================================================
def write_handles_bin(handles, path):
    """handles: list[str].  Format: uint32 count, (count+1) uint32 offsets,
       then concatenated UTF-8 bytes."""
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
    print(f"[OK] {Path(path).name}: {n:,} handles ({Path(path).stat().st_size/1e6:.1f} MB)")


def write_positions_bin(xy, path):
    """xy: (N,2) float array -> flat Float32Array [x0,y0,x1,y1,...]."""
    arr = np.asarray(xy, dtype=np.float32).reshape(-1)
    arr.tofile(path)
    print(f"[OK] {Path(path).name}: {len(arr)//2:,} positions ({Path(path).stat().st_size/1e6:.1f} MB)")


def write_histograms_bin(hist_matrix, path):
    """hist_matrix: (N, B) float array, one B-length histogram per user.
       Flattened row-major Float32.  The website needs B (write into bounds or a
       sidecar)."""
    arr = np.asarray(hist_matrix, dtype=np.float32).reshape(-1)
    arr.tofile(path)
    print(f"[OK] {Path(path).name}: {hist_matrix.shape[0]:,} histograms "
          f"x {hist_matrix.shape[1]} bins ({Path(path).stat().st_size/1e6:.1f} MB)")


def write_json_lookup(mapping, path):
    """mapping: dict handle -> list[float] (or list of row dicts).  Small plots."""
    Path(path).write_text(json.dumps(mapping))
    print(f"[OK] {Path(path).name}: {len(mapping):,} entries ({Path(path).stat().st_size/1e3:.0f} KB)")


# ===========================================================================
# PER-PLOT EXPORTERS
# These assume per_liker.parquet has the metric columns.  Adjust column names
# to match bsky_analyze.py.
# ===========================================================================
def load_per_liker(project_dir=r"F:/GitHub/bsky-likes-analysis/bsky_data"):
    return pl.read_parquet(Path(project_dir) / "per_liker.parquet")


def export_activity(per_liker):
    """Plot 8: x = followers_count (log), y = exp(mean_log_popularity) (log).
       440k users, sorted by followers desc for LOD.  Binary."""
    df = (per_liker
          .filter(pl.col("followers_count") > 0)
          .filter(pl.col("mean_log_popularity").is_not_null())
          .with_columns(pl.col("mean_log_popularity").exp().alias("avg_pop"))
          .sort("followers_count", descending=True))
    handles = df["handle"].to_list()
    xy = np.column_stack([
        df["followers_count"].to_numpy().astype(np.float32),
        df["avg_pop"].to_numpy().astype(np.float32),
    ])
    write_handles_bin(handles, OUT_DIR / "activity.handles.bin")
    write_positions_bin(xy, OUT_DIR / "activity.positions.bin")


def export_typical_popularity(per_liker):
    """Plot 2: x = mean_post_likes, y = median_post_likes.  Binary (440k)."""
    df = per_liker.filter(
        pl.col("mean_post_likes").is_not_null()
        & pl.col("median_post_likes").is_not_null())
    handles = df["handle"].to_list()
    xy = np.column_stack([
        df["mean_post_likes"].to_numpy().astype(np.float32),
        df["median_post_likes"].to_numpy().astype(np.float32),
    ])
    write_handles_bin(handles, OUT_DIR / "typical-popularity.handles.bin")
    write_positions_bin(xy, OUT_DIR / "typical-popularity.positions.bin")


def export_punching(author_df):
    """Plot 9: ~4k authors.  x = followers_count, y = likes_per_post.  JSON.
       author_df expected columns: handle, followers_count, likes_per_post."""
    mapping = {}
    for r in author_df.iter_rows(named=True):
        if r.get("handle"):
            mapping[r["handle"].lower()] = [
                float(r["followers_count"]), float(r["likes_per_post"])]
    write_json_lookup(mapping, OUT_DIR / "punching.lookup.json")


def export_like_repost(author_df):
    """Plot 5: per-author like:repost ratios.  JSON.
       author_df expected columns: handle, like_ratio, repost_ratio."""
    mapping = {}
    for r in author_df.iter_rows(named=True):
        if r.get("handle"):
            mapping[r["handle"].lower()] = [
                float(r["like_ratio"]), float(r["repost_ratio"])]
    write_json_lookup(mapping, OUT_DIR / "like-repost.lookup.json")


def export_leaderboards(per_liker, n=50):
    """Plot 6: top-n and bottom-n by mainstreaminess.  JSON ordered rows."""
    metric = "mean_log_popularity"
    df = per_liker.filter(pl.col(metric).is_not_null()).sort(metric)
    bottom = df.head(n).select(["handle", metric])
    top = df.tail(n).reverse().select(["handle", metric])

    def rows(frame):
        return [{"handle": h, "value": float(v)}
                for h, v in zip(frame["handle"].to_list(),
                                frame[metric].to_list())]

    payload = {"mostMainstream": rows(top), "mostObscure": rows(bottom),
               "metric": metric, "total": df.height}
    write_json_lookup(payload, OUT_DIR / "leaderboards.json")


def export_popularity_curve(per_liker, joined_full, bins=60,
                            x_min_log=0.0, x_max_log=6.0):
    """Plot 3: per-user histogram of log10(liked-post like_count).
       Binary histograms aligned to the same bin grid the PNG uses.
       joined_full: likes joined to posts with a 'like_count' column.
       Only users with >= 50 likes (matching the plot's filter)."""
    eligible = (per_liker.filter(pl.col("n_likes") >= 50)
                .select("liker_did", "handle"))
    elig_dids = eligible["liker_did"].to_list()
    elig_handles = eligible["handle"].to_list()

    # Group like_counts per eligible user
    grouped = (joined_full
               .filter(pl.col("liker_did").is_in(elig_dids))
               .group_by("liker_did")
               .agg(pl.col("like_count")))

    # Map did -> list for ordering with handles
    did_to_likes = dict(zip(grouped["liker_did"].to_list(),
                            grouped["like_count"].to_list()))

    edges = np.linspace(x_min_log, x_max_log, bins + 1)
    handles_out = []
    hist_rows = []
    for did, handle in zip(elig_dids, elig_handles):
        likes = did_to_likes.get(did)
        if not likes:
            continue
        logv = np.log10(np.asarray(likes, dtype=np.float64) + 1.0)
        h, _ = np.histogram(logv, bins=edges, density=True)
        handles_out.append(handle)
        hist_rows.append(h.astype(np.float32))

    if hist_rows:
        mat = np.vstack(hist_rows)
        write_handles_bin(handles_out, OUT_DIR / "popularity-curve.handles.bin")
        write_histograms_bin(mat, OUT_DIR / "popularity-curve.histograms.bin")
        # sidecar describing the bin grid for the website
        (OUT_DIR / "popularity-curve.histmeta.json").write_text(json.dumps({
            "bins": bins, "xMinLog": x_min_log, "xMaxLog": x_max_log,
        }))
        print(f"[OK] popularity-curve: {len(handles_out):,} user histograms")


# ===========================================================================
# USAGE NOTES (read me)
# ===========================================================================
USAGE = """
HOW TO USE (wire into bsky_analyze.py):

For each plot cell, after drawing (with the quote, WITHOUT relying on the
title for layout):

    bounds = export_png_and_bounds(fig, ax, "activity", x_log=True, y_log=True)

Then emit that plot's lookup once (from per_liker or the author frame):

    pl_df = load_per_liker()
    export_activity(pl_df)
    export_typical_popularity(pl_df)
    export_leaderboards(pl_df)
    export_punching(author_df)        # author_df from the punching cell
    export_like_repost(author_df5)    # author_df from the like-repost cell
    export_popularity_curve(pl_df, joined_full)

Static, non-searchable plots (long-tail, wakes-up) only need:

    export_png_and_bounds(fig, ax, "long-tail", x_log=True, y_log=True)
    export_png_and_bounds(fig, ax, "wakes-up")   # heatmap, linear

CAVEATS:
- Column names above are guesses; align them to per_liker.parquet's real schema.
- export_png_and_bounds must NOT be used with bbox_inches='tight' (breaks the
  pixel math).  If you need tighter margins, set them via subplots_adjust and
  the get_position() math stays correct.
- For deck.gl plots the website maps WORLD coords (data units) onto plotArea;
  for log axes it applies log10 first, so xMin/xMax in bounds.json are RAW data
  values and xLog=true tells the site to log them.  Keep that contract.
- Re-run after any data refresh (e.g. after regenerating per_liker.parquet).
"""

if __name__ == "__main__":
    print(USAGE)
