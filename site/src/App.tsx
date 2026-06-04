import { useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

// A wide stack of layered chevrons pointing UP -- the single affordance to
// climb back from the plots to the map. White hairlines, no fill/box.
function ChevronStack() {
  return (
    <svg className="mapchev__svg" viewBox="0 0 140 18" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="16,8 70,3 124,8" />
      <polyline points="16,12 70,7 124,12" />
      <polyline points="16,16 70,11 124,16" />
    </svg>
  );
}

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // One global selected handle, shared by the map and every plot (persists).
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);
  // Which half is focused. No free scroll: the page is bounded so the map's
  // bottom and the plots' top (the tab bar) are always on screen. Clicking a
  // plot title focuses the plots; the map's hover-chevron climbs back up. The
  // only thing that animates is the deck camera (it reframes so the visible map
  // slice keeps your view instead of showing random bottom dots).
  const [view, setView] = useState<"map" | "plots">("map");

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  return (
    <div className={"app app--" + view}>
      <div className="stage">
        {/* Top: the explorable t-SNE field of users. */}
        <section className="explore">
          <ExploreMap
            selectedHandle={selectedHandle}
            onSelectHandle={setSelectedHandle}
            framing={view === "plots" ? "pretty" : "user"}
          />
          {/* The one chevron: centered in the map's bottom slice. Inert while
              the map is focused; when the plots are focused that slice sits at
              the top of the screen and hovering it reveals the climb-up arrow. */}
          <button
            className="mapchev"
            aria-label="back up to the map"
            onClick={() => setView("map")}
          >
            <ChevronStack />
          </button>
        </section>

        {/* Bottom: the premade plots, with the left label + tabs, as before. */}
        <section className="plots">
          <div className="plots__label">
            Explore some
            <br />
            premade plots
            <br />
            with the data!
          </div>
          <div className="plots__main">
            <TabBar
              plots={PLOTS}
              activeId={activeId}
              onSelect={(id) => {
                setActiveId(id);
                setView("plots");
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
    </div>
  );
}
