# -*- coding: utf-8 -*-
"""
export_web.py

Bridge between plots.py (matplotlib) and the website. Reconciled to the real
per_liker schema and the current plot cells (replaces the reference scaffold in
site/reference_docs/bsky_export_web.py).

For each plot it can emit:
  - <plot>.png          background layer; title/subtitle suppressed (rendered as
                        HTML on the site), in-plot QUOTES kept; transparent fig
  - <plot>.bounds.json  data extent + log flags + the axes' pixel rect, so the
                        site maps data coords -> pixels
  - lookup files        handle -> data coords (binary for the 440k-user plots,
                        JSON for the small ones)

Driven from plots.py when the env var WEB_EXPORT=1 is set:
  - export_png_and_bounds(fig, ax, id, ...) is called per plot cell
  - the lookup exporters run once at the end from the in-scope frames

IMPORTANT axis conventions (must match plots.py so highlights land correctly):
  the plots offset values by +1 before plotting on log axes; the lookups below
  bake in the SAME offset. See each exporter.

ASCII-only stdout (Windows cp1252 safe).
"""
import json
import struct
from pathlib import Path

import numpy as np
import polars as pl

from bsky_likes import config

SITE_PLOTS = config.PROJECT_DIR.parent / "site" / "public" / "plots"
SITE_PLOTS.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# PNG + BOUNDS
# ===========================================================================
def export_png_and_bounds(fig, ax, plot_id, x_log=False, y_log=False, dpi=200):
    """Save a transparent PNG (title/subtitle blanked, quotes kept) and a
    bounds.json giving the axes' pixel rect in the saved PNG's pixel space.

    The figure background is transparent; the axes keep their dark facecolor,
    which matches the site's dark theme. Must NOT use bbox_inches='tight'
    (it would change the figure extent and invalidate the pixel math) -- we
    pass bbox_inches=None explicitly to override the global 'tight' rcParam.
    """
    # Suppress title + subtitle (rendered as HTML on the site). Both the axes
    # title (used by most cells, sometimes carrying the subtitle as line 2) and
    # any figure suptitle are blanked. In-plot quotes/annotations are ax.text/
    # fig.text and are left untouched.
    ax.set_title("")
    if getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.set_text("")

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()

    fig.canvas.draw()  # finalize layout before reading positions
    fig_w_px = fig.get_figwidth() * dpi
    fig_h_px = fig.get_figheight() * dpi

    pos = ax.get_position()  # figure-fraction bbox; y is bottom-up
    left_px = pos.x0 * fig_w_px
    right_px = pos.x1 * fig_w_px
    top_px = (1.0 - pos.y1) * fig_h_px      # flip to top-down PNG pixels
    bottom_px = (1.0 - pos.y0) * fig_h_px

    png_path = SITE_PLOTS / f"{plot_id}.png"
    fig.savefig(png_path, dpi=dpi, transparent=True,
                bbox_inches=None, pad_inches=0)

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
    (SITE_PLOTS / f"{plot_id}.bounds.json").write_text(json.dumps(bounds, indent=2))
    print(f"[OK] {plot_id}: png ({png_path.stat().st_size/1e3:.0f} KB) + bounds")
    return bounds


# ===========================================================================
# BINARY / JSON LOOKUP WRITERS  (Theo-format binaries)
# ===========================================================================
def write_handles_bin(handles, path):
    """uint32 count, (count+1) uint32 offsets, then concatenated UTF-8 bytes."""
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
    print(f"[OK] {Path(path).name}: {n:,} handles "
          f"({Path(path).stat().st_size/1e6:.1f} MB)")


def write_positions_bin(xy, path):
    """xy: (N,2) -> flat Float32 [x0,y0,x1,y1,...]."""
    arr = np.asarray(xy, dtype=np.float32).reshape(-1)
    arr.tofile(path)
    print(f"[OK] {Path(path).name}: {len(arr)//2:,} positions "
          f"({Path(path).stat().st_size/1e6:.1f} MB)")


def write_json_lookup(mapping, path):
    Path(path).write_text(json.dumps(mapping))
    print(f"[OK] {Path(path).name}: {len(mapping):,} entries "
          f"({Path(path).stat().st_size/1e3:.0f} KB)")


# ===========================================================================
# PER-PLOT LOOKUP EXPORTERS  (reconciled to the real schema + plot axes)
# ===========================================================================
def export_activity(per_liker):
    """Plot 8 / 'activity'. Axes: x = followers_count + 1 (log),
    y = exp(mean_log_popularity) (log). 440k users, sorted by followers desc so
    the site can do level-of-detail. Binary."""
    df = (per_liker
          .filter(pl.col("mean_log_popularity").is_not_null()
                  & pl.col("handle").is_not_null())
          .with_columns([
              (pl.col("followers_count") + 1).cast(pl.Float32).alias("px"),
              pl.col("mean_log_popularity").exp().cast(pl.Float32).alias("py"),
          ])
          .sort("followers_count", descending=True))
    handles = df["handle"].to_list()
    xy = np.column_stack([df["px"].to_numpy(), df["py"].to_numpy()])
    write_handles_bin(handles, SITE_PLOTS / "activity.handles.bin")
    write_positions_bin(xy, SITE_PLOTS / "activity.positions.bin")


def export_typical_popularity(per_liker):
    """Plot 2 / 'typical-popularity'. Axes: x = median_post_likes + 1 (log),
    y = mean_post_likes + 1 (log). Binary (~440k)."""
    df = per_liker.filter(
        pl.col("mean_post_likes").is_not_null()
        & pl.col("median_post_likes").is_not_null()
        & pl.col("handle").is_not_null())
    handles = df["handle"].to_list()
    xy = np.column_stack([
        (df["median_post_likes"].to_numpy() + 1.0).astype(np.float32),
        (df["mean_post_likes"].to_numpy() + 1.0).astype(np.float32),
    ])
    write_handles_bin(handles, SITE_PLOTS / "typical-popularity.handles.bin")
    write_positions_bin(xy, SITE_PLOTS / "typical-popularity.positions.bin")


def export_leaderboards(per_liker, n=50):
    """Plot 6 / 'leaderboards'. Top-n and bottom-n by mean_log_popularity.
    JSON ordered rows; the site shows these and 'ranked #X of N' for others."""
    metric = "mean_log_popularity"
    df = (per_liker
          .filter(pl.col(metric).is_not_null() & pl.col("handle").is_not_null())
          .sort(metric))
    bottom = df.head(n).select(["handle", metric])
    top = df.tail(n).reverse().select(["handle", metric])

    def rows(frame):
        return [{"handle": h, "value": float(v)}
                for h, v in zip(frame["handle"].to_list(),
                                frame[metric].to_list())]

    payload = {"mostMainstream": rows(top), "mostObscure": rows(bottom),
               "metric": metric, "total": df.height}
    write_json_lookup(payload, SITE_PLOTS / "leaderboards.json")


def export_punching(author_df):
    """Plot 9.5 / 'punching'. Axes: x = followers_count + 1 (log),
    y = likes_per_post + 1 (log). `author_df` is the plotted set (top ~4k +
    highlighted), a pandas DataFrame with handle/followers_count/likes_per_post.
    JSON."""
    mapping = {}
    for _, r in author_df.iterrows():
        h = r.get("handle")
        if h:
            mapping[str(h).lower()] = [
                float(r["followers_count"]) + 1.0,
                float(r["likes_per_post"]) + 1.0,
            ]
    write_json_lookup(mapping, SITE_PLOTS / "punching.lookup.json")


def export_like_repost(author_eng, users_df):
    """Plot 5 / 'like-repost'. Axes: x = avg_likes (log), y = avg_reposts (log),
    no +1 (the plot filters avg >= 1). `author_eng` is the polars frame from the
    cell (post_author_did, avg_likes, avg_reposts); join users_df for handle.
    JSON."""
    joined = author_eng.join(
        users_df.select(["did", "handle"]),
        left_on="post_author_did", right_on="did", how="inner")
    mapping = {}
    for r in joined.iter_rows(named=True):
        h = r.get("handle")
        if h:
            mapping[h.lower()] = [float(r["avg_likes"]), float(r["avg_reposts"])]
    write_json_lookup(mapping, SITE_PLOTS / "like-repost.lookup.json")


# ===========================================================================
# DEFERRED (need design decisions — see notes in the handoff)
# ===========================================================================
#  - popularity-curve (svg-line): per-user histograms for all eligible users
#    would be 100+ MB. Needs fewer bins / quantization / a min-likes gate
#    before shipping. PNG + bounds are still exported; lookup is TODO.
#  - half-life: Plot 7 is an aggregate histogram with no per-entity (x,y), so
#    there is nothing to search/highlight. Marked non-searchable on the site.
