# -*- coding: utf-8 -*-
"""Async HTTP client, DID->PDS resolution, generic pagination, timestamp parsing.

Single canonical copy of code that was duplicated across the four original
ingest scripts. Behavior is identical to those copies (the only original
quirk dropped here is a harmless over-indentation in bsky_ingest.py's get()).
"""
import asyncio
import json
from datetime import datetime, timezone

import httpx


class Client:
    def __init__(self, concurrency=8, user_agent="bsky-likes/0.1"):
        limits = httpx.Limits(max_connections=concurrency * 4,
                              max_keepalive_connections=concurrency * 2)
        self.http = httpx.AsyncClient(
            limits=limits, timeout=30.0,
            headers={"User-Agent": user_agent}
        )

    async def get(self, url, params=None, max_retries=5):
        for attempt in range(max_retries):
            try:
                r = await self.http.get(url, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if r.status_code in (502, 503, 504):
                    await asyncio.sleep(1.5 ** attempt)
                    continue
                if r.status_code in (400, 404):
                    return None
                r.raise_for_status()
                try:
                    return r.json()
                except (json.JSONDecodeError, ValueError):
                    # PDS returned 200 but body wasn't JSON (HTML error page,
                    # empty body, truncated response, etc.)
                    return None
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError,
                    httpx.ReadError, httpx.RemoteProtocolError):
                await asyncio.sleep(1.5 ** attempt)
                continue
            except httpx.HTTPStatusError:
                return None
        return None

    async def close(self):
        await self.http.aclose()


# ----------------------------------------------------------------------------
# DID -> PDS resolution (module-level cache, as in the originals)
# ----------------------------------------------------------------------------
_pds_cache = {}


async def resolve_pds(client, did):
    if did in _pds_cache:
        return _pds_cache[did]
    if did.startswith("did:plc:"):
        doc = await client.get(f"https://plc.directory/{did}")
    elif did.startswith("did:web:"):
        host = did[len("did:web:"):]
        doc = await client.get(f"https://{host}/.well-known/did.json")
    else:
        _pds_cache[did] = None
        return None
    if not doc:
        _pds_cache[did] = None
        return None
    pds = None
    for svc in doc.get("service", []):
        if svc.get("id") in ("#atproto_pds", "atproto_pds"):
            pds = svc.get("serviceEndpoint")
            break
    _pds_cache[did] = pds
    return pds


async def resolve_handle(client, handle, appview):
    data = await client.get(
        f"{appview}/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle})
    return data["did"] if data else None


# ----------------------------------------------------------------------------
# Generic cursor pagination
# ----------------------------------------------------------------------------
async def get_paginated(client, url, params, list_key, cap=None):
    out = []
    cursor = None
    while True:
        p = dict(params)
        p["limit"] = 100
        if cursor:
            p["cursor"] = cursor
        data = await client.get(url, params=p)
        if not data:
            break
        out.extend(data.get(list_key, []))
        cursor = data.get("cursor")
        if not cursor:
            break
        if cap and len(out) >= cap:
            break
    return out


# ----------------------------------------------------------------------------
# Timestamp parsing — the repeated fromisoformat + naive->UTC pattern
# ----------------------------------------------------------------------------
def parse_ts(created_at_str):
    """Parse an ISO timestamp string, coercing naive datetimes to UTC.

    Returns None on any failure (missing, empty, or malformed value). This
    matches the originals: like-pull loops skipped unparseable records, and
    enrichment stored None for them.
    """
    try:
        created_at = datetime.fromisoformat(
            (created_at_str or "").replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at
    except Exception:
        # Matches the originals' bare `except Exception`: never crash the pull
        # loop on a malformed/non-string createdAt — skip the record instead.
        return None
