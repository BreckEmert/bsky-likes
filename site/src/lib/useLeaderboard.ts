import { useEffect, useState } from "react";
import { parseHandles } from "./binary.ts";

export interface LeaderRow {
  handle: string;
  value: number;
}
export interface LeaderboardData {
  mostMainstream: LeaderRow[]; // highest mean_log_popularity (likes the most viral)
  mostObscure: LeaderRow[]; // lowest (likes the most obscure)
  metric: string;
  total: number;
  /** every eligible handle, ranked desc (for search) */
  allHandles: string[];
  /** rank (1 = most viral) + value for any eligible handle, else null */
  rankOf(handle: string): { rank: number; value: number } | null;
}


/** Fetch leaderboards.json (the two columns) + the full ranked lookup. */
export function useLeaderboard(urls: {
  rows?: string;
  handles?: string;
  values?: string;
} | undefined): LeaderboardData | null {
  const [data, setData] = useState<LeaderboardData | null>(null);
  const rowsUrl = urls?.rows;
  const handlesUrl = urls?.handles;
  const valuesUrl = urls?.values;

  useEffect(() => {
    setData(null);
    if (!rowsUrl || !handlesUrl || !valuesUrl) return;
    let cancelled = false;
    Promise.all([
      fetch(rowsUrl).then((r) => r.json()),
      fetch(handlesUrl).then((r) => r.arrayBuffer()),
      fetch(valuesUrl).then((r) => r.arrayBuffer()),
    ])
      .then(([j, hb, vb]) => {
        if (cancelled) return;
        const allHandles = parseHandles(hb);
        const values = new Float32Array(vb);
        const index = new Map<string, number>();
        for (let i = 0; i < allHandles.length; i++) index.set(allHandles[i], i);
        setData({
          mostMainstream: j.mostMainstream,
          mostObscure: j.mostObscure,
          metric: j.metric,
          total: j.total,
          allHandles,
          rankOf(handle: string) {
            const i = index.get(handle.toLowerCase());
            return i === undefined ? null : { rank: i + 1, value: values[i] };
          },
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [rowsUrl, handlesUrl, valuesUrl]);

  return data;
}
