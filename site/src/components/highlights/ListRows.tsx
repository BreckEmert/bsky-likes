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
  const inLists =
    !!sel &&
    (data.mostObscure.some((r) => r.handle === sel) ||
      data.mostMainstream.some((r) => r.handle === sel));

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
      {sel && !inLists && (
        <div className="listrows__note">
          @{sel} isn’t in the top or bottom {data.mostMainstream.length} (of{" "}
          {data.total.toLocaleString()} users)
        </div>
      )}
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
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
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
                  width: `${(Math.abs(r.value) / max) * 100}%`,
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
