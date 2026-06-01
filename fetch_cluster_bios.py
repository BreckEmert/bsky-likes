# -*- coding: utf-8 -*-
"""
fetch_cluster_bios.py  —  sample 30 random profile bios per cluster (Theo's
naming signal). Reads cluster_members.parquet (from umap_regions.py), samples
members per (tier, cluster), and pulls their profile description + displayName
from the public (unauthenticated) bsky AppView. Writes cluster_bios.json for the
naming step.

Run:  python fetch_cluster_bios.py
"""
import json
import time
import urllib.parse
import urllib.request
import numpy as np
import polars as pl

from bsky_likes import config

MEMBERS = config.PROJECT_DIR / "cluster_members.parquet"
OUT = config.PROJECT_DIR.parent / "cluster_bios.json"
APPVIEW = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"
N_SAMPLE = 30
SEED = 0

df = pl.read_parquet(MEMBERS)
rng = np.random.default_rng(SEED)

# sample handles per (tier, cluster)
samples = {}     # (tier, cid) -> [handles]
needed = set()
for tier, col in [(1, "t1"), (2, "t2"), (3, "t3")]:
    for cid in sorted(df[col].unique().to_list()):
        hs = df.filter(pl.col(col) == cid)["handle"].to_list()
        pick = [str(h) for h in rng.choice(hs, size=min(N_SAMPLE, len(hs)), replace=False)]
        samples[(tier, cid)] = pick
        needed.update(pick)
print(f"[i] {len(samples)} clusters, {len(needed):,} unique handles to fetch", flush=True)


def get_profiles(batch):
    url = APPVIEW + "?" + "&".join("actors=" + urllib.parse.quote(h) for h in batch)
    req = urllib.request.Request(url, headers={"User-Agent": "bsky-likes-analysis/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("profiles", [])
        except Exception as e:
            if attempt == 2:
                print(f"    batch failed: {e}", flush=True)
            time.sleep(1.0 * (attempt + 1))
    return []


prof = {}
nb = list(needed)
for i in range(0, len(nb), 25):
    for p in get_profiles(nb[i:i + 25]):
        prof[(p.get("handle") or "").lower()] = {
            "handle": p.get("handle", ""),
            "name": p.get("displayName", "") or "",
            "desc": p.get("description", "") or "",
        }
    if i % 250 == 0:
        print(f"    fetched {min(i+25, len(nb)):,}/{len(nb):,}", flush=True)
    time.sleep(0.12)
print(f"[i] got {len(prof):,} profiles", flush=True)

out = []
for (tier, cid), hs in samples.items():
    bios = []
    for h in hs:
        p = prof.get(h.lower())
        if p and (p["desc"].strip() or p["name"].strip()):
            bios.append(p)
    out.append({"tier": tier, "id": int(cid), "sampled": len(hs), "with_bio": len(bios),
                "bios": bios})

OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
cov = np.mean([r["with_bio"] for r in out])
print(f"[OK] {OUT.name}  ({len(out)} clusters, avg {cov:.1f} non-empty bios/cluster)",
      flush=True)
