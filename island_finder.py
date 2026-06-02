# -*- coding: utf-8 -*-
"""
island_finder.py  —  find the SPATIAL islands the user actually sees

Root cause of the whack-a-mole: islands were removed in the 50-d TF-IDF space,
but the dots are laid out by the 2D UMAP. A TF-IDF cluster isn't spatially
contiguous, so removing it doesn't clear the visible 2D spike.

This finds islands in the SAME 2D space the map is drawn in: DBSCAN on the 2D
coords (of the current English set) -> the main mass is one giant component;
everything else is a separate spatial island. For each island we pull 3
non-empty bios so a human (Claude) can judge foreign-vs-English directly.

Run:  python island_finder.py [eps]
"""
import json, sys, time, urllib.parse, urllib.request
import numpy as np, polars as pl
from sklearn.cluster import DBSCAN
from bsky_likes import config

EPS = float(sys.argv[1]) if len(sys.argv) > 1 else 0.25
MIN_SAMPLES = 15
ISLAND_MAX = 6000          # components bigger than this are "mainland", not islands
SAMPLE_BIOS = 3
APP = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"

coords = pl.read_parquet(config.PROJECT_DIR / "umap_coords.parquet")
en = set(json.loads((config.PROJECT_DIR / "english_dids.json").read_text()))
coords = coords.filter(pl.col("liker_did").is_in(list(en)))
xy = np.column_stack([coords["x"].to_numpy(), coords["y"].to_numpy()])
dids = coords["liker_did"].to_list()
handles = coords["handle"].to_list()
print(f"[i] {len(xy):,} English points; DBSCAN eps={EPS} min_samples={MIN_SAMPLES}", flush=True)

lab = DBSCAN(eps=EPS, min_samples=MIN_SAMPLES, n_jobs=-1).fit_predict(xy)
import collections
sizes = collections.Counter(lab.tolist())
main = max((c for c in sizes if c != -1), key=lambda c: sizes[c])
noise = sizes.get(-1, 0)
comps = sorted([c for c in sizes if c not in (-1, main)], key=lambda c: -sizes[c])
print(f"[i] mainland comp={main} size={sizes[main]:,} | noise={noise:,} | "
      f"{len(comps)} other components", flush=True)
print("[i] component size histogram (excl mainland):",
      sorted((sizes[c] for c in comps), reverse=True)[:40], flush=True)

# islands = non-mainland components within the island size band
islands = [c for c in comps if sizes[c] <= ISLAND_MAX]
print(f"[i] {len(islands)} islands (<= {ISLAND_MAX}); total {sum(sizes[c] for c in islands):,} users", flush=True)

rng = np.random.default_rng(0)
cache = {}
def fetch(hs):
    todo = [h for h in dict.fromkeys(hs) if h and h.lower() not in cache]
    for i in range(0, len(todo), 25):
        b = todo[i:i+25]; url = APP + "?" + "&".join("actors=" + urllib.parse.quote(h) for h in b)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "x"}), timeout=30) as r:
                for p in json.load(r).get("profiles", []):
                    cache[(p.get("handle") or "").lower()] = ((p.get("description") or "") + " " + (p.get("displayName") or "")).strip()
        except Exception:
            pass
        time.sleep(0.08)

# oversample handles per island so we can find 3 non-empty bios
cand = {}
for c in islands:
    members = np.where(lab == c)[0]
    pick = [handles[i] for i in rng.choice(members, size=min(20, len(members)), replace=False) if handles[i]]
    cand[c] = pick
fetch([h for v in cand.values() for h in v])

out = []
for c in islands:
    members = np.where(lab == c)[0]
    bios = []
    for h in cand[c]:
        d = cache.get((h or "").lower(), "")
        if d:
            bios.append({"handle": h, "desc": d})
            if len(bios) >= SAMPLE_BIOS:
                break
    cx, cy = xy[members, 0].mean(), xy[members, 1].mean()
    out.append({"comp": int(c), "size": int(sizes[c]), "x": round(float(cx), 2),
                "y": round(float(cy), 2), "bios": bios,
                "members": [dids[i] for i in members]})
out.sort(key=lambda o: (round(o["x"], 0), o["y"]))
# write samples (without member lists) for reading, + full members for removal
(config.PROJECT_DIR.parent / "island_samples.json").write_text(
    json.dumps([{k: v for k, v in o.items() if k != "members"} for o in out], ensure_ascii=False), encoding="utf-8")
(config.PROJECT_DIR / "island_components.json").write_text(
    json.dumps({str(o["comp"]): o["members"] for o in out}), encoding="utf-8")
print(f"[OK] island_samples.json ({len(out)} islands) + island_components.json", flush=True)
