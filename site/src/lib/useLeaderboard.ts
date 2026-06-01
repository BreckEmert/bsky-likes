import { useEffect, useState } from "react";

export interface LeaderRow {
  handle: string;
  value: number;
}
export interface LeaderboardData {
  mostMainstream: LeaderRow[]; // highest mean_log_popularity (likes the most viral)
  mostObscure: LeaderRow[]; // lowest (likes the most obscure)
  metric: string;
  total: number;
}

/** Fetch leaderboards.json (ranked top/bottom rows). */
export function useLeaderboard(url: string | undefined): LeaderboardData | null {
  const [data, setData] = useState<LeaderboardData | null>(null);
  useEffect(() => {
    setData(null);
    if (!url) return;
    let cancelled = false;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!cancelled) setData(j as LeaderboardData | null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [url]);
  return data;
}
