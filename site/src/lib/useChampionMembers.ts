import { useEffect, useState } from "react";
import { asset } from "./asset.ts";
import { parseHandles } from "./binary.ts";

// handle -> sub-community lookup for the champions tab's user-search. Lazy: only
// fetched once `enabled` flips true (i.e. the user actually focuses the search),
// so the ~3.4 MB handles.bin isn't pulled just for viewing the board.
export interface ChampionMembers {
  handles: string[]; // for the SearchBox autocomplete index
  subOf: Map<string, number>; // lowercased handle -> sub id
}

export function useChampionMembers(enabled: boolean): ChampionMembers | null {
  const [data, setData] = useState<ChampionMembers | null>(null);
  useEffect(() => {
    if (!enabled || data) return;
    let cancelled = false;
    Promise.all([
      fetch(asset("/explore/handles.bin")).then((r) => r.arrayBuffer()),
      fetch(asset("/explore/subs.bin")).then((r) => r.arrayBuffer()),
    ])
      .then(([hb, sb]) => {
        if (cancelled) return;
        const handles = parseHandles(hb);
        const subs = new Uint8Array(sb);
        const subOf = new Map<string, number>();
        for (let i = 0; i < handles.length; i++) {
          if (subs[i] !== 255) subOf.set(handles[i].toLowerCase(), subs[i]);
        }
        setData({ handles, subOf });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [enabled, data]);
  return data;
}
