# -*- coding: utf-8 -*-
"""
export_champions.py — find each community's CHAMPION: the account it likes far
more than the rest of Bluesky does. Chosen by LIFT, not raw popularity, so even
niche sub-communities get a distinctive owner instead of the same handful of
megastars winning every group.

    lift(account A, community C) =
        (share of C's members who like A)  /  (share of ALL clustered users who like A)

A globally-huge account has a big denominator -> low lift -> loses. A niche
account adored by C -> high lift -> wins. So at any granularity you surface the
real owners. Champions are then bucketed by follower count into upper / middle /
lower "class" (the middle-class ones are the workhorses: they own a community
without being famous).

Writes site/public/explore/champions.json for the "champions" map tab.
Run:  python export_champions.py
"""
import json
import time
from pathlib import Path

import polars as pl
from bsky_likes import config

MIN_SUPPORT = 0.06        # champion must be liked by >= 6% of its community
UPPER_FOLLOWERS = 50_000  # >= this -> upper class
LOWER_FOLLOWERS = 2_000   # < this  -> lower class (middle is in between)
ROOT = Path(__file__).parent
SITE = ROOT / "site" / "public" / "explore"

t0 = time.time()

# --- membership: liker -> sub-cluster, and the sub -> tier-1 topic it sits in ---
sub = pl.read_parquet(config.PROJECT_DIR / "cluster_members_sub.parquet").select(["liker_did", "sub"])
top = pl.read_parquet(config.PROJECT_DIR / "cluster_members_en.parquet").select(["liker_did", "topic"])
mem = sub.join(top, on="liker_did", how="inner")
N = mem.height
sub_sizes = mem.group_by("sub").agg(pl.len().alias("sub_size"))
sub_topic = (
    mem.group_by(["sub", "topic"]).agg(pl.len().alias("n"))
    .sort("n", descending=True).unique("sub", keep="first").select(["sub", "topic"])
)
print(f"{N:,} clustered users, {sub_sizes.height} sub-communities ({time.time()-t0:.0f}s)", flush=True)

# --- streaming join: unique supporters per (sub, liked-author) ---
cmap = mem.select(["liker_did", "sub"])
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(["liker_did", "post_uri"])
posts = pl.scan_parquet(str(config.POSTS_PATH)).select(["post_uri", "post_author_did"])
sa = (
    likes.join(cmap.lazy(), on="liker_did", how="inner")
    .join(posts, on="post_uri", how="inner")
    .group_by(["sub", "post_author_did"])
    .agg(pl.col("liker_did").n_unique().alias("supporters"))  # distinct members, not raw likes
    .collect(engine="streaming")
)
# each user is in exactly one sub, so summing supporters across subs = global count
ga = sa.group_by("post_author_did").agg(pl.col("supporters").sum().alias("global_supporters"))
print(f"likee join done: {sa.height:,} (sub,author) pairs ({time.time()-t0:.0f}s)", flush=True)

# --- lift, then the champion per sub (highest lift clearing the support floor) ---
sa = (
    sa.join(sub_sizes, on="sub")
    .join(ga, on="post_author_did")
    .with_columns(
        (pl.col("supporters") / pl.col("sub_size")).alias("penetration"),
    )
    .with_columns(
        (pl.col("penetration") / (pl.col("global_supporters") / N)).alias("lift"),
    )
    .filter(pl.col("penetration") >= MIN_SUPPORT)
)
champ = sa.sort("lift", descending=True).unique("sub", keep="first")

# --- attach handle + follower count + topic ---
users = pl.read_parquet(config.USERS_PATH, columns=["did", "handle", "followers_count"]).unique("did")
champ = (
    champ.join(users, left_on="post_author_did", right_on="did", how="left")
    .join(sub_topic, on="sub", how="left")
)


def klass(f):
    if f is None:
        return "lower"
    if f >= UPPER_FOLLOWERS:
        return "upper"
    if f >= LOWER_FOLLOWERS:
        return "middle"
    return "lower"


# --- topic names + colors (from the map's legend) ---
legend = json.loads((ROOT / "topic_legend.json").read_text(encoding="utf-8"))
topic_meta = {t["id"]: t for t in legend}

# --- finer-grained tier-2 sub-community names (e.g. "Atproto Tinkerers"). Matched
#     exactly the way the map's tier-1 legend is: greedy overlap of each cluster's
#     top-liked authors with the saved names_reference signatures, so the labels
#     stay in sync with the map. cluster_context_t2 ids == the `sub` ids here. ---
ref2 = json.loads((ROOT / "names_reference.json").read_text(encoding="utf-8"))["tier2"]
ctx2 = {x["id"]: x for x in json.loads((ROOT / "cluster_context_t2.json").read_text(encoding="utf-8"))}
_sig = {r["name"]: set(r["top_likes"]) for r in ref2}
_pairs = []
for _cid, _c in ctx2.items():
    _L = set(b["handle"] for b in _c["likes"][:14])
    for _nm, _tl in _sig.items():
        _pairs.append((len(_L & _tl), _cid, _nm))
_pairs.sort(reverse=True)
_usedc, _usedn, sub_name = set(), set(), {}
for _ov, _cid, _nm in _pairs:
    if _cid in _usedc or _nm in _usedn:
        continue
    sub_name[_cid] = _nm
    _usedc.add(_cid)
    _usedn.add(_nm)

topics: dict = {}
counts = {"upper": 0, "middle": 0, "lower": 0}
for r in champ.sort("lift", descending=True).to_dicts():
    if not r.get("handle"):
        continue
    f = r.get("followers_count")
    cl = klass(f)
    counts[cl] += 1
    tid = r.get("topic")
    tm = topic_meta.get(tid, {})
    t = topics.setdefault(
        tid,
        {"topic": tid, "name": tm.get("name", f"Topic {tid}"),
         "color": tm.get("color", [140, 140, 140]), "champions": []},
    )
    t["champions"].append({
        "handle": r["handle"],
        "subName": sub_name.get(int(r["sub"]), ""),
        "subSize": int(r["sub_size"]),
        "supporters": int(r["supporters"]),
        "lift": round(float(r["lift"]), 1),
        "followers": int(f) if f else 0,
        "class": cl,
    })

# One account can win two sub-communities in the same topic -> merge into a
# single cell (sum the sizes, keep the strongest lift) so it doesn't appear twice.
for t in topics.values():
    by_h, deduped = {}, []
    for c in t["champions"]:
        if c["handle"] in by_h:
            e = by_h[c["handle"]]
            e["subSize"] += c["subSize"]
            e["supporters"] += c["supporters"]
            e["lift"] = max(e["lift"], c["lift"])
            parts = [p for p in e["subName"].split(" + ") if p]
            if c["subName"] and c["subName"] not in parts:
                parts.append(c["subName"])
            e["subName"] = " + ".join(parts)
        else:
            by_h[c["handle"]] = c
            deduped.append(c)
    t["champions"] = deduped
counts = {"upper": 0, "middle": 0, "lower": 0}
for t in topics.values():
    for c in t["champions"]:
        counts[c["class"]] += 1

out = {
    "totalUsers": N,
    "classCounts": counts,
    "topics": sorted(
        topics.values(),
        key=lambda t: -sum(c["subSize"] for c in t["champions"]),
    ),
}
SITE.mkdir(parents=True, exist_ok=True)
(SITE / "champions.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
n_ch = sum(len(t["champions"]) for t in out["topics"])
print(f"[OK] champions.json: {n_ch} champions "
      f"(upper {counts['upper']} / middle {counts['middle']} / lower {counts['lower']}) "
      f"({time.time()-t0:.0f}s)", flush=True)
