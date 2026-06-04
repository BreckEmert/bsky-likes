# -*- coding: utf-8 -*-
"""
export_champion_search.py — emit site/public/explore/subs.bin: one uint8 sub-id
per user, ALIGNED to the existing handles.bin order, so the champions tab's
user-search can resolve any handle -> its community (and topic) and float that
row to the top.

Reads the already-exported handles.bin (no need to regenerate the map) and joins
each handle to its sub-cluster via cluster_members_sub.parquet. 255 = not found.

Run:  python export_champion_search.py   (after export_explore_web.py)
"""
import struct
from pathlib import Path

import numpy as np
import polars as pl
from bsky_likes import config

SITE = Path(__file__).parent / "site" / "public" / "explore"

# --- parse the existing handles.bin (uint32 count, count+1 uint32 offsets, utf8
#     bytes; ".bsky.social" stored as the 0x01 sentinel) ---
buf = (SITE / "handles.bin").read_bytes()
n = struct.unpack_from("<I", buf, 0)[0]
offs = struct.unpack_from(f"<{n+1}I", buf, 4)
base = 4 + (n + 1) * 4
handles = []
for i in range(n):
    s = buf[base + offs[i]:base + offs[i + 1]].decode("utf-8")
    handles.append(s.replace("\x01", ".bsky.social"))

# --- handle -> sub ---
m = pl.read_parquet(config.PROJECT_DIR / "cluster_members_sub.parquet").select(["handle", "sub"])
h2s = dict(zip(m["handle"].to_list(), m["sub"].to_list()))
if max(h2s.values()) > 254:
    raise SystemExit("more than 255 subs — bump subs.bin to uint16")

subs = np.array([h2s.get(h, 255) for h in handles], dtype=np.uint8)
subs.tofile(SITE / "subs.bin")
mapped = int((subs != 255).sum())
print(f"[OK] subs.bin: {n:,} entries, {mapped:,} mapped "
      f"({(SITE / 'subs.bin').stat().st_size / 1e3:.0f} KB)")
