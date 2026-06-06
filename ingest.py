#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified Bluesky like-ingest CLI.

Subcommands:
  initial       Full 2-hop crawl: build set A -> B, pull <=200 likes/120d, enrich.
  forward       Pull NEW likes since each user's last captured timestamp.
  backward      Variable-cap backfill for heavy users with short spans.
  add-handles   Append likes for a hand-picked list of handles.

Replaces the four original scripts:
  initial      <- bsky_ingest.py
  forward      <- bsky_ingest_extend.py
  backward     <- bsky_ingest_uncap.py
  add-handles  <- bsky_ingest_supplement.py

The pull-loop / enrichment logic is unchanged — it lives in the bsky_likes
library. This file only parses arguments and wires the pieces together,
preserving each original mode's flow and console output.

Usage:
  python ingest.py initial [--test-seconds N]
  python ingest.py forward
  python ingest.py backward
  python ingest.py add-handles [HANDLE ...]
"""
import argparse
import asyncio
import datetime as _dt
import random
import time

import polars as pl

from bsky_likes import config, graph
from bsky_likes import likes as likes_mod
from bsky_likes.client import Client, resolve_handle
from bsky_likes.enrich import enrich_posts, enrich_users
from bsky_likes.state import load_state, save_state


# ============================================================================
# Shared incremental enrichment (forward + backward)
# ============================================================================
async def _enrich_incremental(client, likes_dir=None):
    """Enrich posts/authors discovered in the shards but absent from the
    enriched tables. Snapshot of existing posts is preserved (never re-fetched).
    Identical to the forward/backward enrichment phases in the originals.

    `likes_dir` defaults to LIKES_DIR; the sweep mode passes its own shard dir.
    """
    likes_dir = likes_dir or config.LIKES_DIR
    print("\n=== ENRICHMENT PHASE ===")
    all_likes = pl.scan_parquet(str(likes_dir / "part-*.parquet")).collect()
    all_post_uris = set(all_likes["post_uri"].to_list())

    existing_posts = pl.read_parquet(config.POSTS_PATH)
    existing_post_uris = set(existing_posts["post_uri"].to_list())
    new_post_uris = all_post_uris - existing_post_uris

    print(f"Total likes now:    {len(all_likes):,}")
    print(f"Total unique posts: {len(all_post_uris):,}")
    print(f"Already enriched:   {len(existing_post_uris):,}")
    print(f"NEW to enrich:      {len(new_post_uris):,}")

    if new_post_uris:
        new_post_rows = await enrich_posts(
            client, new_post_uris, config.APPVIEW, config.APPVIEW_CONCURRENCY)
        new_posts_df = pl.DataFrame(new_post_rows).cast(dict(existing_posts.schema))
        combined = pl.concat([existing_posts, new_posts_df])
        combined.write_parquet(config.POSTS_PATH, compression="zstd")
        print(f"posts.parquet now: {len(combined):,} rows")
    else:
        new_post_rows = []
        print("No new posts to enrich.")

    existing_users = pl.read_parquet(config.USERS_PATH)
    existing_user_dids = set(existing_users["did"].to_list())
    new_authors = {r["post_author_did"] for r in new_post_rows
                   if r.get("post_author_did")} - existing_user_dids

    print(f"\nNew post authors not yet in users.parquet: {len(new_authors):,}")
    if new_authors:
        new_user_rows = await enrich_users(
            client, new_authors, config.APPVIEW, config.APPVIEW_CONCURRENCY)
        new_users_df = pl.DataFrame(new_user_rows).cast(dict(existing_users.schema))
        combined_u = pl.concat([existing_users, new_users_df])
        combined_u.write_parquet(config.USERS_PATH, compression="zstd")
        print(f"users.parquet now: {len(combined_u):,} rows")


# ============================================================================
# MODE: initial  (was bsky_ingest.py)
# ============================================================================
async def run_initial_mode(args):
    config.PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    config.LIKES_DIR.mkdir(parents=True, exist_ok=True)

    client = Client(concurrency=config.CONCURRENCY, user_agent="bsky-likes-ingest/0.1")
    state = load_state(config.STATE_PATH, defaults={
        "shard_idx": 0, "set_A": None, "set_B": None,
        "my_did": None, "filters_applied": None})

    try:
        if not state.get("my_did"):
            data = await client.get(
                f"{config.APPVIEW}/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": config.MY_HANDLE})
            state["my_did"] = data["did"]
            save_state(config.STATE_PATH, state)
        my_did = state["my_did"]
        print(f"My DID: {my_did}")

        filters = [config.MAX_FOLLOWERS_FOR_FOLLOWER_OF_MINE,
                   config.MAX_FOLLOWS_FOR_FOLLOW_OF_MINE]
        if state.get("set_A") is None or state.get("filters_applied") != filters:
            follower_dids, follow_dids = await graph.build_set_A(client, my_did)
            all_A_dids = list(set(follower_dids) | set(follow_dids))
            print(f"Fetching profiles for {len(all_A_dids)} A-candidates...")
            profiles = await graph.fetch_profiles_for_dids(client, all_A_dids)
            follower_profiles = {d: profiles[d] for d in follower_dids if d in profiles}
            follow_profiles   = {d: profiles[d] for d in follow_dids   if d in profiles}
            set_A = graph.apply_A_filters(follower_profiles, follow_profiles)
            state["set_A"] = set_A
            state["filters_applied"] = filters
            state["set_B"] = None
            state["done_users"] = set()
            state["shard_idx"] = 0
            save_state(config.STATE_PATH, state)
        else:
            set_A = state["set_A"]
            print(f"Loaded |A| = {len(set_A)} from state (filters already applied)")

        if state.get("set_B") is None:
            set_B = await graph.build_set_B(client, set_A)
            state["set_B"] = set_B
            save_state(config.STATE_PATH, state)
        else:
            set_B = state["set_B"]
            print(f"Loaded |B| = {len(set_B):,} from state")

        rng = random.Random(42)
        rng.shuffle(set_B)

        cutoff = config.initial_window_cutoff()
        deadline = (time.time() + args.test_seconds) if args.test_seconds else None
        processed = await likes_mod.run_initial(
            client, set_B, state, config.STATE_PATH, cutoff, deadline=deadline)

        if args.test_seconds:
            print(f"\n=== TEST RUN COMPLETE ===")
            print(f"Processed {processed} users in {args.test_seconds}s")
            print(f"Likes shards in {config.LIKES_DIR}:")
            for f in sorted(config.LIKES_DIR.glob("*.parquet")):
                print(f"  {f.name}: {f.stat().st_size/1e6:.2f} MB")
            shards = list(config.LIKES_DIR.glob("*.parquet"))
            if shards:
                df = pl.scan_parquet([str(s) for s in shards]).collect()
                print(f"\nTotal likes captured: {len(df):,}")
                print(f"Unique likers:        {df['liker_did'].n_unique():,}")
                print(f"Unique posts liked:   {df['post_uri'].n_unique():,}")
                print(f"\nFirst few rows:")
                print(df.head().to_pandas().to_string())
                if processed > 0:
                    rate = processed / args.test_seconds
                    full_eta_hr = (len(set_B) - processed) / rate / 3600
                    avg_likes = len(df) / processed
                    proj_total = int(avg_likes * len(set_B))
                    print(f"\n=== PROJECTION FOR FULL RUN ===")
                    print(f"Rate: {rate:.2f} users/sec")
                    print(f"Avg likes/user (with cap+window): {avg_likes:.1f}")
                    print(f"Projected total likes: {proj_total:,}")
                    print(f"Projected ETA: {full_eta_hr:.1f}h")
            return

        # FULL RUN: enrichment
        print("\n=== ENRICHMENT PHASE ===", flush=True)
        shards = list(config.LIKES_DIR.glob("*.parquet"))
        print(f"Loading {len(shards):,} like shards from disk "
              "(no progress bar -- this can take a while)...", flush=True)
        df = pl.scan_parquet([str(s) for s in shards]).collect()
        print(f"Total likes loaded: {len(df):,}", flush=True)

        unique_posts = df["post_uri"].unique().to_list()
        posts_rows = await enrich_posts(
            client, unique_posts, config.APPVIEW, config.APPVIEW_CONCURRENCY)
        pl.DataFrame(posts_rows).write_parquet(config.POSTS_PATH, compression="zstd")
        print(f"posts.parquet written: {len(posts_rows):,} rows")

        author_dids = [r["post_author_did"] for r in posts_rows if r.get("post_author_did")]
        liker_dids = df["liker_did"].unique().to_list()
        all_dids = list(set(author_dids) | set(liker_dids))
        users_rows = await enrich_users(
            client, all_dids, config.APPVIEW, config.APPVIEW_CONCURRENCY)
        pl.DataFrame(users_rows).write_parquet(config.USERS_PATH, compression="zstd")
        print(f"users.parquet written: {len(users_rows):,} rows")

        print("\n=== DONE ===")
    finally:
        await client.close()


# ============================================================================
# MODE: forward  (was bsky_ingest_extend.py)
# ============================================================================
async def run_forward_mode(args):
    client = Client(concurrency=config.CONCURRENCY, user_agent="bsky-likes-extend/0.1")
    state = load_state(config.EXTEND_STATE_PATH, defaults={"shard_idx": None})

    try:
        print("Building per-user max-captured-timestamp from existing shards...")
        t0 = time.time()
        existing = (pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet"))
            .group_by("liker_did")
            .agg(pl.col("like_created_at").max().alias("max_captured"))
            .collect())
        print(f"  {len(existing):,} users with prior captures (took {time.time()-t0:.1f}s)")
        print(f"  global max captured: {existing['max_captured'].max()}")
        print(f"  global min captured: {existing['max_captured'].min()}")

        user_max_pairs = list(zip(
            existing["liker_did"].to_list(),
            existing["max_captured"].to_list(),
        ))

        rng = random.Random(42)
        rng.shuffle(user_max_pairs)

        if state.get("shard_idx") is None:
            existing_shards = sorted(config.LIKES_DIR.glob("part-*.parquet"))
            if existing_shards:
                state["shard_idx"] = int(existing_shards[-1].stem.split("-")[1]) + 1
            else:
                state["shard_idx"] = 0
            save_state(config.EXTEND_STATE_PATH, state)
            print(f"Starting new shards at index {state['shard_idx']:05d}")

        await likes_mod.run_forward(
            client, user_max_pairs, state, config.EXTEND_STATE_PATH)

        await _enrich_incremental(client)
        print("\n=== DONE ===")
    finally:
        await client.close()


# ============================================================================
# MODE: backward  (was bsky_ingest_uncap.py)
# ============================================================================
async def run_backward_mode(args):
    client = Client(concurrency=config.CONCURRENCY, user_agent="bsky-likes-uncap/0.1")
    state = load_state(config.UNCAP_STATE_PATH, defaults={"shard_idx": None})

    try:
        print("Computing per-user span from existing shards...")
        t0 = time.time()
        per_user = (pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet"))
            .group_by("liker_did")
            .agg([
                pl.len().alias("n_likes"),
                pl.col("like_created_at").max().alias("newest"),
                pl.col("like_created_at").min().alias("oldest"),
            ])
            .with_columns(
                ((pl.col("newest") - pl.col("oldest")).dt.total_seconds() / 86400)
                    .alias("span_days")
            )
            .filter(pl.col("n_likes") >= 200)   # only capped users
            .filter(pl.col("span_days") <= 28)  # only those with short span
            .collect())
        print(f"  {len(per_user):,} capped users with short spans "
              f"(took {time.time()-t0:.1f}s)")

        work_items = []
        for row in per_user.iter_rows(named=True):
            extra = likes_mod.cap_for_span(row["span_days"])
            if extra > 0:
                work_items.append((row["liker_did"], row["oldest"], extra))

        bucket_counts = {14: 0, 21: 0, 28: 0}
        for row in per_user.iter_rows(named=True):
            for t in [14, 21, 28]:
                if row["span_days"] <= t:
                    bucket_counts[t] += 1
                    break
        print(f"Bucket counts:")
        print(f"  span <= 14 days: {bucket_counts[14]:>6,} (extra cap = 300)")
        print(f"  span <= 21 days: {bucket_counts[21]:>6,} (extra cap = 200)")
        print(f"  span <= 28 days: {bucket_counts[28]:>6,} (extra cap = 100)")
        print(f"Total work items: {len(work_items):,}")

        rng = random.Random(42)
        rng.shuffle(work_items)

        if state.get("shard_idx") is None:
            existing_shards = sorted(config.LIKES_DIR.glob("part-*.parquet"))
            if existing_shards:
                state["shard_idx"] = int(existing_shards[-1].stem.split("-")[1]) + 1
            else:
                state["shard_idx"] = 0
            save_state(config.UNCAP_STATE_PATH, state)
            print(f"Starting new shards at index {state['shard_idx']:05d}")

        await likes_mod.run_backward(
            client, work_items, state, config.UNCAP_STATE_PATH, config.WINDOW_CUTOFF)

        await _enrich_incremental(client)
        print("\n=== DONE ===")
    finally:
        await client.close()


# ============================================================================
# MODE: add-handles  (was bsky_ingest_supplement.py)
# ============================================================================
async def run_add_handles_mode(args):
    handles = args.handles or config.SUPPLEMENT_HANDLES
    client = Client(concurrency=config.CONCURRENCY, user_agent="bsky-likes-supplement/0.1")

    try:
        print(f"Using WINDOW_CUTOFF = {config.WINDOW_CUTOFF.isoformat()}\n")

        print(f"Resolving {len(handles)} handles...")
        new_dids = []
        for h in handles:
            did = await resolve_handle(client, h, config.APPVIEW)
            if did:
                print(f"  {h} -> {did}")
                new_dids.append(did)
            else:
                print(f"  {h} -> NOT FOUND")

        print(f"\nPulling likes for {len(new_dids)} users...")
        sem = asyncio.Semaphore(config.CONCURRENCY)
        all_rows = []
        for did in new_dids:
            t0 = time.time()
            rows = await likes_mod.pull_initial(client, did, sem, config.WINDOW_CUTOFF)
            print(f"  {did[:30]}... -> {len(rows)} likes ({time.time()-t0:.1f}s)")
            all_rows.extend(rows)
        print(f"Total new likes: {len(all_rows):,}")

        if not all_rows:
            print("No likes captured. Exiting.")
            return

        # Write all new likes as a single shard at the next available index
        existing_shards = sorted(config.LIKES_DIR.glob("part-*.parquet"))
        next_idx = (int(existing_shards[-1].stem.split("-")[1]) + 1
                    if existing_shards else 0)
        likes_mod.flush_likes(all_rows, next_idx)

        # New posts not already enriched
        if config.POSTS_PATH.exists():
            existing_posts = pl.read_parquet(config.POSTS_PATH)
            existing_post_uris = set(existing_posts["post_uri"].to_list())
        else:
            existing_posts = None
            existing_post_uris = set()

        shard_uris = {r["post_uri"] for r in all_rows}
        new_post_uris = shard_uris - existing_post_uris
        print(f"\nNew posts to enrich: {len(new_post_uris):,}")
        print(f"(skipping {len(shard_uris & existing_post_uris):,} "
              f"already in posts.parquet)")

        new_post_rows = []
        if new_post_uris:
            new_post_rows = await enrich_posts(
                client, new_post_uris, config.APPVIEW, config.APPVIEW_CONCURRENCY)
            new_posts_df = pl.DataFrame(new_post_rows)
            if existing_posts is not None:
                new_posts_df = new_posts_df.cast(dict(existing_posts.schema))
                combined = pl.concat([existing_posts, new_posts_df])
            else:
                combined = new_posts_df
            combined.write_parquet(config.POSTS_PATH, compression="zstd")
            print(f"posts.parquet updated: {len(combined):,} rows")

        # New users = the new likers themselves + any newly-seen authors
        if config.USERS_PATH.exists():
            existing_users = pl.read_parquet(config.USERS_PATH)
            existing_user_dids = set(existing_users["did"].to_list())
        else:
            existing_users = None
            existing_user_dids = set()

        new_authors = {r["post_author_did"] for r in new_post_rows
                       if r.get("post_author_did")}
        new_user_dids = (set(new_dids) | new_authors) - existing_user_dids
        print(f"\nNew users to enrich: {len(new_user_dids):,}")

        if new_user_dids:
            new_user_rows = await enrich_users(
                client, new_user_dids, config.APPVIEW, config.APPVIEW_CONCURRENCY)
            new_users_df = pl.DataFrame(new_user_rows)
            if existing_users is not None:
                new_users_df = new_users_df.cast(dict(existing_users.schema))
                combined_u = pl.concat([existing_users, new_users_df])
            else:
                combined_u = new_users_df
            combined_u.write_parquet(config.USERS_PATH, compression="zstd")
            print(f"users.parquet updated: {len(combined_u):,} rows")

        print("\n=== DONE ===")
    finally:
        await client.close()


# ============================================================================
# MODE: sweep  (clean, uncapped pull back to --since)  --  NOT YET RUN
# ============================================================================
async def run_sweep_mode(args):
    """From-scratch UNCAPPED pull of every like back to --since, reusing the
    cached set_B population (no graph rebuild). Writes 4-column shards (with
    like_rkey) to a SEPARATE directory (SWEEP_LIKES_DIR) so they never mix with
    the existing capped 3-column shards in LIKES_DIR.

    NOTE: this mode has never been run. It is wired up and ready, but running
    it will issue a very large number of API requests — uncapped means heavy
    users contribute thousands of likes each, far more than the ~74M already
    captured. Existing posts.parquet/users.parquet are reused; only newly-seen
    posts/authors are enriched.
    """
    # Reuse the 2-hop population the initial crawl already resolved.
    init_state = load_state(config.STATE_PATH, defaults={
        "shard_idx": 0, "set_A": None, "set_B": None,
        "my_did": None, "filters_applied": None})
    set_B = init_state.get("set_B")
    if not set_B:
        raise SystemExit("No cached set_B in state.json — run `initial` first.")

    if args.since:
        since = _dt.datetime.fromisoformat(args.since).replace(tzinfo=_dt.timezone.utc)
    else:
        since = config.SWEEP_SINCE

    if args.targets == "clustered":
        # Only the users that landed in a community (cluster_members_sub). This is
        # ALL the champions board uses -- the other ~220k likers aren't in any
        # community, so their likes never enter a champion calc. ~half the work.
        targets = (pl.read_parquet(config.PROJECT_DIR / "cluster_members_sub.parquet")
                   .select("liker_did").unique()["liker_did"].to_list())
    elif args.targets == "known-likers":
        # Users with >=1 captured like already: cheaper (skips the ~420k empty
        # set-B users) and near-complete, but misses anyone who started liking
        # since the original crawl.
        targets = (pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet"))
                   .select("liker_did").unique().collect()["liker_did"].to_list())
    else:
        targets = list(set_B)

    out_dir = config.SWEEP_LIKES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    client = Client(concurrency=args.concurrency, user_agent="bsky-likes-sweep/0.1")
    state = load_state(config.SWEEP_STATE_PATH, defaults={"shard_idx": 0})
    try:
        print(f"Sweep: {len(targets):,} target users ({args.targets}), uncapped, "
              f"concurrency={args.concurrency}, back to {since.date()}  ->  {out_dir}")
        rng = random.Random(42)
        rng.shuffle(targets)

        await likes_mod.run_initial(
            client, targets, state, config.SWEEP_STATE_PATH, since,
            cap=float("inf"), out_dir=out_dir, concurrency=args.concurrency)

        # Enrich posts/users newly discovered in the sweep shards, reusing the
        # existing enriched tables.
        await _enrich_incremental(client, likes_dir=out_dir)
        print("\n=== DONE ===")
    finally:
        await client.close()


# ============================================================================
# CLI
# ============================================================================
def build_parser():
    p = argparse.ArgumentParser(
        description="Bluesky 2-hop like-ingest pipeline.")
    sub = p.add_subparsers(dest="mode", required=True)

    p_init = sub.add_parser(
        "initial", help="Full 2-hop crawl (build A->B, pull likes, enrich)")
    p_init.add_argument(
        "--test-seconds", type=int, default=None,
        help="Run for N seconds, then print a full-run projection instead of "
             "enriching (mirrors the old TEST_MODE).")

    sub.add_parser(
        "forward", help="Pull NEW likes since each user's last captured timestamp")
    sub.add_parser(
        "backward", help="Variable-cap backfill for heavy users with short spans")

    p_add = sub.add_parser(
        "add-handles", help="Append likes for specific handles")
    p_add.add_argument(
        "handles", nargs="*",
        help="Handles to add (default: config.SUPPLEMENT_HANDLES)")

    p_sweep = sub.add_parser(
        "sweep",
        help="Clean UNCAPPED pull back to --since, reusing set_B (NOT YET RUN)")
    p_sweep.add_argument(
        "--since", default=None,
        help="Backward cutoff date YYYY-MM-DD (default: config.SWEEP_SINCE, "
             "i.e. 2026-01-01).")
    p_sweep.add_argument(
        "--targets", choices=["all-b", "known-likers", "clustered"], default="known-likers",
        help="Which users to sweep. 'clustered' = only the ~221k users that landed "
             "in a community (all the champions board needs, ~half the work); "
             "'known-likers' = every user with >=1 captured like; 'all-b' = the "
             "full set B (includes ~420k empty users — slow).")
    p_sweep.add_argument(
        "--concurrency", type=int, default=24,
        help="Parallel request workers for the sweep (default 24; the client backs "
             "off on 429). Higher = faster but more rate-limit pressure.")

    return p


def main():
    args = build_parser().parse_args()
    runner = {
        "initial": run_initial_mode,
        "forward": run_forward_mode,
        "backward": run_backward_mode,
        "add-handles": run_add_handles_mode,
        "sweep": run_sweep_mode,
    }[args.mode]
    asyncio.run(runner(args))


if __name__ == "__main__":
    main()
