import { useEffect, useRef } from "react";
import type { LeaderboardData, LeaderRow } from "../../lib/useLeaderboard.ts";

interface Props {
  data: LeaderboardData | null;
  selectedHandle: string | null;
}

const OBSCURE = "#10b981";
const VIRAL = "#f59e0b";

function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(Math.round(n));
}
// value = mean_log_popularity (natural log), so exp(value) = the typical like-count
// of the posts this user likes -- the meaningful unit for the axis + the readout.
// One decimal under 10 so the obscure end reads "1.5 .. 2.2" instead of "1 .. 2".
const likesAt = (v: number) => {
  const x = Math.exp(v);
  return x < 10 ? x.toFixed(1) : compact(x);
};
const range = (rows: LeaderRow[]) => {
  const vals = rows.map((r) => r.value);
  return { lo: Math.min(...vals), hi: Math.max(...vals) };
};

// Two ranked columns (most obscure / most viral taste). The selected handle's row
// is highlighted + scrolled into view; if it's not in either top/bottom 50, a band
// below the columns shows where it falls (rank + percentile + typical likes). Each
// column gets a small x-axis labeling the bar scale.
export function ListRows({ data, selectedHandle }: Props) {
  if (!data) return <div className="listrows__loading">loading…</div>;
  const sel = selectedHandle ? selectedHandle.toLowerCase() : null;
  const inList =
    !!sel &&
    (data.mostObscure.some((r) => r.handle === sel) ||
      data.mostMainstream.some((r) => r.handle === sel));
  const showFound = !!sel && !inList;
  const ranked = showFound ? data.rankOf(sel) : null;

  return (
    <div className="listrows">
      <div className="listrows__cols">
        <Column title="Likes the most obscure" accent={OBSCURE} rows={data.mostObscure} selected={sel} />
        <Column title="Likes the most viral" accent={VIRAL} rows={data.mostMainstream} selected={sel} />
      </div>

      <div className="listrows__foot">
        {showFound && <FoundBand handle={sel!} ranked={ranked} total={data.total} />}
        <div className="listrows__axes">
          <Axis accent={OBSCURE} {...range(data.mostObscure)} />
          <Axis accent={VIRAL} {...range(data.mostMainstream)} />
        </div>
      </div>
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
  // Scale bars to THIS column's value range so differences are visible (otherwise
  // the values are all close and every bar reads as ~full). lo->hi maps to the
  // bar region left->right, which is exactly what the axis below labels.
  const { lo, hi } = range(rows);
  const span = hi - lo || 1;
  const frac = (v: number) => 0.04 + 0.96 * ((v - lo) / span); // keep a sliver
  const selRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (selRef.current) selRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
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

// Small x-axis under a column. The bar length encodes value (lo->hi = left->right of
// the bar region), so label both ends with exp(value) = the typical like-count of
// posts these users like.
function Axis({ accent, lo, hi }: { accent: string; lo: number; hi: number }) {
  return (
    <div className="listaxis">
      <div className="listaxis__track">
        <span className="listaxis__tick" />
        <span className="listaxis__line" style={{ background: accent }} />
        <span className="listaxis__tick" />
      </div>
      <div className="listaxis__labels">
        <span>{likesAt(lo)}</span>
        <span className="listaxis__cap">avg likes on the posts they like</span>
        <span>{likesAt(hi)}</span>
      </div>
    </div>
  );
}

// Where a searched, out-of-top/bottom-50 user falls in the full ranking.
function FoundBand({
  handle,
  ranked,
  total,
}: {
  handle: string;
  ranked: { rank: number; value: number } | null;
  total: number;
}) {
  if (!ranked) {
    return (
      <div className="listfound listfound--none">
        @{handle} isn’t ranked yet (needs ≥50 likes)
      </div>
    );
  }
  // rank 1 = most viral; so (total - rank) accounts are more obscure than them.
  const pct = Math.max(1, Math.round(((total - ranked.rank) / total) * 100));
  return (
    <div className="listfound">
      <span className="listfound__h">@{handle}</span>
      <span className="listfound__rank">
        #{ranked.rank.toLocaleString()} <small>of {total.toLocaleString()}</small>
      </span>
      <span className="listfound__pct">more mainstream than {pct}%</span>
      <span className="listfound__likes">likes posts averaging ~{likesAt(ranked.value)} likes</span>
    </div>
  );
}
