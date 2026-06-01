import { useEffect, useState } from "react";

export interface Region {
  id: number;
  name: string;
  x: number;
  y: number;
  size: number;
}

/** Load the named map regions (cluster centroids + labels) for the TextLayer. */
export function useRegions(): Region[] {
  const [regions, setRegions] = useState<Region[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch("/explore/regions.json")
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
