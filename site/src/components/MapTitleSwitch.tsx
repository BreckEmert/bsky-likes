export type MapView = "likes" | "champions";

interface Props {
  view: MapView;
  onSwitch: (v: MapView) => void;
  /** 0..1 — lets the caller fade the whole title (e.g. as the map zooms in). */
  opacity?: number;
}

// Shared header for the two map views. "Bluesky Users" stays put; the two
// subtitles sit side by side with a slash between -- the active one bright, the
// other faded and clickable, so it doubles as the tab switcher.
export function MapTitleSwitch({ view, onSwitch, opacity = 1 }: Props) {
  return (
    <div className="maptitle" style={{ opacity }} aria-hidden={opacity < 0.05}>
      <span className="maptitle__main">Bluesky Users</span>
      <div className="maptitle__subs">
        <button
          className={"maptitle__sub" + (view === "likes" ? " is-on" : "")}
          onClick={() => onSwitch("likes")}
        >
          clustered by who they like
        </button>
        <span className="maptitle__slash">/</span>
        <button
          className={"maptitle__sub" + (view === "champions" ? " is-on" : "")}
          onClick={() => onSwitch("champions")}
        >
          top accounts per topic
        </button>
      </div>
    </div>
  );
}
