import { useRef, useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // One global selected handle, shared by the map and every plot (persists).
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);

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
        {/* Hover the bottom edge -> a chevron bar inviting you down to the plots. */}
        <div className="seam seam--down" onClick={() => scrollTo(plotsRef)}>
          <div className="seam__bar">
            <i className="seam__chev" />
            <span>the premade plots</span>
            <i className="seam__chev" />
          </div>
        </div>
      </section>

      {/* Below: the premade plots, with a label on the left. */}
      <section className="plots" ref={plotsRef}>
        {/* Mirror: hover the top edge -> a chevron bar back up to the map. */}
        <div className="seam seam--up" onClick={() => scrollTo(exploreRef)}>
          <div className="seam__bar">
            <i className="seam__chev" />
            <span>back to the map</span>
            <i className="seam__chev" />
          </div>
        </div>
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
