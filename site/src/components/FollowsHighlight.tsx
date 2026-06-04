import { useState } from "react";
import type { PointData } from "../lib/binary.ts";
import { resolveHandle, getFollows } from "../lib/bsky.ts";

export interface FollowPicks {
  user: string | null; // the entered handle, if it's on the plot
  picks: string[]; // up to 15 sampled follows that are on the plot
}

interface Props {
  points: PointData | null; // the plot's handle set (top-4,000 accounts)
  onPicks: (p: FollowPicks) => void;
}

const N = 15;

function sample<T>(arr: T[], n: number): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a.slice(0, n);
}

// "Punch in your handle" -> highlights 15 random accounts you follow that are in
// the top-4,000 set, plus you. Re-roll for a fresh 15. All client-side against
// Bluesky's public API.
export function FollowsHighlight({ points, onPicks }: Props) {
  const [handle, setHandle] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [pool, setPool] = useState<string[]>([]); // follows present on the plot
  const [user, setUser] = useState<string | null>(null);

  const reshuffle = (p = pool, u = user) => {
    onPicks({ user: u, picks: sample(p, N) });
  };

  const run = async () => {
    if (!points || !handle.trim() || busy) return;
    setBusy(true);
    setStatus("looking you up…");
    try {
      const did = await resolveHandle(handle);
      setStatus("reading who you follow…");
      const follows = await getFollows(did);
      const present = [...new Set(follows.filter((h) => points.index.has(h)))];
      const me = handle.trim().replace(/^@+/, "").toLowerCase();
      const onPlot = points.index.has(me) ? me : null;
      setPool(present);
      setUser(onPlot);
      if (!present.length) {
        setStatus("none of your follows are in the top 4,000 — try a bigger account");
        onPicks({ user: onPlot, picks: [] });
      } else {
        setStatus(
          `${present.length} of your follows are here — showing ${Math.min(N, present.length)}`
        );
        reshuffle(present, onPlot);
      }
    } catch {
      setStatus("couldn’t find that handle");
      setPool([]);
      setUser(null);
      onPicks({ user: null, picks: [] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="followshl">
      <div className="followshl__row">
        <input
          className="followshl__input"
          placeholder="your @handle"
          value={handle}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          onChange={(e) => setHandle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") run();
          }}
        />
        <button className="followshl__btn" onClick={run} disabled={busy || !handle.trim()}>
          Highlight 15
        </button>
      </div>
      {pool.length > 0 && (
        <button className="followshl__shuffle" onClick={() => reshuffle()} disabled={busy}>
          🎲 shuffle 15 more
        </button>
      )}
      {status && <div className="followshl__status">{status}</div>}
    </div>
  );
}
