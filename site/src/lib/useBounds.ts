import { useEffect, useState } from "react";
import type { Bounds } from "./coords.ts";

/**
 * Fetch a plot's `<plot>.bounds.json`. Returns null while loading, if no URL
 * is given, or if the file doesn't exist yet (the real exports aren't emitted
 * until bsky_export_web.py runs — callers fall back to identityBounds).
 */
export function useBounds(url: string | undefined): Bounds | null {
  const [bounds, setBounds] = useState<Bounds | null>(null);

  useEffect(() => {
    setBounds(null);
    if (!url) return;
    let cancelled = false;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (!cancelled) setBounds(json as Bounds | null);
      })
      .catch(() => {
        /* missing/unparseable bounds -> stay null, caller falls back */
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return bounds;
}
