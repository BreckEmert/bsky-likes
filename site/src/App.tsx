import { useEffect, useRef, useState } from "react";
import { PLOTS } from "./plots.config.ts";
import { TabBar } from "./components/TabBar.tsx";
import { PlotPage } from "./components/PlotPage.tsx";
import { ExploreMap } from "./components/ExploreMap.tsx";
import { ChampionsView } from "./components/ChampionsView.tsx";
import type { MapView } from "./components/MapTitleSwitch.tsx";

// A wide stack of layered chevrons pointing UP -- the single affordance to
// climb back from the plots to the map. White hairlines, no fill/box.
function ChevronStack() {
  return (
    <svg className="mapchev__svg" viewBox="0 0 140 22" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="16,8 70,2.8 124,8" />
      <polyline points="16,14 70,8.8 124,14" />
      <polyline points="16,20 70,14.8 124,20" />
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
  // Which map view: the like-cluster field, or the champions tree.
  const [mapView, setMapView] = useState<MapView>("likes");

  // Slide the stack via the Web Animations API. A CSS transition on .stage gets
  // starved (frozen) because the constantly-repainting WebGL map inside it keeps
  // the transform off the GPU compositor; WAA animates the transform on the
  // compositor explicitly, so it stays smooth even while the map's camera fly-to
  // pegs the main thread. Concrete px (176 - viewportH) keeps it composited.
  const stageRef = useRef<HTMLDivElement>(null);
  const didMount = useRef(false);
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const to = view === "plots" ? 176 - window.innerHeight : 0;
    if (!didMount.current) {
      didMount.current = true;
      el.style.transform = `translateY(${to}px)`; // no animation on first paint
      return;
    }
    el.animate(
      [{ transform: getComputedStyle(el).transform }, { transform: `translateY(${to}px)` }],
      { duration: 850, easing: "cubic-bezier(.33,0,.2,1)", fill: "forwards" }
    );
    el.style.transform = `translateY(${to}px)`; // commit the end state
  }, [view]);

  const active = PLOTS.find((p) => p.id === activeId) ?? PLOTS[0];

  return (
    <div className={"app app--" + view}>
      <div className="stage" ref={stageRef}>
        {/* Top: the explorable t-SNE field of users, OR the champions tree. */}
        <section className="explore">
          {mapView === "likes" ? (
            <ExploreMap
              selectedHandle={selectedHandle}
              onSelectHandle={setSelectedHandle}
              framing={view === "plots" ? "pretty" : "user"}
              mapView={mapView}
              onSwitchView={setMapView}
            />
          ) : (
            <ChampionsView
              view={mapView}
              onSwitch={setMapView}
              selectedHandle={selectedHandle}
              onSelectHandle={setSelectedHandle}
            />
          )}
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
            Explore some premade
            <br />
            plots with the data!
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
