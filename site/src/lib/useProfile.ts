import { useEffect, useState } from "react";

export interface Profile {
  handle: string;
  displayName: string;
  avatar: string | null;
  description: string;
  followersCount: number;
  followsCount: number;
  postsCount: number;
}

// Module-level cache so re-selecting a handle (or revisiting across tabs) never
// re-hits the network. Keyed by lowercased handle.
const cache = new Map<string, Profile | null>();
const APPVIEW = "https://public.api.bsky.app";

async function fetchProfile(handle: string): Promise<Profile | null> {
  const key = handle.toLowerCase();
  if (cache.has(key)) return cache.get(key)!;
  try {
    const r = await fetch(
      `${APPVIEW}/xrpc/app.bsky.actor.getProfile?actor=${encodeURIComponent(key)}`
    );
    if (!r.ok) {
      cache.set(key, null);
      return null;
    }
    const j = await r.json();
    const p: Profile = {
      handle: j.handle ?? key,
      displayName: j.displayName || j.handle || key,
      avatar: j.avatar ?? null,
      description: j.description ?? "",
      followersCount: j.followersCount ?? 0,
      followsCount: j.followsCount ?? 0,
      postsCount: j.postsCount ?? 0,
    };
    cache.set(key, p);
    return p;
  } catch {
    cache.set(key, null);
    return null;
  }
}

/**
 * Live profile for a handle (avatar/name/bio/counts), fetched lazily and cached.
 * Search-triggered for now; hover on dot plots will reuse this. Returns
 * { profile, loading }.
 */
export function useProfile(handle: string | null): {
  profile: Profile | null;
  loading: boolean;
} {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!handle) {
      setProfile(null);
      setLoading(false);
      return;
    }
    const key = handle.toLowerCase();
    if (cache.has(key)) {
      setProfile(cache.get(key)!);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setProfile(null);
    fetchProfile(key).then((p) => {
      if (!cancelled) {
        setProfile(p);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [handle]);

  return { profile, loading };
}
