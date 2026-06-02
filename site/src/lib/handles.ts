// Handle normalization + autocomplete search. Lookup keys are lowercased
// handles (e.g. "hankgreen.bsky.social"); the export lowercased them.

/** Strip a leading '@', lowercase, trim. */
export function normalizeQuery(q: string): string {
  return q.replace(/^@+/, "").trim().toLowerCase();
}

/**
 * Substring autocomplete over a handle list. Ranks prefix matches first, then
 * shorter handles, then alphabetical. Caps the scanned-match set so a short
 * query (matching tens of thousands) stays responsive at ~250k handles.
 */
export function searchHandles(
  index: string[],
  rawQuery: string,
  limit = 20,
  scanCap = 2000
): string[] {
  const q = normalizeQuery(rawQuery);
  if (q.length < 2) return [];
  const matches: string[] = [];
  for (let i = 0; i < index.length && matches.length < scanCap; i++) {
    // Skip "handle.invalid" — Bluesky's placeholder for accounts whose handle
    // didn't resolve at crawl time. It's a short prefix-match for "han/hand/
    // handle…", so it floods the dropdown mid-type (and isn't a real handle).
    if (index[i] === "handle.invalid") continue;
    if (index[i].includes(q)) matches.push(index[i]);
  }
  matches.sort((a, b) => {
    const ap = a.startsWith(q) ? 0 : 1;
    const bp = b.startsWith(q) ? 0 : 1;
    if (ap !== bp) return ap - bp;
    if (a.length !== b.length) return a.length - b.length;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  return matches.slice(0, limit);
}
