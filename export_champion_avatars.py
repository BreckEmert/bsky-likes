# -*- coding: utf-8 -*-
"""
export_champion_avatars.py — add profile pictures to the champions board.

Collects every distinct champion handle in champions.json, resolves each to its
DID (stable even if the account renamed), fetches avatar URLs from the public
Bluesky AppView (getProfiles, batched), and writes a deduped {handle: avatarUrl}
map into champions.json as `avatars`. The frontend looks up ch.handle -> avatar.

Run AFTER export_champions.py (and re-run after the sweep regen).
Run:  python export_champion_avatars.py
"""
import json
import time
from pathlib import Path

import httpx
import polars as pl
from bsky_likes import config

SITE = Path(__file__).parent / "site" / "public" / "explore"
CH = SITE / "champions.json"
APPVIEW = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"

d = json.loads(CH.read_text(encoding="utf-8"))

# every distinct champion handle across all lenses + both views
handles = set()
for v in d["variants"].values():
    for co in v["communities"]:
        handles.update(ch["handle"] for ch in co["champions"])
    for t in v["topics"]:
        handles.update(ch["handle"] for ch in t["champions"])
print(f"{len(handles)} distinct champion handles")

# handle -> DID (DID is the stable key; getProfiles by DID returns the CURRENT
# avatar even if the handle has since changed)
u = pl.read_parquet(config.USERS_PATH, columns=["did", "handle"]).unique("handle")
h2d = dict(zip(u["handle"].to_list(), u["did"].to_list()))
dids = sorted({h2d[h] for h in handles if h in h2d})

did2av = {}
with httpx.Client(timeout=30, headers={"user-agent": "bsky-likes-avatars/0.1"}) as c:
    for i in range(0, len(dids), 25):
        batch = dids[i:i + 25]
        try:
            r = c.get(APPVIEW, params=[("actors", x) for x in batch])
            for p in r.json().get("profiles", []):
                if p.get("avatar"):
                    # getProfiles hands back the full-size avatar (~1000px). We
                    # render it at 20px, so request the tiny thumbnail variant
                    # instead — same CDN, a fraction of the bytes.
                    did2av[p["did"]] = p["avatar"].replace(
                        "/img/avatar/plain/", "/img/avatar_thumbnail/plain/"
                    )
        except Exception as e:
            print("  batch failed:", e)
        time.sleep(0.1)

avatars = {h: did2av[h2d[h]] for h in handles if h2d.get(h) in did2av}
d["avatars"] = avatars
CH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print(f"[OK] {len(avatars)}/{len(handles)} champions have avatars -> champions.json")
