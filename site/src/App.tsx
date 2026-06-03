import { useEffect, useRef, useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

// A column-wide stack of layered chevrons ("<<<" turned to point vertically).
// White hairlines, no fill/box. Flipped to point up via CSS on the up variant.
function ChevronStack() {
  return (
    <svg className="seamchev__svg" viewBox="0 0 130 38" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="14,6 65,15 116,6" />
      <polyline points="14,17 65,26 116,17" />
      <polyline points="14,28 65,37 116,28" />
    </svg>
  );
}

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // One global selected handle, shared by the map and every plot (persists).
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);
  // The boundary jump-chevrons. `nearSeam` = mouse is in the boundary row;
  // `seamZone` = which half you're mostly viewing (from scroll position). You
  // only get the chevron pointing to the OTHER half -- both appear only at the
  // awkward ~halfway scroll.
  const [nearSeam, setNearSeam] = useState(false);
  const [seamZone, setSeamZone] = useState<"map" | "plots" | "mid">("map");
  const showDown = nearSeam && seamZone !== "plots"; // map or mid -> offer "down"
  const showUp = nearSeam && seamZone !== "map"; //     plots or mid -> offer "up"

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  const exploreRef = useRef<HTMLElement>(null);
  const plotsRef = useRef<HTMLElement>(null);
  const scrollTo = (r: React.RefObject<HTMLElement>) =>
    r.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  // Track where the map/plots boundary sits in the viewport: high up = viewing
  // the plots, low down = viewing the map, middle = the awkward halfway.
  useEffect(() => {
    const onScroll = () => {
      const ex = exploreRef.current?.getBoundingClientRect();
      if (!ex) return;
      const r = ex.bottom / window.innerHeight; // 1 = boundary at viewport bottom
      setSeamZone(r > 0.7 ? "map" : r < 0.3 ? "plots" : "mid");
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <div className="app">
      {/* Main page: the explorable t-SNE field of users. */}
      <section className="explore" ref={exploreRef}>
        <ExploreMap
          selectedHandle={selectedHandle}
          onSelectHandle={setSelectedHandle}
        />
        {/* Full-width hover band along the map's bottom edge. */}
        <div
          className="seamzone seamzone--down"
          onMouseEnter={() => setNearSeam(true)}
          onMouseLeave={() => setNearSeam(false)}
        />
        {/* UP chevron lives here (map bottom); shown when going up. */}
        <button
          className={"seamchev seamchev--up" + (showUp ? " is-on" : "")}
          aria-label="back up to the map"
          onMouseEnter={() => setNearSeam(true)}
          onMouseLeave={() => setNearSeam(false)}
          onClick={() => scrollTo(exploreRef)}
        >
          <ChevronStack />
        </button>
      </section>

      {/* Below: the premade plots, with a label on the left. */}
      <section className="plots" ref={plotsRef}>
        {/* Full-width hover band along the plots' top edge. */}
        <div
          className="seamzone seamzone--up"
          onMouseEnter={() => setNearSeam(true)}
          onMouseLeave={() => setNearSeam(false)}
        />
        {/* DOWN chevron lives here (plots top); shown when going down. */}
        <button
          className={"seamchev seamchev--down" + (showDown ? " is-on" : "")}
          aria-label="down to the premade plots"
          onMouseEnter={() => setNearSeam(true)}
          onMouseLeave={() => setNearSeam(false)}
          onClick={() => scrollTo(plotsRef)}
        >
          <ChevronStack />
        </button>
        <div className="plots__label">
          Explore some
          <br />
          premade plots
          <br />
          with the data!
        </div>
        <div className="plots__main">
          {/* Selecting a tab jumps to the plot so the change is visible. */}
          <TabBar
            plots={PLOTS}
            activeId={activeId}
            onSelect={(id) => {
              setActiveId(id);
              scrollTo(plotsRef);
            }}
          />
          <PlotPage
            plot={active}
            selectedHandle={selectedHandle}
            onSelectHandle={setSelectedHandle}
          />
        </div>
      </section>
    </div>
  );
}
