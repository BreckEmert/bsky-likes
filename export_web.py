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
# Squarish / slightly-portrait canvas for the MOBILE variant of every web plot.
# Wide desktop plots become much taller here so they fill a phone's vertical space
# instead of being a short strip; the site loads only the matching one per viewport.
MOBILE_FIG = (6.5, 7.0)


def export_png_and_bounds(fig, ax, plot_id, x_log=False, y_log=False, dpi=200):
    """Save a transparent PNG + bounds.json (axes' pixel rect) for the site.

    Emits TWO variants from the SAME drawn figure:
      {id}.png / {id}.bounds.json          -- desktop, at the cell's figsize
      {id}.mobile.png / {id}.mobile.bounds.json -- re-rendered at MOBILE_FIG
    The site picks one per viewport via <picture>, so a phone never downloads the
    desktop image (and vice-versa). The PNG MUST be the full, uncropped figure so
    its pixel size equals imgWidth/imgHeight; rcParams sets savefig.bbox='tight',
    which would crop it, so we force the full figure via rc_context at save time.
    """
    import matplotlib as mpl
    # Suppress title + subtitle (rendered as HTML on the site). In-plot quotes are
    # ax.text/fig.text and are left untouched.
    ax.set_title("")
    if getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.set_text("")

    def _save(suffix):
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        fig.canvas.draw()  # finalize layout before reading positions
        fig_w_px = fig.get_figwidth() * dpi
        fig_h_px = fig.get_figheight() * dpi
        pos = ax.get_position()  # figure-fraction bbox; y is bottom-up
        png_path = SITE_PLOTS / f"{plot_id}{suffix}.png"
        with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0}):
            fig.savefig(png_path, dpi=dpi, transparent=True)
        bounds = {
            "xMin": float(x_min), "xMax": float(x_max),
            "yMin": float(y_min), "yMax": float(y_max),
            "xLog": bool(x_log), "yLog": bool(y_log),
            "imgWidth": int(round(fig_w_px)), "imgHeight": int(round(fig_h_px)),
            "plotArea": {
                "left": float(pos.x0 * fig_w_px), "top": float((1.0 - pos.y1) * fig_h_px),
                "right": float(pos.x1 * fig_w_px), "bottom": float((1.0 - pos.y0) * fig_h_px),
            },
        }
        (SITE_PLOTS / f"{plot_id}{suffix}.bounds.json").write_text(json.dumps(bounds, indent=2))
        print(f"[OK] {plot_id}{suffix}: png ({png_path.stat().st_size/1e3:.0f} KB) + bounds")
        return bounds

    orig = fig.get_size_inches().copy()
    desktop = _save("")                # desktop, at the cell's figsize
    fig.set_size_inches(*MOBILE_FIG)
    _save(".mobile")                   # mobile, squarish portrait
    fig.set_size_inches(*orig)         # restore so the cell's plt.show() is unaffected
    return desktop


# ===========================================================================
# BINARY / JSON LOOKUP WRITERS  (Theo-format binaries)
# ===========================================================================
def write_handles_bin(handles, path):
    """uint32 count, (count+1) uint32 offsets, then concatenated UTF-8 bytes.

    The very common ".bsky.social" suffix is replaced with a 1-byte sentinel
    (0x01) to shrink the files ~40%; the client (src/lib/binary.ts expandHandle)
    restores it on decode."""
    def strip(h):
        return (h[:-12] + "\x01") if h.endswith(".bsky.social") else h
    enc = [strip(h).encode("utf-8") for h in handles]
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


def export_leaderboards(per_liker, n=50, min_likes=50):
    """Plot 6 / 'leaderboards'. Ranked by mean_log_popularity over users with
    >= min_likes likes (without that filter the extremes are degenerate: someone
    who liked a single viral/obscure post outranks everyone, and the values tie
    at the boundaries). Emits:
      leaderboards.json        top-n + bottom-n rows for the two columns
      leaderboards.handles.bin full ranked handles (desc), for search-any-user
      leaderboards.values.bin  parallel Float32 metric values
    so the site can search ANY eligible user and show 'ranked #X of N'."""
    metric = "mean_log_popularity"
    df = (per_liker
          .filter(pl.col(metric).is_not_null() & pl.col("handle").is_not_null()
                  & (pl.col("n_likes") >= min_likes))
          .sort(metric, descending=True))   # highest (most viral) first
    total = df.height
    top = df.head(n).select(["handle", metric])             # most viral
    bottom = df.tail(n).reverse().select(["handle", metric])  # most obscure, lowest first

    def rows(frame):
        return [{"handle": h, "value": float(v)}
                for h, v in zip(frame["handle"].to_list(),
                                frame[metric].to_list())]

    payload = {"mostMainstream": rows(top), "mostObscure": rows(bottom),
               "metric": metric, "total": total}
    write_json_lookup(payload, SITE_PLOTS / "leaderboards.json")

    # Full ranked lookup (sorted desc -> rank = index + 1) for search-any-user.
    handles = [h.lower() for h in df["handle"].to_list()]
    write_handles_bin(handles, SITE_PLOTS / "leaderboards.handles.bin")
    df[metric].to_numpy().astype(np.float32).tofile(SITE_PLOTS / "leaderboards.values.bin")
    print(f"[OK] leaderboards: {total:,} ranked users (n_likes>={min_likes})")


def export_punching(author_df):
    """Plot 9.5 / 'punching'. Axes: x = followers_count (log), y = likes_per_post
    (log) -- RAW, no +1, matching the hexbin; 0-value accounts land off the log
    axis. `author_df` is the plotted set, a pandas DataFrame with
    handle/followers_count/likes_per_post. Binary handles + positions."""
    df = author_df[author_df["handle"].notna()]
    handles = [str(h).lower() for h in df["handle"].tolist()]
    xy = np.column_stack([
        df["followers_count"].to_numpy().astype(np.float32),
        df["likes_per_post"].to_numpy().astype(np.float32),
    ])
    write_handles_bin(handles, SITE_PLOTS / "punching.handles.bin")
    write_positions_bin(xy, SITE_PLOTS / "punching.positions.bin")


def export_like_repost(author_eng, users_df):
    """Plot 5 / 'like-repost'. Axes: x = avg_likes (log), y = avg_reposts (log),
    no +1 (the plot filters avg >= 1). `author_eng` is the polars frame from the
    cell (post_author_did, avg_likes, avg_reposts); join users_df for handle.
    Binary (handles + positions) -- avoids a 14.5 MB JSON blob on the client."""
    joined = (author_eng
        .join(users_df.select(["did", "handle"]),
              left_on="post_author_did", right_on="did", how="inner")
        .filter(pl.col("handle").is_not_null())
        .with_columns(pl.col("handle").str.to_lowercase()))
    handles = joined["handle"].to_list()
    xy = np.column_stack([
        joined["avg_likes"].to_numpy().astype(np.float32),
        joined["avg_reposts"].to_numpy().astype(np.float32),
    ])
    write_handles_bin(handles, SITE_PLOTS / "like-repost.handles.bin")
    write_positions_bin(xy, SITE_PLOTS / "like-repost.positions.bin")


# ===========================================================================
# DEFERRED (need design decisions — see notes in the handoff)
# ===========================================================================
#  - popularity-curve (svg-line): per-user histograms for all eligible users
#    would be 100+ MB. Needs fewer bins / quantization / a min-likes gate
#    before shipping. PNG + bounds are still exported; lookup is TODO.
#  - half-life: Plot 7 is an aggregate histogram with no per-entity (x,y), so
#    there is nothing to search/highlight. Marked non-searchable on the site.
