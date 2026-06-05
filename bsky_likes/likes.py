# -*- coding: utf-8 -*-
"""Like collection: per-user pull workers + their orchestration loops.

Three distinct pull strategies, kept as separate functions because their
stop conditions genuinely differ. The bodies are copied verbatim from the
original scripts; the only changes are lifting module globals to parameters:

  pull_initial   forward, newest-first, stop at `cutoff`        (bsky_ingest.py)
  pull_forward   forward, newest-first, stop at `since`         (bsky_ingest_extend.py)
  pull_backward  skip to `oldest_captured`, then walk older     (bsky_ingest_uncap.py)
                 until `cutoff` or `extra_cap`

flush_likes / shard indexing / checkpointing are shared.
"""
import asyncio
import time

import polars as pl

from . import config
from .client import resolve_pds, parse_ts
from .state import save_state

_LIKES_SCHEMA = {
    "liker_did": pl.Utf8,
    "post_uri": pl.Utf8,
    "like_created_at": pl.Datetime(time_zone="UTC"),
    # The like record's rkey (last segment of at://<did>/app.bsky.feed.like/<rkey>).
    # Usable directly as a listRecords cursor -> cheap backward extension later.
    # NOTE: absent from shards written before this column existed; the 3,168
    # current shards have only the first three columns. See
    # config.LIKES_RKEY_IN_EXISTING_SHARDS.
    "like_rkey": pl.Utf8,
}


def flush_likes(rows, shard_idx, out_dir=None):
    if not rows:
        return None
    out_dir = out_dir or config.LIKES_DIR
    df = pl.DataFrame(rows, schema=_LIKES_SCHEMA)
    out_path = out_dir / f"part-{shard_idx:05d}.parquet"
    df.write_parquet(out_path, compression="zstd")
    print(f"    -> flushed {len(rows):,} likes to {out_path.name} "
          f"({out_path.stat().st_size / 1e6:.1f} MB)")
    return out_path


def cap_for_span(span_days):
    """How many ADDITIONAL likes to pull for a user with this span (backward mode)."""
    for threshold, extra in config.CAP_BUCKETS:
        if span_days <= threshold:
            return extra
    return 0


# ============================================================================
# PER-USER PULL WORKERS
# ============================================================================
async def pull_initial(client, did, sem, cutoff, cap=None):
    """Most-recent likes, newest-first, stopping at `cutoff`.

    `cap` limits how many likes to keep (default config.LIKES_PER_USER_CAP).
    Pass float("inf") for an uncapped pull (used by the `sweep` mode).
    """
    if cap is None:
        cap = config.LIKES_PER_USER_CAP
    async with sem:
        pds = await resolve_pds(client, did)
        if not pds:
            return []
        rows = []
        cursor = None
        while len(rows) < cap:
            params = {"repo": did, "collection": "app.bsky.feed.like", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = await client.get(f"{pds}/xrpc/com.atproto.repo.listRecords",
                                    params=params)
            if not data:
                break
            records = data.get("records", [])
            if not records:
                break
            stop = False
            for rec in records:
                val = rec.get("value", {})
                created_at = parse_ts(val.get("createdAt", ""))
                if created_at is None:
                    continue
                if created_at < cutoff:
                    stop = True
                    break
                subject = val.get("subject", {})
                post_uri = subject.get("uri")
                if not post_uri:
                    continue
                rows.append({
                    "liker_did": did,
                    "post_uri": post_uri,
                    "like_created_at": created_at,
                    "like_rkey": rec.get("uri", "").rsplit("/", 1)[-1],
                })
                if len(rows) >= cap:
                    break
            if stop or len(rows) >= cap:
                break
            cursor = data.get("cursor")
            if not cursor:
                break
        return rows


async def pull_forward(client, did, since, sem):
    """Likes newer than `since`, newest-first, capped. Stops at a like <= since."""
    async with sem:
        pds = await resolve_pds(client, did)
        if not pds:
            return []
        rows = []
        cursor = None
        while len(rows) < config.LIKES_PER_USER_CAP:
            params = {"repo": did, "collection": "app.bsky.feed.like", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = await client.get(f"{pds}/xrpc/com.atproto.repo.listRecords",
                                    params=params)
            if not data:
                break
            records = data.get("records", [])
            if not records:
                break
            stop = False
            for rec in records:
                val = rec.get("value", {})
                created_at = parse_ts(val.get("createdAt", ""))
                if created_at is None:
                    continue
                # Stop at the boundary: anything <= since is already captured
                if created_at <= since:
                    stop = True
                    break
                subject = val.get("subject", {})
                post_uri = subject.get("uri")
                if not post_uri:
                    continue
                rows.append({
                    "liker_did": did,
                    "post_uri": post_uri,
                    "like_created_at": created_at,
                    "like_rkey": rec.get("uri", "").rsplit("/", 1)[-1],
                })
                if len(rows) >= config.LIKES_PER_USER_CAP:
                    break
            if stop or len(rows) >= config.LIKES_PER_USER_CAP:
                break
            cursor = data.get("cursor")
            if not cursor:
                break
        return rows


async def pull_backward(client, did, oldest_captured, extra_cap, sem, cutoff):
    """Likes OLDER than `oldest_captured`, up to `extra_cap`, stopping at `cutoff`.

    Walks listRecords newest->oldest: skips records >= oldest_captured (already
    have them), then collects older records until extra_cap or cutoff.
    """
    async with sem:
        pds = await resolve_pds(client, did)
        if not pds:
            return []
        rows = []
        cursor = None
        in_new_territory = False
        while len(rows) < extra_cap:
            params = {"repo": did, "collection": "app.bsky.feed.like", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = await client.get(f"{pds}/xrpc/com.atproto.repo.listRecords",
                                    params=params)
            if not data:
                break
            records = data.get("records", [])
            if not records:
                break
            stop = False
            for rec in records:
                val = rec.get("value", {})
                created_at = parse_ts(val.get("createdAt", ""))
                if created_at is None:
                    continue
                # Skip records we already have
                if not in_new_territory:
                    if created_at >= oldest_captured:
                        continue
                    in_new_territory = True
                # Now we're in new territory
                if created_at < cutoff:
                    stop = True
                    break
                subject = val.get("subject", {})
                post_uri = subject.get("uri")
                if not post_uri:
                    continue
                rows.append({
                    "liker_did": did,
                    "post_uri": post_uri,
                    "like_created_at": created_at,
                    "like_rkey": rec.get("uri", "").rsplit("/", 1)[-1],
                })
                if len(rows) >= extra_cap:
                    break
            if stop or len(rows) >= extra_cap:
                break
            cursor = data.get("cursor")
            if not cursor:
                break
        return rows


# ============================================================================
# ORCHESTRATORS (pull -> buffer -> flush shard -> checkpoint state)
# ============================================================================
async def run_initial(client, user_dids, state, state_path, cutoff,
                      deadline=None, cap=None, out_dir=None, concurrency=None):
    """Orchestrate the initial-style pull. `cap`/`out_dir` default to the
    standard cap and LIKES_DIR; the `sweep` mode passes cap=float("inf") and a
    separate out_dir for an uncapped crawl into its own shard directory.
    `concurrency` overrides config.CONCURRENCY (the sweep passes its --concurrency
    so the flag actually takes effect on the worker semaphore, not just the pool)."""
    sem = asyncio.Semaphore(concurrency or config.CONCURRENCY)
    pending = [d for d in user_dids if d not in state["done_users"]]
    print(f"Pulling likes for {len(pending):,} users "
          f"({len(state['done_users']):,} already done)...")

    buffer = []
    processed = 0
    start = time.time()
    win_t, win_n = start, 0   # window anchor for the INSTANTANEOUS rate (not cumulative)
    shard_idx = state.get("shard_idx", 0)

    async def worker(did):
        likes = await pull_initial(client, did, sem, cutoff, cap=cap)
        return did, likes

    tasks = [asyncio.create_task(worker(d)) for d in pending]
    try:
        for coro in asyncio.as_completed(tasks):
            did, likes = await coro
            buffer.extend(likes)
            state["done_users"].add(did)
            processed += 1

            if processed % 50 == 0:
                now = time.time()
                # instantaneous rate over the last window (the real current speed);
                # the cumulative avg only ever decays from the startup burst.
                inst = (processed - win_n) / (now - win_t) if now > win_t else 0.0
                avg = processed / (now - start) if now > start else 0.0
                eta_sec = (len(pending) - processed) / inst if inst > 0 else 0
                print(f"  [{processed}/{len(pending)}] "
                      f"likes buffered: {len(buffer):,}  "
                      f"rate: {inst:.1f}/s (avg {avg:.1f})  "
                      f"eta: {eta_sec/3600:.1f}h")
                win_t, win_n = now, processed

            # SAVE STATE rarely (it re-serializes the whole growing done_users
            # set, which blocks the event loop and drags the rate down as the set
            # grows). The buffer is a MEMORY GUARD, not the primary flush trigger:
            # at ~1k likes/user in the sweep, 500k likes ~= 500 users, so in
            # practice shards land on the CHECKPOINT_EVERY cadence (~every 500
            # users) -- ~10x fewer/bigger parquet writes than the old 50k buffer.
            # Raise/lower this to trade memory for write frequency.
            if len(buffer) >= 500_000:
                flush_likes(buffer, shard_idx, out_dir)
                shard_idx += 1
                state["shard_idx"] = shard_idx
                buffer = []
            if processed % config.CHECKPOINT_EVERY == 0:
                if buffer:
                    flush_likes(buffer, shard_idx, out_dir)
                    shard_idx += 1
                    state["shard_idx"] = shard_idx
                    buffer = []
                save_state(state_path, state)

            if deadline and time.time() > deadline:
                print(f"  [deadline reached at {processed} users] flushing and stopping")
                break
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        if buffer:
            flush_likes(buffer, shard_idx, out_dir)
            shard_idx += 1
            state["shard_idx"] = shard_idx
        save_state(state_path, state)
    return processed


async def run_forward(client, user_max_pairs, state, state_path):
    """user_max_pairs: list of (did, datetime) — user and their max captured ts."""
    sem = asyncio.Semaphore(config.CONCURRENCY)
    pending = [(d, ts) for d, ts in user_max_pairs if d not in state["done_users"]]
    print(f"Extending likes for {len(pending):,} users "
          f"({len(state['done_users']):,} already done this run)...")

    buffer = []
    processed = 0
    nonzero = 0
    start = time.time()
    shard_idx = state.get("shard_idx")  # set up by caller

    async def worker(did, since):
        likes = await pull_forward(client, did, since, sem)
        return did, likes

    tasks = [asyncio.create_task(worker(d, ts)) for d, ts in pending]
    try:
        for coro in asyncio.as_completed(tasks):
            did, likes = await coro
            if likes:
                buffer.extend(likes)
                nonzero += 1
            state["done_users"].add(did)
            processed += 1

            if processed % 100 == 0:
                elapsed = time.time() - start
                rate = processed / elapsed
                eta_sec = (len(pending) - processed) / rate if rate > 0 else 0
                print(f"  [{processed}/{len(pending)}] "
                      f"buffered: {len(buffer):,}  "
                      f"users w/ new likes: {nonzero:,}  "
                      f"rate: {rate:.1f}/s  "
                      f"eta: {eta_sec/60:.0f}m")

            if len(buffer) >= 50_000 or processed % config.CHECKPOINT_EVERY == 0:
                if buffer:
                    flush_likes(buffer, shard_idx)
                    shard_idx += 1
                    state["shard_idx"] = shard_idx
                    buffer = []
                save_state(state_path, state)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        if buffer:
            flush_likes(buffer, shard_idx)
            shard_idx += 1
            state["shard_idx"] = shard_idx
        save_state(state_path, state)
    print(f"\nUsers processed: {processed:,}  with new likes: {nonzero:,}")
    return processed, nonzero


async def run_backward(client, work_items, state, state_path, cutoff):
    """work_items: list of (did, oldest_captured_datetime, extra_cap)."""
    sem = asyncio.Semaphore(config.CONCURRENCY)
    pending = [w for w in work_items if w[0] not in state["done_users"]]
    print(f"Uncapping {len(pending):,} users "
          f"({len(state['done_users']):,} already done this run)...")

    buffer = []
    processed = 0
    nonzero = 0
    start = time.time()
    shard_idx = state["shard_idx"]

    async def worker(did, oldest, cap):
        likes = await pull_backward(client, did, oldest, cap, sem, cutoff)
        return did, likes

    tasks = [asyncio.create_task(worker(d, o, c)) for d, o, c in pending]
    try:
        for coro in asyncio.as_completed(tasks):
            did, likes = await coro
            if likes:
                buffer.extend(likes)
                nonzero += 1
            state["done_users"].add(did)
            processed += 1

            if processed % 100 == 0:
                elapsed = time.time() - start
                rate = processed / elapsed
                eta_sec = (len(pending) - processed) / rate if rate > 0 else 0
                print(f"  [{processed}/{len(pending)}] "
                      f"buffered: {len(buffer):,}  "
                      f"users w/ new likes: {nonzero:,}  "
                      f"rate: {rate:.1f}/s  "
                      f"eta: {eta_sec/60:.0f}m")

            if len(buffer) >= 50_000 or processed % config.CHECKPOINT_EVERY == 0:
                if buffer:
                    flush_likes(buffer, shard_idx)
                    shard_idx += 1
                    state["shard_idx"] = shard_idx
                    buffer = []
                save_state(state_path, state)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        if buffer:
            flush_likes(buffer, shard_idx)
            shard_idx += 1
            state["shard_idx"] = shard_idx
        save_state(state_path, state)
    print(f"\nUsers processed: {processed:,}  with new likes: {nonzero:,}")
    return processed
