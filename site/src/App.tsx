import { useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // One global selected handle, shared by the map and every plot (persists).
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  return (
    <div className="app">
      {/* Main page: the explorable t-SNE field of users. */}
      <section className="explore">
        <ExploreMap
          selectedHandle={selectedHandle}
          onSelectHandle={setSelectedHandle}
        />
      </section>

      {/* Below: the premade plots, with a label on the left. */}
      <section className="plots">
        <div className="plots__label">
          Explore some premade
          <br />
          plots with the data!
        </div>
        <div className="plots__main">
          <TabBar plots={PLOTS} activeId={activeId} onSelect={setActiveId} />
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
