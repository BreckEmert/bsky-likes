import { useEffect, useRef, useState } from "react";
import { ProfileCard } from "./ProfileCard.tsx";

interface Props {
  handle: string | null; // selected handle -> profile card below the notes
  startOpen?: boolean; // expanded on mount (map gets true on desktop; others false)
}

// Shared top-right stack, rendered once PER PAGE (cluster map, champions, plots):
// the collapsible "Limitations & Notes" panel with the selected profile card
// flowing below it. Self-contained — no global state. Pinned to its page's
// top-right corner, immune to everything else on the page.
export function NotesPanel({ handle, startOpen = false }: Props) {
  const [open, setOpen] = useState(startOpen);
  // The FIRST profile selection (none -> selected) collapses the notes to clear
  // the top-right for the profile card; later selection changes don't.
  const prevSel = useRef<string | null>(handle);
  useEffect(() => {
    const was = prevSel.current;
    prevSel.current = handle;
    if (!was && handle) setOpen(false);
  }, [handle]);

  return (
    <div className="maptopright">
      <div
        className={"mapnotes" + (open ? " is-open" : "")}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
      >
        <div className="mapnotes__head">
          <span>Limitations &amp; Notes</span>
          <span className="mapnotes__chev">{open ? "–" : "+"}</span>
        </div>
        {open && (
          <ul className="mapnotes__list">
            <li>
              Each account is represented by <strong>who they like</strong>, not from{" "}
              <strong>what that account itself posts</strong>.
            </li>
            <li>
              Limited to <strong>my extended network</strong> (~221k accounts, two hops
              out), not all of Bluesky.
            </li>
            <li>
              <strong>English-language</strong> accounts only, it doesn't cluster as
              well otherwise.
            </li>
            <li>
              Data was collected over two separate pulls on different date windows.
              Counts may slightly differ if a popular post goes outside of those, sorry!
            </li>
            <li>
              Some viz drop low-signal accounts, e.g. the like/repost plot needs 1+
              repost per post and 5+ posts.
            </li>
            <li>
              Popularity numbers are over posts that got ≥1 like, so they
              overestimate small accounts.
            </li>
          </ul>
        )}
      </div>
      <ProfileCard handle={handle} />
    </div>
  );
}
