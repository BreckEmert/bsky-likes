# -*- coding: utf-8 -*-
"""
cluster_context.py  —  richer naming context per cluster (both tiers)

For each cluster, gather:
  - 20 NON-EMPTY member bios (who they are)
  - 25 NON-EMPTY bios of the authors the cluster most LIKES (what they enjoy),
    found via a streaming likes -> posts -> author join.
Empty/None bios are skipped so every cluster gets a consistent amount of signal.

Writes cluster_context_t1.json / cluster_context_t2.json for the naming step.

Run:  python cluster_context.py
"""
import json, time, urllib.parse, urllib.request
import numpy as np, polars as pl
from bsky_likes import config

MEMBER_N = 20         # non-empty member bios per cluster
LIKEE_N = 25          # non-empty liked-author bios per cluster
OVERSAMPLE = 90       # fetch this many candidates to reach N non-empty
TOP_AUTHORS = 90      # consider this many top liked-authors per cluster
SEED = 0
APP = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"
rng = np.random.default_rng(SEED)
cache = {}

def fetch(hs):
    todo = [h for h in dict.fromkeys(hs) if h and h.lower() not in cache]
    for i in range(0, len(todo), 25):
        b = todo[i:i+25]
        url = APP + "?" + "&".join("actors=" + urllib.parse.quote(h) for h in b)
        got = []
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "x"}), timeout=30) as r:
                    got = json.load(r).get("profiles", []); break
            except Exception:
                time.sleep(1.0 * (attempt + 1))
        for p in got:
            cache[(p.get("handle") or "").lower()] = ((p.get("description") or "") + " " + (p.get("displayName") or "")).strip()
        time.sleep(0.08)

def non_empty(handles, n):
    out = []
    for h in handles:
        d = cache.get((h or "").lower(), "")
        if d and len(d) >= 2:
            out.append({"handle": h, "desc": d})
            if len(out) >= n:
                break
    return out

users = pl.read_parquet(config.USERS_PATH, columns=["did", "handle"]).unique("did")

def build(members_path, col, out_path, label):
    t0 = time.time()
    mem = pl.read_parquet(members_path)
    clusters = sorted(mem[col].unique().to_list())
    print(f"[{label}] {len(clusters)} clusters, {mem.height:,} users", flush=True)

    # top liked-authors per cluster (streaming join)
    cmap = mem.select(["liker_did", col])
    likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(["liker_did", "post_uri"])
    posts = pl.scan_parquet(str(config.POSTS_PATH)).select(["post_uri", "post_author_did"])
    ca = (likes.join(cmap.lazy(), on="liker_did", how="inner")
          .join(posts, on="post_uri", how="inner")
          .group_by([col, "post_author_did"]).agg(pl.len().alias("c"))
          .collect(engine="streaming"))
    ca = ca.join(users, left_on="post_author_did", right_on="did", how="left").filter(pl.col("handle").is_not_null())
    print(f"[{label}] likee join done ({time.time()-t0:.0f}s)", flush=True)

    # gather candidate handles to fetch
    member_cands, likee_cands = {}, {}
    for c in clusters:
        hs = mem.filter(pl.col(col) == c)["handle"].to_list()
        pick = [str(hs[i]) for i in rng.choice(len(hs), size=min(OVERSAMPLE, len(hs)), replace=False)]
        member_cands[c] = pick
        top = (ca.filter(pl.col(col) == c).sort("c", descending=True).head(TOP_AUTHORS)["handle"].to_list())
        likee_cands[c] = [str(h) for h in top]
    fetch([h for v in member_cands.values() for h in v] + [h for v in likee_cands.values() for h in v])
    print(f"[{label}] fetched {len(cache):,} bios cumulative ({time.time()-t0:.0f}s)", flush=True)

    out = []
    for c in clusters:
        out.append({
            "id": int(c),
            "size": int(mem.filter(pl.col(col) == c).height),
            "members": non_empty(member_cands[c], MEMBER_N),
            "likes": non_empty(likee_cands[c], LIKEE_N),
        })
    (config.PROJECT_DIR.parent / out_path).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    cov_m = np.mean([len(o["members"]) for o in out]); cov_l = np.mean([len(o["likes"]) for o in out])
    print(f"[OK] {out_path}: {len(out)} clusters, avg {cov_m:.0f} member + {cov_l:.0f} likee bios ({time.time()-t0:.0f}s)", flush=True)

build(config.PROJECT_DIR / "cluster_members_en.parquet", "topic", "cluster_context_t1.json", "T1")
build(config.PROJECT_DIR / "cluster_members_sub.parquet", "sub", "cluster_context_t2.json", "T2")
