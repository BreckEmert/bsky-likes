import { useEffect, useState } from "react";
import { loadPointData, type PointData } from "./binary.ts";

/**
 * Load a plot's binary point data (handles + positions) given the two URLs.
 * Returns null while loading or when URLs are missing. Shared by svg-point and
 * deck.gl plots.
 */
export function usePointData(
  handlesUrl: string | undefined,
  positionsUrl: string | undefined
): PointData | null {
  const [data, setData] = useState<PointData | null>(null);

  useEffect(() => {
    setData(null);
    if (!handlesUrl || !positionsUrl) return;
    let cancelled = false;
    loadPointData(handlesUrl, positionsUrl)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [handlesUrl, positionsUrl]);

  return data;
}
