import { useEffect, useState } from "react";
import { asset } from "./asset.ts";

export type ChampClass = "upper" | "middle" | "lower";

export interface Champion {
  handle: string;
  subName: string; // the finer-grained community this account owns (e.g. "Atproto Tinkerers")
  subSize: number; // users in the community this account owns
  supporters: number; // distinct members who like them
  lift: number; // how much more this community likes them vs everyone
  followers: number;
  class: ChampClass;
}

export interface ChampTopic {
  topic: number;
  name: string;
  color: [number, number, number];
  champions: Champion[];
}

// "By community" view: one fine-grained sub-community + its top-K champions (by lift).
export interface CommunityChampion {
  handle: string;
  supporters: number;
  lift: number;
  followers: number;
  class: ChampClass;
}
export interface Community {
  sub: number;
  name: string;
  topic: number;
  color: [number, number, number];
  subSize: number;
  champions: CommunityChampion[];
}

export interface ChampionsData {
  totalUsers: number;
  classCounts: Record<ChampClass, number>;
  topics: ChampTopic[];
  communities: Community[];
}

/** Load champions.json (produced by export_champions.py) for the champions tab. */
export function useChampions(): ChampionsData | null {
  const [data, setData] = useState<ChampionsData | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(asset("/explore/champions.json"))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return data;
}

export const CLASS_COLOR: Record<ChampClass, string> = {
  upper: "#e8b84b", // famous — gold
  middle: "#1d9bf0", // the workhorses — pop blue
  lower: "#34d399", // tiny but devoted — green
};
export const CLASS_LABEL: Record<ChampClass, string> = {
  upper: "Upper class (famous)",
  middle: "Middle class (workhorses)",
  lower: "Lower class (niche)",
};
