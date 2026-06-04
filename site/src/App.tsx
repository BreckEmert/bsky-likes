import { useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

// A wide stack of layered chevrons ("<<<" turned to point vertically). White
// hairlines, no fill/box. Points down by default (toward the plots); flipped to
// point up via CSS when we're viewing the plots (toward the map).
function ChevronStack() {
  return (
    <svg className="seambar__svg" viewBox="0 0 130 38" preserveAspectRatio="none" aria-hidden="true">
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
  // Which half has focus. There's no free scroll; you slide between the two by
  // clicking the persistent center bar (or a plot tab, which jumps to plots).
  const [view, setView] = useState<"map" | "plots">("map");

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];
  const toggle = () => setView((v) => (v === "map" ? "plots" : "map"));

  return (
    <div className={"app app--" + view}>
      {/* The two full-height panes, stacked; the stack slides up/down. */}
      <div className="stage">
        <section className="pane pane--map">
          <ExploreMap
            selectedHandle={selectedHandle}
            onSelectHandle={setSelectedHandle}
            framing={view === "plots" ? "pretty" : "user"}
          />
        </section>
        <section className="pane pane--plots">
          <PlotPage
            plot={active}
            selectedHandle={selectedHandle}
            onSelectHandle={setSelectedHandle}
          />
        </section>
      </div>

      {/* Persistent center bar: always on screen, rides from the bottom edge
          (map focus) to the top edge (plots focus). Holds the plot tabs (always
          reachable) + a long centered chevron that toggles the view. */}
      <div className="seambar">
        <button
          className="seambar__chev"
          aria-label={view === "map" ? "go down to the plots" : "back up to the map"}
          onClick={toggle}
        >
          <ChevronStack />
          <span className="seambar__hint">
            {view === "map" ? "the premade plots" : "back to the cluster map"}
          </span>
        </button>
        <TabBar
          plots={PLOTS}
          activeId={activeId}
          onSelect={(id) => {
            setActiveId(id);
            setView("plots");
          }}
        />
      </div>
    </div>
  );
}
