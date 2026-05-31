# -*- coding: utf-8 -*-
"""
bsky_health_check.py

Comprehensive integrity scan of the bsky-likes dataset.
Designed to catch any anomalies introduced by extending the data.

Run: python health_check.py 2>&1 | tee health_check.txt
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import polars as pl

# Make the bsky_likes package importable regardless of working directory.
try:
    _ROOT = Path(__file__).resolve().parent
except NameError:
    _ROOT = Path.cwd()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bsky_likes import config

# ============================================================================
PROJECT_DIR = config.PROJECT_DIR
LIKES_DIR   = config.LIKES_DIR
POSTS_PATH  = config.POSTS_PATH
USERS_PATH  = config.USERS_PATH

def section(title):
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)

def ok(msg):
    print(f"  [OK]   {msg}")

def warn(msg):
    print(f"  [WARN] {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")

# ============================================================================
# 1. SHARD INVENTORY AND SCHEMA CONSISTENCY
# ============================================================================
section("1. SHARD INVENTORY")

shards = sorted(LIKES_DIR.glob("part-*.parquet"))
print(f"Total shards: {len(shards)}")
if not shards:
    fail("No shards found.")
    raise SystemExit(1)

# Check for index gaps
indices = [int(s.stem.split("-")[1]) for s in shards]
expected = list(range(min(indices), max(indices) + 1))
missing = sorted(set(expected) - set(indices))
duplicates = [i for i in set(indices) if indices.count(i) > 1]
if missing:
    warn(f"Missing shard indices: {missing[:10]}{'...' if len(missing) > 10 else ''}")
else:
    ok(f"Shard indices contiguous from {min(indices):05d} to {max(indices):05d}")
if duplicates:
    fail(f"Duplicate shard indices: {duplicates}")
else:
    ok("No duplicate indices")

# Size distribution
sizes = [s.stat().st_size for s in shards]
total_mb = sum(sizes) / 1e6
print(f"Total likes parquet: {total_mb:,.1f} MB")
print(f"Shard size range: {min(sizes)/1e6:.2f} MB to {max(sizes)/1e6:.2f} MB")
tiny = [s for s in shards if s.stat().st_size < 1000]
if tiny:
    warn(f"{len(tiny)} shards under 1 KB (likely empty checkpoints, mostly harmless)")
else:
    ok("No suspicious tiny shards")

# Schema consistency
schemas = set()
for s in shards:
    sch = pl.read_parquet_schema(s)
    schemas.add(tuple(sorted(sch.items())))
print(f"Distinct schemas across shards: {len(schemas)}  (should be 1)")
if len(schemas) == 1:
    ok(f"Schema: {dict(next(iter(schemas)))}")
else:
    fail("Schema mismatch — incompatible shards present")
    for s in schemas:
        print("    ", dict(s))

# ============================================================================
# 2. LIKES DATA INTEGRITY
# ============================================================================
section("2. LIKES DATA")

likes = pl.scan_parquet([str(s) for s in shards]).collect()
n = len(likes)
print(f"Total like rows: {n:,}")
print(f"Unique likers:   {likes['liker_did'].n_unique():,}")
print(f"Unique posts:    {likes['post_uri'].n_unique():,}")

# Nulls
nulls = likes.null_count()
print("Null counts per column:")
for col in nulls.columns:
    v = nulls[col][0]
    if v == 0:
        ok(f"  {col}: 0 nulls")
    else:
        fail(f"  {col}: {v:,} nulls")

# DID format
bad_did = likes.filter(~pl.col("liker_did").str.starts_with("did:")).height
if bad_did == 0:
    ok("All liker_dids start with 'did:'")
else:
    fail(f"{bad_did} malformed liker_dids")

# URI format
bad_uri = likes.filter(~pl.col("post_uri").str.starts_with("at://did:")).height
if bad_uri == 0:
    ok("All post_uris start with 'at://did:'")
else:
    warn(f"{bad_uri} malformed post_uris (very small; safe to drop in analysis)")

# Date range
min_ts = likes["like_created_at"].min()
max_ts = likes["like_created_at"].max()
span_days = (max_ts - min_ts).total_seconds() / 86400
print(f"Date range: {min_ts}  to  {max_ts}")
print(f"Span: {span_days:.1f} days")
now = datetime.now(timezone.utc)
future_likes = likes.filter(pl.col("like_created_at") > now).height
if future_likes == 0:
    ok("No likes timestamped in the future")
else:
    warn(f"{future_likes:,} likes have future timestamps (clock-skew clients)")
ancient = likes.filter(pl.col("like_created_at") < datetime(2023, 1, 1, tzinfo=timezone.utc)).height
if ancient == 0:
    ok("No suspiciously ancient likes")
else:
    warn(f"{ancient:,} likes dated before 2023 (clock-skew clients)")

# Exact duplicates within likes
dupes = (likes.group_by(["liker_did", "post_uri", "like_created_at"])
              .agg(pl.len().alias("n"))
              .filter(pl.col("n") > 1))
if dupes.height == 0:
    ok("No exact (liker, post, ts) duplicates")
else:
    warn(f"{dupes.height} exact duplicates (likely from extend re-fetching boundary likes)")

# Near-duplicates (same liker+post, different timestamps — re-like behavior)
near_dupes = (likes.group_by(["liker_did", "post_uri"])
                   .agg(pl.len().alias("n"))
                   .filter(pl.col("n") > 1))
if near_dupes.height == 0:
    ok("No repeat likes on same post by same user")
else:
    print(f"  ({near_dupes.height:,} (liker, post) pairs with multiple timestamps — "
          f"users unliking and re-liking is normal)")

# ============================================================================
# 3. EXTEND BOUNDARY CHECK
# ============================================================================
section("3. EXTEND BOUNDARY")

# Look at per-shard date ranges to see if there's a clear "original vs extended" split
print("Per-shard date ranges (showing oldest 5, newest 5):")
shard_summary = []
for s in shards:
    df = pl.read_parquet(s, columns=["like_created_at"])
    if df.height > 0:
        shard_summary.append({
            "shard": s.name,
            "n": df.height,
            "min": df["like_created_at"].min(),
            "max": df["like_created_at"].max(),
        })
shard_summary.sort(key=lambda r: int(r["shard"].split("-")[1].split(".")[0]))
for r in shard_summary[:5] + [{"shard": "...", "n": "", "min": "", "max": ""}] + shard_summary[-5:]:
    print(f"  {r['shard']:>20s}  n={str(r['n']):>7s}  "
          f"{str(r['min'])[:19] if r['min'] else '':<19s} ->  "
          f"{str(r['max'])[:19] if r['max'] else '':<19s}")

# Find the transition: the shard where dates jump forward
print("\nLooking for the extend boundary (shard where dates jump forward >1 day)...")
transitions = []
for i in range(1, len(shard_summary)):
    prev_max = shard_summary[i-1]["max"]
    this_min = shard_summary[i]["min"]
    if prev_max and this_min:
        gap_days = (this_min - prev_max).total_seconds() / 86400
        if abs(gap_days) > 1:
            transitions.append((shard_summary[i]["shard"], gap_days))
if transitions:
    print(f"  Found {len(transitions)} date-jump transitions:")
    for shard, gap in transitions[:5]:
        print(f"    at {shard}: jump of {gap:+.1f} days")
else:
    ok("No major date jumps between shards")

# ============================================================================
# 4. POSTS TABLE
# ============================================================================
section("4. posts.parquet")

if not POSTS_PATH.exists():
    fail("posts.parquet missing")
else:
    posts = pl.read_parquet(POSTS_PATH)
    print(f"Rows: {len(posts):,}")
    print(f"Size: {POSTS_PATH.stat().st_size/1e6:.2f} MB")
    print(f"Schema: {dict(posts.schema)}")

    # Nulls
    for col in posts.columns:
        v = posts[col].null_count()
        if v == 0:
            ok(f"  {col}: 0 nulls")
        else:
            warn(f"  {col}: {v:,} nulls")

    # Duplicates
    dup_posts = (posts.group_by("post_uri")
                       .agg(pl.len().alias("n"))
                       .filter(pl.col("n") > 1))
    if dup_posts.height == 0:
        ok("post_uri is unique across posts.parquet")
    else:
        fail(f"{dup_posts.height:,} duplicate post_uri rows in posts.parquet")
        print(dup_posts.head())

    # Coverage: are all post_uris in likes present in posts.parquet?
    likes_uris = set(likes["post_uri"].to_list())
    posts_uris = set(posts["post_uri"].to_list())
    missing_in_posts = likes_uris - posts_uris
    extra_in_posts = posts_uris - likes_uris
    pct_missing = len(missing_in_posts) / max(len(likes_uris), 1) * 100
    print(f"\nLiked posts not in posts.parquet: {len(missing_in_posts):,}  ({pct_missing:.2f}%)")
    if pct_missing < 5:
        ok("Coverage gap is expected (deleted/blocked posts)")
    else:
        warn(f"Unusually large coverage gap: {pct_missing:.1f}%")
    if extra_in_posts:
        warn(f"{len(extra_in_posts):,} posts in posts.parquet not referenced by any like")
    else:
        ok("No orphan posts (all enriched posts are referenced by a like)")

    # Sanity on counts
    neg_quote = posts.filter(pl.col("quote_count") < 0).height
    if neg_quote == 0:
        ok("quote_count has no negative values")
    else:
        warn(f"{neg_quote:,} posts with quote_count < 0 (Bluesky API bug, drop in analysis)")

    # Date sanity
    ancient_posts = posts.filter(
        pl.col("post_created_at") < datetime(2023, 1, 1, tzinfo=timezone.utc)
    ).height
    if ancient_posts == 0:
        ok("No posts dated before 2023")
    else:
        warn(f"{ancient_posts:,} posts with clearly-bogus timestamps")

    future_posts = posts.filter(pl.col("post_created_at") > now).height
    if future_posts == 0:
        ok("No posts dated in the future")
    else:
        warn(f"{future_posts:,} posts dated in the future")

    # Stats summary
    print("\nPopularity distribution (like_count):")
    s = posts["like_count"]
    print(f"  min={s.min()}  median={s.median()}  mean={s.mean():.1f}  max={s.max():,}")
    print(f"  posts with 0 likes:  {(s == 0).sum():,}  ({(s == 0).sum()/len(posts)*100:.1f}%)")
    print(f"  posts with 1000+:    {(s >= 1000).sum():,}")
    print(f"  posts with 10000+:   {(s >= 10000).sum():,}")

# ============================================================================
# 5. USERS TABLE
# ============================================================================
section("5. users.parquet")

if not USERS_PATH.exists():
    fail("users.parquet missing")
else:
    users = pl.read_parquet(USERS_PATH)
    print(f"Rows: {len(users):,}")
    print(f"Size: {USERS_PATH.stat().st_size/1e6:.2f} MB")
    print(f"Schema: {dict(users.schema)}")

    # Nulls
    for col in users.columns:
        v = users[col].null_count()
        if v == 0:
            ok(f"  {col}: 0 nulls")
        else:
            warn(f"  {col}: {v:,} nulls")

    # Duplicate DIDs
    dup_users = (users.group_by("did")
                      .agg(pl.len().alias("n"))
                      .filter(pl.col("n") > 1))
    if dup_users.height == 0:
        ok("did is unique across users.parquet")
    else:
        fail(f"{dup_users.height:,} duplicate did rows in users.parquet")

    # Coverage: every liker should be in users.parquet
    liker_dids = set(likes["liker_did"].unique().to_list())
    users_dids = set(users["did"].to_list())
    missing_likers = liker_dids - users_dids
    pct_missing_likers = len(missing_likers) / max(len(liker_dids), 1) * 100
    print(f"\nLikers not in users.parquet: {len(missing_likers):,}  ({pct_missing_likers:.3f}%)")
    if pct_missing_likers < 1:
        ok("Liker coverage is essentially complete")
    else:
        warn(f"Liker coverage gap of {pct_missing_likers:.2f}% — usually deactivated accounts")

    # Coverage: every post author should be in users.parquet
    if POSTS_PATH.exists():
        author_dids = set(posts["post_author_did"].drop_nulls().unique().to_list())
        missing_authors = author_dids - users_dids
        pct_missing_authors = len(missing_authors) / max(len(author_dids), 1) * 100
        print(f"Authors not in users.parquet: {len(missing_authors):,}  ({pct_missing_authors:.3f}%)")
        if pct_missing_authors < 1:
            ok("Author coverage is essentially complete")
        else:
            warn(f"Author coverage gap of {pct_missing_authors:.2f}%")

    # Stats
    print("\nFollower-count distribution:")
    s = users["followers_count"]
    print(f"  median={s.median()}  mean={s.mean():.1f}  max={s.max():,}")
    print(f"  users with 0 followers:    {(s == 0).sum():,}")
    print(f"  users with 1000+:          {(s >= 1000).sum():,}")
    print(f"  users with 100000+:        {(s >= 100000).sum():,}")

# ============================================================================
# 6. CROSS-TABLE INTEGRITY
# ============================================================================
section("6. CROSS-TABLE INTEGRITY")

# Every (liker_did, post_uri) in likes — does the author of post_uri (parsed from URI)
# match the post_author_did in posts.parquet?
print("Spot-checking URI-encoded author DIDs against posts.post_author_did...")
sample = likes.sample(n=min(1000, len(likes)), seed=42)
# at://did:plc:XXXX/app.bsky.feed.post/YYYY ->  authot did is the part between at:// and /app.bsky.feed.post
sample = sample.with_columns(
    pl.col("post_uri").str.extract(r"at://(did:[^/]+)/", 1).alias("uri_author")
)
joined = sample.join(posts.select(["post_uri", "post_author_did"]),
                     on="post_uri", how="left")
mismatch = joined.filter(
    pl.col("post_author_did").is_not_null() &
    (pl.col("uri_author") != pl.col("post_author_did"))
)
if mismatch.height == 0:
    ok(f"All {len(sample):,} sampled URIs have matching authors in posts.parquet")
else:
    fail(f"{mismatch.height:,} URI-author mismatches in sample")
    print(mismatch.head())

# Sanity: count of unique authors should be reasonable
unique_authors = posts["post_author_did"].n_unique() if POSTS_PATH.exists() else 0
unique_likers = likes["liker_did"].n_unique()
print(f"\nUnique authors in posts.parquet: {unique_authors:,}")
print(f"Unique likers in likes:          {unique_likers:,}")
print(f"Unique users in users.parquet:   {len(users) if USERS_PATH.exists() else 0:,}")

# ============================================================================
# 7. SUMMARY
# ============================================================================
section("7. SUMMARY")
print(f"Likes:         {len(likes):>15,} rows across {len(shards):,} shards")
print(f"Posts:         {len(posts):>15,} enriched")
print(f"Users:         {len(users):>15,} profiles")
print(f"Date range:    {min_ts} ->  {max_ts}")
print(f"Span:          {span_days:.1f} days")
print(f"Total on disk: {(total_mb + POSTS_PATH.stat().st_size/1e6 + USERS_PATH.stat().st_size/1e6):.1f} MB")
print()
print("Health check complete.")
