import { useEffect, useState } from "react";

/** handle (lowercased) -> [x, y] in data units, matching the plot's axes. */
export type PointLookup = Record<string, [number, number]>;

/**
 * Fetch a JSON point-lookup (`<plot>.lookup.json`). Returns null while loading
 * or when no URL is given. Used by svg-point highlight plots (e.g. like-repost).
 */
export function useLookup(url: string | undefined): PointLookup | null {
  const [lookup, setLookup] = useState<PointLookup | null>(null);

  useEffect(() => {
    setLookup(null);
    if (!url) return;
    let cancelled = false;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (!cancelled) setLookup(json as PointLookup | null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [url]);

  return lookup;
}
