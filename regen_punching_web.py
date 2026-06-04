"""Regenerate site/public/plots/punching.png as a CLEAN scatter (no baked gold
highlights / labels), using ONLY the already-exported web data -- no parquet
pipeline needed.

punching.positions.bin stores [followers_count+1, likes_per_post+1] per point,
so the original color (engagement_ratio = likes_per_post/(followers+1)) is
recoverable as (y-1)/x. We re-render with the same axes/limits/theme and let the
bounds.json be re-derived from the rendered axes, so the existing positions.bin
overlay (the "highlight 15 you follow" rings) stays pixel-aligned.
"""
import json
import struct
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

SITE_PLOTS = Path(__file__).parent / "site" / "public" / "plots"

# --- dark theme (mirrors plots.py) ---
plt.rcParams.update({
    "figure.facecolor": "#0e1116",
    "axes.facecolor": "#0e1116",
    "axes.edgecolor": "#9aa4b1",
    "axes.labelcolor": "#e6edf3",
    "xtick.color": "#9aa4b1",
    "ytick.color": "#9aa4b1",
    "text.color": "#e6edf3",
    "axes.titlecolor": "#e6edf3",
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "font.family": "DejaVu Sans",
    "axes.grid": True,
    "grid.color": "#1f2933",
    "grid.linewidth": 0.6,
})

# --- load the exported positions: x = followers+1, y = likes_per_post+1 ---
xy = np.fromfile(SITE_PLOTS / "punching.positions.bin", dtype=np.float32).reshape(-1, 2)
x = xy[:, 0].astype(np.float64)
y = xy[:, 1].astype(np.float64)
eng = (y - 1.0) / x  # engagement_ratio = likes_per_post / (followers + 1)
print(f"{len(xy):,} points; engagement_ratio range {eng.min():.4g}..{eng.max():.4g}")

# --- render (no manual highlights) ---
fig, ax = plt.subplots(figsize=(12, 7.5))
sc = ax.scatter(
    x, y, s=8, c=eng, cmap="plasma", alpha=0.55, edgecolors="none",
    norm=LogNorm(vmin=np.quantile(eng, 0.05) + 1e-6, vmax=np.quantile(eng, 0.95)),
)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(1e3, 10 ** 6.5)
ax.set_ylim(10, None)
cb = fig.colorbar(sc, ax=ax, label="engagement ratio (log)")
cb.outline.set_visible(False)
ax.set_xlabel("Follower count")
ax.set_ylabel("Avg likes per post")
ax.set_title("Top 4,000 liked accounts", fontsize=18)

# --- export PNG + bounds (mirrors export_web.export_png_and_bounds) ---
DPI = 200
ax.set_title("")  # title is rendered as HTML on the site
fig.canvas.draw()
x_min, x_max = ax.get_xlim()
y_min, y_max = ax.get_ylim()
fig_w_px = fig.get_figwidth() * DPI
fig_h_px = fig.get_figheight() * DPI
pos = ax.get_position()
bounds = {
    "xMin": float(x_min), "xMax": float(x_max),
    "yMin": float(y_min), "yMax": float(y_max),
    "xLog": True, "yLog": True,
    "imgWidth": int(round(fig_w_px)), "imgHeight": int(round(fig_h_px)),
    "plotArea": {
        "left": float(pos.x0 * fig_w_px),
        "top": float((1.0 - pos.y1) * fig_h_px),
        "right": float(pos.x1 * fig_w_px),
        "bottom": float((1.0 - pos.y0) * fig_h_px),
    },
}
with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0}):
    fig.savefig(SITE_PLOTS / "punching.png", dpi=DPI, transparent=True)
(SITE_PLOTS / "punching.bounds.json").write_text(json.dumps(bounds, indent=2))
print("[OK] wrote punching.png + punching.bounds.json")
print("plotArea:", bounds["plotArea"], "img", bounds["imgWidth"], "x", bounds["imgHeight"])
