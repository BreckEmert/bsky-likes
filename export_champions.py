# -*- coding: utf-8 -*-
"""
export_champions.py — for each community, find the accounts it rallies around,
under THREE interchangeable lenses (the "champions" map tab lets the viewer switch
between them live):

  - devotion     raw count of superfans here (superfan = liked >= FAN_MIN_LIKES of
                 their posts). "Who does this community love most." Shown to the
                 viewer as "Loyalty rate".  [DEFAULT]
  - distinct     LIFT: community like-rate / whole-site like-rate. Surfaces niche
                 signature accounts the rest of Bluesky doesn't care about.
  - likerate     average likes-per-post from this community (prolific accounts
                 only). "Whose posts land reliably here." Controls for volume.

Every like is counted ONLY from members of the account's own community, so a
megastar never wins a community its own people don't actually engage with.

Each lens is fully preset (no tunable knobs). We precompute all four as small
"variants" and ship them in site/public/explore/champions.json; the frontend
radio just swaps between them. Champions are also bucketed by follower count into
upper / middle / lower "class".

Run:  python export_champions.py
"""
import json
import os
import time
from pathlib import Path

import polars as pl
from bsky_likes import config

# After the uncapped sweep finishes, run `USE_SWEEP=1 python export_champions.py`
# to rebuild the champions from the clean (uncapped) likes_v2 shards instead of the
# capped likes/ dir. The global plots stay on the capped likes/ -- only the
# community-specific champions board needs the unbiased pull.
LIKES_SOURCE = config.SWEEP_LIKES_DIR if os.environ.get("USE_SWEEP") else config.LIKES_DIR

FAN_MIN_LIKES = 15        # a "superfan" must have liked >= this many of an account's posts
SUPERFAN_FLOOR = 10       # loyalty/devotion: need >= this many superfans here to qualify
#                           (kills "3 of 3 superfans" share flukes; 10 keeps full coverage)
DISTINCT_FLOOR = 0.10     # distinctiveness: account must be liked by >= 10% of the community
LIKERATE_MIN_FANS = 30    # like-rate: need >= this many (any) likers here to qualify
TOP_K = 6                 # "by community" view: top-K per sub
UPPER_FOLLOWERS = 50_000  # >= this -> upper class
LOWER_FOLLOWERS = 2_000   # < this  -> lower class (middle is in between)
ROOT = Path(__file__).parent
SITE = ROOT / "site" / "public" / "explore"

# Lens metadata travels with the data so the frontend renders the picker +
# mini-explanations from one source of truth. `rank` is the column to sort by.
METRICS = [
    {"id": "devotion", "label": "Loyalty rate", "rank": "superfans", "default": True,
     "blurb": "Accounts with the most superfans (15+ likes) in this community."},
    {"id": "distinct", "label": "Distinctiveness", "rank": "lift",
     "blurb": "Accounts this community likes at a far higher rate than the rest of "
              "Bluesky does (highest lift)."},
    # Like-rate is famous-skewed (rare-but-viral posters like @markhamillofficial
    # top many communities) -- kept by choice; re-evaluate on the uncapped sweep data.
    {"id": "likerate", "label": "Like-rate", "rank": "likeRate",
     "blurb": "Accounts with the highest average likes per post from this community "
              "(must have more posts than the median account)."},
]

t0 = time.time()

# --- membership: liker -> sub-cluster, and the sub -> tier-1 topic it sits in ---
sub = pl.read_parquet(config.PROJECT_DIR / "cluster_members_sub.parquet").select(["liker_did", "sub"])
top = pl.read_parquet(config.PROJECT_DIR / "cluster_members_en.parquet").select(["liker_did", "topic"])
mem = sub.join(top, on="liker_did", how="inner")
N = mem.height
sub_sizes = mem.group_by("sub").agg(pl.len().alias("ss"))
sub_topic = (
    mem.group_by(["sub", "topic"]).agg(pl.len().alias("n"))
    .sort("n", descending=True).unique("sub", keep="first").select(["sub", "topic"])
)
print(f"{N:,} clustered users, {sub_sizes.height} sub-communities ({time.time()-t0:.0f}s)", flush=True)

cmap = mem.select(["liker_did", "sub"])
# The author DID is embedded in every post_uri (at://<author_did>/app.bsky.feed.post/
# <rkey>), so we PARSE it instead of joining to posts.parquet. This lets the board run
# straight off the raw (uncapped sweep) likes WITHOUT enriching tens of millions of
# posts: enrichment only adds like_count/created_at, and the board uses neither -- it
# needs only post_uri -> author plus the superfan counts derived from the likes.
likes = (pl.scan_parquet(str(LIKES_SOURCE / "part-*.parquet"))
         .select(["liker_did", "post_uri"])
         .with_columns(pl.col("post_uri").str.extract(r"^at://([^/]+)/", 1)
                       .alias("post_author_did")))
print(f"likes source: {LIKES_SOURCE.name}", flush=True)
base = likes.join(cmap.lazy(), on="liker_did", how="inner")

# per (sub, author): unique likers (any like) + total likes
agg = (
    base.group_by(["sub", "post_author_did"])
    .agg(pl.col("liker_did").n_unique().alias("uf"), pl.len().alias("tl"))
    .collect(engine="streaming")
)
# per (sub, author): superfans = distinct members who liked >= FAN_MIN_LIKES of their posts
sf = (
    base.group_by(["sub", "post_author_did", "liker_did"]).agg(pl.len().alias("np"))
    .filter(pl.col("np") >= FAN_MIN_LIKES)
    .group_by(["sub", "post_author_did"]).agg(pl.len().alias("superfans"))
    .collect(engine="streaming")
)
# author post volume (for like-rate): distinct liked posts per author, from the likes
npost = (likes.select(["post_author_did", "post_uri"]).unique()
         .group_by("post_author_did").agg(pl.len().alias("npost"))
         .collect(engine="streaming"))
print(f"aggregations done ({time.time()-t0:.0f}s)", flush=True)

# --- assemble the master per-(sub, author) stats table ---
users = pl.read_parquet(config.USERS_PATH, columns=["did", "handle", "followers_count"]).unique("did")
d = (
    agg.join(sf, on=["sub", "post_author_did"], how="left")
    .join(npost, on="post_author_did", how="left")
    .join(sub_sizes, on="sub")
    .join(sub_topic, on="sub", how="left")
    .join(users, left_on="post_author_did", right_on="did", how="left")
    .filter(pl.col("handle").is_not_null())          # drop deleted/unresolved accounts
    .with_columns(pl.col("superfans").fill_null(0))
)
# global superfans per author (sum across communities) -> loyalty denominator
gsf = d.group_by("post_author_did").agg(pl.col("superfans").sum().alias("gsf"))
# global unique likers per author -> lift denominator
guf = d.group_by("post_author_did").agg(pl.col("uf").sum().alias("guf"))
d = d.join(gsf, on="post_author_did").join(guf, on="post_author_did")
d = d.with_columns([
    pl.when(pl.col("gsf") > 0).then(pl.col("superfans") / pl.col("gsf")).otherwise(0.0).alias("share"),
    (pl.col("uf") / pl.col("ss")).alias("pen"),
    (pl.col("tl") / pl.col("npost")).alias("likeRate"),
])
d = d.with_columns((pl.col("pen") / (pl.col("guf") / N)).alias("lift"))
# loyalty = concentration (share) tempered by substance (log of superfans), so a
# devoted home community wins without a hard floor: tiny accounts score ~0, and it
# keeps full coverage + recognizable pillars (codetard, gracekind) instead of the
# either/or a fixed superfan floor forces.
d = d.with_columns((pl.col("share") * (pl.col("superfans") + 1).log()).alias("loyaltyScore"))
MED_POST = float(d.filter(pl.col("uf") >= LIKERATE_MIN_FANS)["npost"].median())
print(f"master table: {d.height:,} (sub,author) rows; median posts={MED_POST:.0f} ({time.time()-t0:.0f}s)", flush=True)

# --- tier-2 sub-community names (e.g. "Atproto Tinkerers"), matched the same way
#     the map's tier-1 legend is: greedy overlap of each cluster's top-liked authors
#     with names_reference. cluster_context_t2 ids == the `sub` ids. ---
ref2 = json.loads((ROOT / "names_reference.json").read_text(encoding="utf-8"))["tier2"]
ctx2 = {x["id"]: x for x in json.loads((ROOT / "cluster_context_t2.json").read_text(encoding="utf-8"))}
_sig = {r["name"]: set(r["top_likes"]) for r in ref2}
_pairs = []
for _cid, _c in ctx2.items():
    _L = set(b["handle"] for b in _c["likes"][:14])
    for _nm, _tl in _sig.items():
        _pairs.append((len(_L & _tl), _cid, _nm))
_pairs.sort(reverse=True)
_uc, _un, sub_name = set(), set(), {}
for _ov, _cid, _nm in _pairs:
    if _cid in _uc or _nm in _un:
        continue
    sub_name[_cid] = _nm
    _uc.add(_cid)
    _un.add(_nm)

legend = json.loads((ROOT / "topic_legend.json").read_text(encoding="utf-8"))
topic_meta = {t["id"]: t for t in legend}


def klass(f):
    if f is None:
        return "lower"
    if f >= UPPER_FOLLOWERS:
        return "upper"
    if f >= LOWER_FOLLOWERS:
        return "middle"
    return "lower"


def champ_dict(r):
    f = r.get("followers_count")
    return {
        "handle": r["handle"],
        "subName": sub_name.get(int(r["sub"]), ""),
        "subSize": int(r["ss"]),
        "followers": int(f) if f else 0,
        "class": klass(f),
        "superfans": int(r["superfans"] or 0),
        "globalSuperfans": int(r["gsf"] or 0),
        "share": round(float(r["share"] or 0), 4),
        "lift": round(float(r["lift"] or 0), 1),
        "likeRate": round(float(r["likeRate"] or 0), 1),
    }


def build_variant(rank, floor):
    """champion-per-sub (by-topic) + top-K-per-sub (by-community) under one lens."""
    dq = d.with_columns(floor.alias("_q"))   # _q = clears this lens's quality floor
    dd = dq.filter(pl.col("_q"))             # by-topic champions must clear the floor

    # ---- by-topic: each sub's #1, grouped under its tier-1 topic ----
    champ = dd.sort(rank, descending=True).unique("sub", keep="first")
    topics = {}
    counts = {"upper": 0, "middle": 0, "lower": 0}
    for r in champ.sort(rank, descending=True).to_dicts():
        c = champ_dict(r)
        c["value"] = round(float(r[rank] or 0), 4)  # for the by-community bar width
        counts[c["class"]] += 1
        tid = r.get("topic")
        tm = topic_meta.get(tid, {})
        t = topics.setdefault(tid, {"topic": tid, "name": tm.get("name", f"Topic {tid}"),
                                    "color": tm.get("color", [140, 140, 140]), "champions": []})
        t["champions"].append(c)
    # one handle can win two subs in the same topic -> merge into a single cell
    for t in topics.values():
        by_h, deduped = {}, []
        for c in t["champions"]:
            if c["handle"] in by_h:
                e = by_h[c["handle"]]
                e["subSize"] += c["subSize"]
                e["superfans"] += c["superfans"]
                parts = [p for p in e["subName"].split(" + ") if p]
                if c["subName"] and c["subName"] not in parts:
                    parts.append(c["subName"])
                e["subName"] = " + ".join(parts)
            else:
                by_h[c["handle"]] = c
                deduped.append(c)
        t["champions"] = deduped

    # ---- by-community: each sub's top-K, preferring floor-qualified accounts and
    #      backfilling with the next-best so every community shows a full TOP_K ----
    topk = (
        dq.sort([pl.col("_q"), pl.col(rank)], descending=[True, True])
        .group_by("sub").head(TOP_K)
    )
    communities = {}
    for r in topk.sort(rank, descending=True).to_dicts():
        sid = int(r["sub"])
        tid = r.get("topic")
        co = communities.setdefault(sid, {
            "sub": sid, "name": sub_name.get(sid, ""), "topic": tid,
            "color": topic_meta.get(tid, {}).get("color", [140, 140, 140]),
            "subSize": int(r["ss"]), "champions": [],
        })
        cd = champ_dict(r)
        cd["value"] = round(float(r[rank] or 0), 4)
        co["champions"].append(cd)

    return {
        "classCounts": counts,
        "topics": sorted(topics.values(), key=lambda t: -sum(c["subSize"] for c in t["champions"])),
        "communities": sorted(communities.values(), key=lambda c: -c["subSize"]),
    }


FLOORS = {
    "devotion": pl.col("superfans") >= SUPERFAN_FLOOR,
    # lift, but also require a real local following (>=10 superfans), else it
    # surfaces accounts liked ONCE by many (0-1 superfans) -> obscure flukes.
    "distinct": (pl.col("pen") >= DISTINCT_FLOOR) & (pl.col("superfans") >= SUPERFAN_FLOOR),
    "likerate": (pl.col("uf") >= LIKERATE_MIN_FANS) & (pl.col("npost") >= MED_POST),
}
variants = {}
for m in METRICS:
    v = build_variant(m["rank"], FLOORS[m["id"]])
    variants[m["id"]] = v
    cc = v["classCounts"]
    tot = sum(cc.values()) or 1
    print(f"  [{m['id']:9s}] {len(v['communities'])}/49 communities, "
          f"classes U{cc['upper']}/M{cc['middle']}/L{cc['lower']} "
          f"({round((cc['middle']+cc['lower'])/tot*100)}% non-famous)", flush=True)

out = {
    "totalUsers": N,
    "fanMinLikes": FAN_MIN_LIKES,
    "metrics": [{k: m[k] for k in ("id", "label", "blurb")} | ({"default": True} if m.get("default") else {})
                for m in METRICS],
    "variants": variants,
}
SITE.mkdir(parents=True, exist_ok=True)
(SITE / "champions.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"[OK] champions.json: {len(METRICS)} lenses ({time.time()-t0:.0f}s)", flush=True)
