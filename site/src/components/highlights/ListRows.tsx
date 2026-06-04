import { useEffect, useRef } from "react";
import type { LeaderboardData, LeaderRow } from "../../lib/useLeaderboard.ts";

interface Props {
  data: LeaderboardData | null;
  selectedHandle: string | null;
}

// Two ranked columns (most obscure / most viral taste). The selected handle's
// row is highlighted and scrolled into view; if it's not in either top/bottom
// list, a note says so. Replaces a PNG for the leaderboards plot.
export function ListRows({ data, selectedHandle }: Props) {
  if (!data) return <div className="listrows__loading">loading…</div>;
  const sel = selectedHandle ? selectedHandle.toLowerCase() : null;

  // The "rank #N of M" readout now lives in PlotPage (below the search bar), so
  // it stays legible and off the lists.
  return (
    <div className="listrows">
      <Column
        title="Likes the most obscure"
        accent="#10b981"
        rows={data.mostObscure}
        selected={sel}
      />
      <Column
        title="Likes the most viral"
        accent="#f59e0b"
        rows={data.mostMainstream}
        selected={sel}
      />
    </div>
  );
}

function Column({
  title,
  accent,
  rows,
  selected,
}: {
  title: string;
  accent: string;
  rows: LeaderRow[];
  selected: string | null;
}) {
  // Scale bars to THIS column's value range so differences are visible
  // (otherwise the values are all close and every bar reads as ~full).
  const vals = rows.map((r) => r.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const frac = (v: number) => 0.04 + 0.96 * ((v - lo) / span); // keep a sliver
  const selRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (selRef.current) {
      selRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selected]);

  return (
    <div className="listcol">
      <h2 className="listcol__title" style={{ color: accent }}>
        {title}
      </h2>
      <ol className="listcol__list">
        {rows.map((r, i) => {
          const isSel = r.handle === selected;
          return (
            <li
              key={r.handle}
              ref={isSel ? selRef : undefined}
              className={"listrow" + (isSel ? " listrow--sel" : "")}
            >
              <span className="listrow__rank">{i + 1}</span>
              <span className="listrow__handle">@{r.handle}</span>
              <span
                className="listrow__bar"
                style={{
                  // Span between the handle's left (36px) and an 8px right
                  // margin so the bar never overflows the row (which used to
                  // trigger a horizontal scrollbar on the column).
                  width: `calc((100% - 44px) * ${frac(r.value)})`,
                  background: accent,
                }}
              />
            </li>
          );
        })}
      </ol>
    </div>
  );
}
