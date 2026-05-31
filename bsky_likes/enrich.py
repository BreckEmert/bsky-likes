# -*- coding: utf-8 -*-
"""Enrich posts and users via the public AppView (batched + concurrent).

Single copy of the async enrichment functions that were duplicated in the
initial / forward / backward ingest scripts. Row schemas are unchanged.
"""
import asyncio

from .client import parse_ts


async def enrich_posts(client, post_uris, appview, concurrency=4, log_every=100):
    print(f"Enriching {len(post_uris):,} posts...")
    sem = asyncio.Semaphore(concurrency)
    out = []
    BATCH = 25
    uris = list(post_uris)

    async def fetch_batch(batch):
        async with sem:
            params = [("uris", u) for u in batch]
            data = await client.get(f"{appview}/xrpc/app.bsky.feed.getPosts",
                                    params=params)
            if not data:
                return []
            rows = []
            for p in data.get("posts", []):
                rec = p.get("record", {}) or {}
                created_at = parse_ts(rec.get("createdAt", ""))
                rows.append({
                    "post_uri": p.get("uri"),
                    "post_author_did": (p.get("author") or {}).get("did"),
                    "post_created_at": created_at,
                    "like_count": p.get("likeCount", 0),
                    "repost_count": p.get("repostCount", 0),
                    "reply_count": p.get("replyCount", 0),
                    "quote_count": p.get("quoteCount", 0),
                })
            return rows

    tasks = [fetch_batch(uris[i:i+BATCH]) for i in range(0, len(uris), BATCH)]
    done = 0
    for coro in asyncio.as_completed(tasks):
        rows = await coro
        out.extend(rows)
        done += 1
        if done % log_every == 0:
            print(f"  [{done}/{len(tasks)}] posts enriched: {len(out):,}")
    return out


async def enrich_users(client, user_dids, appview, concurrency=4, log_every=100):
    print(f"Enriching {len(user_dids):,} users...")
    sem = asyncio.Semaphore(concurrency)
    out = []
    BATCH = 25
    dids = list(user_dids)

    async def fetch_batch(batch):
        async with sem:
            params = [("actors", d) for d in batch]
            data = await client.get(f"{appview}/xrpc/app.bsky.actor.getProfiles",
                                    params=params)
            if not data:
                return []
            rows = []
            for p in data.get("profiles", []):
                rows.append({
                    "did": p.get("did"),
                    "handle": p.get("handle"),
                    "followers_count": p.get("followersCount", 0),
                    "follows_count": p.get("followsCount", 0),
                    "posts_count": p.get("postsCount", 0),
                })
            return rows

    tasks = [fetch_batch(dids[i:i+BATCH]) for i in range(0, len(dids), BATCH)]
    done = 0
    for coro in asyncio.as_completed(tasks):
        rows = await coro
        out.extend(rows)
        done += 1
        if done % log_every == 0:
            print(f"  [{done}/{len(tasks)}] users enriched: {len(out):,}")
    return out
