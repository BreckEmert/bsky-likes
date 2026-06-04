import { useEffect, useRef, useState } from "react";
import type { PointData } from "../lib/binary.ts";
import {
  resolveHandle,
  getFollows,
  searchActorsTypeahead,
  type ActorSuggestion,
} from "../lib/bsky.ts";

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
  // Live handle typeahead (Bluesky's own suggestions) as you type.
  const [suggest, setSuggest] = useState<ActorSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<number | undefined>(undefined);
  const seqRef = useRef(0); // drop out-of-order responses

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const onType = (v: string) => {
    setHandle(v);
    window.clearTimeout(debounceRef.current);
    const q = v.trim();
    if (q.length < 2) {
      setSuggest([]);
      setOpen(false);
      return;
    }
    const seq = ++seqRef.current;
    debounceRef.current = window.setTimeout(async () => {
      const res = await searchActorsTypeahead(q);
      if (seq === seqRef.current) {
        setSuggest(res);
        setOpen(res.length > 0);
      }
    }, 180);
  };

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
    <div className="followshl" ref={boxRef}>
      <div className="followshl__row">
        <div className="followshl__field">
          <input
            className="followshl__input"
            placeholder="your @handle"
            value={handle}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            onChange={(e) => onType(e.target.value)}
            onFocus={() => suggest.length > 0 && setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setOpen(false);
                run();
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
          />
          {open && suggest.length > 0 && (
            <ul className="followshl__list">
              {suggest.map((s) => (
                <li
                  key={s.handle}
                  className="followshl__item"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    setHandle(s.handle);
                    setSuggest([]);
                    setOpen(false);
                  }}
                >
                  {s.avatar ? (
                    <img className="followshl__avatar" src={s.avatar} alt="" />
                  ) : (
                    <span className="followshl__avatar followshl__avatar--blank" />
                  )}
                  <span className="followshl__sgh">@{s.handle}</span>
                  {s.displayName && (
                    <span className="followshl__sgn">{s.displayName}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
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
