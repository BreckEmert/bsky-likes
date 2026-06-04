import { useEffect, useMemo, useRef, useState } from "react";
import { searchHandles } from "../lib/handles.ts";

interface Props {
  /** Searchable handle list for the active plot (lookup keys). */
  index: string[];
  /** Currently selected handle (persisted across tabs), or null. */
  selected: string | null;
  onSelect: (handle: string | null) => void;
}

// Search box with substring autocomplete. The chosen handle is the canonical
// lookup key, so it highlights consistently on every plot that has it.
export function SearchBox({ index, selected, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  const results = useMemo(
    () => (open ? searchHandles(index, query) : []),
    [index, query, open]
  );

  useEffect(() => setActive(0), [query]);

  // Reflect an externally-set selection (from another plot or the map) in the
  // box, so a searched handle is always visible instead of an empty prompt.
  useEffect(() => {
    setQuery(selected ?? "");
  }, [selected]);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function choose(handle: string) {
    onSelect(handle);
    setQuery(handle);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="searchbox" ref={boxRef}>
      <input
        className="searchbox__input"
        type="text"
        placeholder="search a handle…"
        value={query}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {selected && (
        <button
          className="searchbox__clear"
          title="clear selection"
          onClick={() => {
            onSelect(null);
            setQuery("");
          }}
        >
          ×
        </button>
      )}
      {open && results.length > 0 && (
        <ul className="searchbox__list">
          {results.map((h, i) => (
            <li
              key={h}
              className={"searchbox__item" + (i === active ? " is-active" : "")}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(h);
              }}
              onMouseEnter={() => setActive(i)}
            >
              @{h}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
