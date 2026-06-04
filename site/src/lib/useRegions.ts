import { useEffect, useState } from "react";
import { asset } from "./asset.ts";

export interface Region {
  name: string;
  x: number;
  y: number;
  size: number;
  tier?: number; // 1 = broad (overview), 2 = finer (appears ~37% zoom)
}

/** Load the named map regions (cluster centroids + labels) for the TextLayer. */
export function useRegions(): Region[] {
  const [regions, setRegions] = useState<Region[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch(asset("/explore/regions.json"))
      .then((r) => r.json())
      .then((d: Region[]) => {
        if (!cancelled) setRegions(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return regions;
}
