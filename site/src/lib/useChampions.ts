import { useEffect, useState } from "react";
import { asset } from "./asset.ts";

export type ChampClass = "upper" | "middle" | "lower";

// One champion carries the stats for EVERY lens, so the frontend can switch the
// displayed metric without refetching. `value` is the active lens's ranking value
// (used for the by-community bar width).
export interface Champion {
  handle: string;
  subName: string;
  subSize: number;
  followers: number;
  class: ChampClass;
  superfans: number; // members who liked >= fanMinLikes of their posts
  globalSuperfans: number; // their superfans across all communities
  share: number; // superfans here / globalSuperfans (0-1)
  lift: number;
  likeRate: number;
  value: number; // the active lens's ranking value (bar width)
}

export interface ChampTopic {
  topic: number;
  name: string;
  color: [number, number, number];
  champions: Champion[];
}
export interface Community {
  sub: number;
  name: string;
  topic: number;
  color: [number, number, number];
  subSize: number;
  champions: Champion[];
}
export interface Variant {
  classCounts: Record<ChampClass, number>;
  topics: ChampTopic[];
  communities: Community[];
}
export interface MetricMeta {
  id: string;
  label: string;
  blurb: string;
  default?: boolean;
}

export interface ChampionsData {
  totalUsers: number;
  fanMinLikes: number;
  metrics: MetricMeta[];
  variants: Record<string, Variant>;
  avatars?: Record<string, string>; // handle -> profile-picture URL
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
  upper: "Upper class",
  middle: "Middle class",
  lower: "Lower class",
};
// the parenthetical gloss, shown after the label on desktop and hidden on mobile
export const CLASS_PAREN: Record<ChampClass, string> = {
  upper: "famous",
  middle: "workhorses",
  lower: "niche",
};
