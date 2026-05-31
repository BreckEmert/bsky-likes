import { useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";

export default function App() {
  const [activeId, setActiveId] = useState(PLOTS[0].id);
  // Selected handle is global so it persists across tabs (the defining feature).
  // Wired into highlight renderers in a later step.
  const [selectedHandle, setSelectedHandle] = useState<string | null>(null);

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  return (
    <div className="app">
      <TabBar plots={PLOTS} activeId={activeId} onSelect={setActiveId} />
      <PlotPage
        plot={active}
        selectedHandle={selectedHandle}
        onSelectHandle={setSelectedHandle}
      />
    </div>
  );
}
