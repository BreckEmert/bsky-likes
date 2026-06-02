import { useRef, useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

// A column-wide stack of layered chevrons ("<<<" turned to point vertically).
// White hairlines, no fill/box. Flipped to point up via CSS on the up variant.
function ChevronStack() {
  return (
    <svg className="seamchev__svg" viewBox="0 0 120 60" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="16,9 60,23 104,9" />
      <polyline points="16,27 60,41 104,27" />
      <polyline points="16,45 60,59 104,45" />
    </svg>
  );
}

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // One global selected handle, shared by the map and every plot (persists).
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);
  // Which boundary chevron is revealed: 'down' (shown in the plots, jumps down)
  // or 'up' (shown in the map, jumps up). Hovering one side reveals the OTHER
  // side's chevron near the seam.
  const [seamHover, setSeamHover] = useState<null | "down" | "up">(null);

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  const exploreRef = useRef<HTMLElement>(null);
  const plotsRef = useRef<HTMLElement>(null);
  const scrollTo = (r: React.RefObject<HTMLElement>) =>
    r.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="app">
      {/* Main page: the explorable t-SNE field of users. */}
      <section className="explore" ref={exploreRef}>
        <ExploreMap
          selectedHandle={selectedHandle}
          onSelectHandle={setSelectedHandle}
        />
        {/* Hover zone (map's bottom-left) -> reveals the DOWN chevron in the
            plots. Underneath the up-chevron, so it's only reached when hidden. */}
        <div
          className="seamzone seamzone--down"
          onMouseEnter={() => setSeamHover("down")}
          onMouseLeave={() => setSeamHover(null)}
        />
        {/* UP chevron lives here (map bottom); shown when hovering the plots. */}
        <button
          className={"seamchev seamchev--up" + (seamHover === "up" ? " is-on" : "")}
          aria-label="back up to the map"
          onMouseEnter={() => setSeamHover("up")}
          onMouseLeave={() => setSeamHover(null)}
          onClick={() => scrollTo(exploreRef)}
        >
          <ChevronStack />
        </button>
      </section>

      {/* Below: the premade plots, with a label on the left. */}
      <section className="plots" ref={plotsRef}>
        {/* Hover zone (plots' top-left) -> reveals the UP chevron in the map. */}
        <div
          className="seamzone seamzone--up"
          onMouseEnter={() => setSeamHover("up")}
          onMouseLeave={() => setSeamHover(null)}
        />
        {/* DOWN chevron lives here (plots top); shown when hovering the map. */}
        <button
          className={"seamchev seamchev--down" + (seamHover === "down" ? " is-on" : "")}
          aria-label="down to the premade plots"
          onMouseEnter={() => setSeamHover("down")}
          onMouseLeave={() => setSeamHover(null)}
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
