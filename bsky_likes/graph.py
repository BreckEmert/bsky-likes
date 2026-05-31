# -*- coding: utf-8 -*-
"""Set-A / set-B construction for the initial 2-hop crawl.

  set A = (your followers UNION your follows), filtered:
    - drop followers of mine with > MAX_FOLLOWERS_FOR_FOLLOWER_OF_MINE followers
    - drop follows of mine with > MAX_FOLLOWS_FOR_FOLLOW_OF_MINE follows
  set B = union of followers(a) for a in filtered A

Used only by the `initial` ingest mode. Logic is copied verbatim from the
original bsky_ingest.py.
"""
import asyncio

from . import config
from .client import get_paginated

APPVIEW = config.APPVIEW


async def build_set_A(client, my_did):
    print(f"Pulling your followers + follows for {my_did}...")
    followers_task = get_paginated(
        client, f"{APPVIEW}/xrpc/app.bsky.graph.getFollowers",
        {"actor": my_did}, "followers")
    follows_task = get_paginated(
        client, f"{APPVIEW}/xrpc/app.bsky.graph.getFollows",
        {"actor": my_did}, "follows")
    followers, follows = await asyncio.gather(followers_task, follows_task)
    follower_dids = [u["did"] for u in followers if u["did"] != my_did]
    follow_dids   = [u["did"] for u in follows   if u["did"] != my_did]
    print(f"  followers: {len(follower_dids)}, follows: {len(follow_dids)}")
    return follower_dids, follow_dids


async def fetch_profiles_for_dids(client, dids):
    out = {}
    BATCH = 25
    sem = asyncio.Semaphore(config.APPVIEW_CONCURRENCY)

    async def fetch_batch(batch):
        async with sem:
            params = [("actors", d) for d in batch]
            data = await client.get(f"{APPVIEW}/xrpc/app.bsky.actor.getProfiles",
                                    params=params)
            if not data:
                return []
            return data.get("profiles", [])

    tasks = [fetch_batch(dids[i:i+BATCH]) for i in range(0, len(dids), BATCH)]
    for coro in asyncio.as_completed(tasks):
        profiles = await coro
        for p in profiles:
            out[p["did"]] = p
    return out


def apply_A_filters(follower_profiles, follow_profiles):
    keep = []
    dropped_follower = []
    dropped_follow = []
    for did, p in follower_profiles.items():
        fc = p.get("followersCount", 0)
        if fc > config.MAX_FOLLOWERS_FOR_FOLLOWER_OF_MINE:
            dropped_follower.append((did, p.get("handle"), fc))
        else:
            keep.append(did)
    for did, p in follow_profiles.items():
        if did in follower_profiles:
            continue
        fc = p.get("followsCount", 0)
        if fc > config.MAX_FOLLOWS_FOR_FOLLOW_OF_MINE:
            dropped_follow.append((did, p.get("handle"), fc))
        else:
            keep.append(did)
    print(f"  filters: kept {len(keep)} A-users")
    print(f"  dropped {len(dropped_follower)} of your followers "
          f"(followers_count > {config.MAX_FOLLOWERS_FOR_FOLLOWER_OF_MINE}):")
    for did, handle, fc in sorted(dropped_follower, key=lambda x: -x[2])[:10]:
        print(f"    {handle:40s}  followers={fc:,}")
    print(f"  dropped {len(dropped_follow)} of your follows "
          f"(follows_count > {config.MAX_FOLLOWS_FOR_FOLLOW_OF_MINE}):")
    for did, handle, fc in sorted(dropped_follow, key=lambda x: -x[2])[:10]:
        print(f"    {handle:40s}  follows={fc:,}")
    return keep


async def get_followers_of(client, did, sem):
    async with sem:
        return await get_paginated(
            client, f"{APPVIEW}/xrpc/app.bsky.graph.getFollowers",
            {"actor": did}, "followers")


async def build_set_B(client, set_A):
    print(f"Building set B = union of followers of {len(set_A)} filtered A-users...")
    sem = asyncio.Semaphore(config.APPVIEW_CONCURRENCY)
    tasks = [get_followers_of(client, did, sem) for did in set_A]
    union = set()
    done = 0
    for coro in asyncio.as_completed(tasks):
        followers = await coro
        for u in followers:
            union.add(u["did"])
        done += 1
        if done % 5 == 0 or done == len(tasks):
            print(f"  [{done}/{len(tasks)}] |B| so far: {len(union):,}")
    print(f"  final |B|: {len(union):,}")
    return list(union)
