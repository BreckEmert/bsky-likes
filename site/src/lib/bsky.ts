// Tiny client for Bluesky's public AppView (unauthenticated, CORS-enabled) --
// just enough to resolve a handle and page through who they follow. Used by the
// "highlight people you follow" feature on the punching plot.

const API = "https://public.api.bsky.app/xrpc";

function cleanHandle(handle: string): string {
  return handle.trim().replace(/^@+/, "").toLowerCase();
}

export interface ActorSuggestion {
  handle: string;
  displayName?: string;
  avatar?: string;
}

/** Live handle suggestions as you type (Bluesky's own typeahead). */
export async function searchActorsTypeahead(
  q: string,
  limit = 8
): Promise<ActorSuggestion[]> {
  const query = cleanHandle(q);
  if (!query) return [];
  try {
    const r = await fetch(
      `${API}/app.bsky.actor.searchActorsTypeahead?q=${encodeURIComponent(query)}&limit=${limit}`
    );
    if (!r.ok) return [];
    const j = await r.json();
    return (j.actors ?? []).map(
      (a: { handle: string; displayName?: string; avatar?: string }) => ({
        handle: a.handle,
        displayName: a.displayName,
        avatar: a.avatar,
      })
    );
  } catch {
    return [];
  }
}

/** Resolve a handle (e.g. "hankgreen.bsky.social") to its DID. Throws if unknown. */
export async function resolveHandle(handle: string): Promise<string> {
  const h = cleanHandle(handle);
  const r = await fetch(
    `${API}/com.atproto.identity.resolveHandle?handle=${encodeURIComponent(h)}`
  );
  if (!r.ok) throw new Error("handle not found");
  const j = await r.json();
  if (!j.did) throw new Error("handle not found");
  return j.did as string;
}

/**
 * Fetch the handles a DID follows (lowercased), paging until exhausted or the
 * cap. getFollows is reverse-chronological, so a heavy follower is sampled, not
 * fully enumerated -- fine for "15 random". Cap keeps it snappy.
 */
export async function getFollows(did: string, maxPages = 15): Promise<string[]> {
  const out: string[] = [];
  let cursor: string | undefined;
  for (let p = 0; p < maxPages; p++) {
    const url =
      `${API}/app.bsky.graph.getFollows?actor=${encodeURIComponent(did)}&limit=100` +
      (cursor ? `&cursor=${encodeURIComponent(cursor)}` : "");
    const r = await fetch(url);
    if (!r.ok) break;
    const j = await r.json();
    for (const f of j.follows ?? []) if (f?.handle) out.push(f.handle.toLowerCase());
    cursor = j.cursor;
    if (!cursor) break;
  }
  return out;
}
