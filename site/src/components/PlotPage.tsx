import type { PlotConfig } from "../plots.config.ts";

interface Props {
  plot: PlotConfig;
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
}

// Step 1: render the title/subtitle header + a letterboxed background image.
// The highlight overlay (SVG / deck.gl), search box, and coordinate mapping
// are layered on in later steps; selectedHandle/onSelectHandle are threaded
// through now so the wiring is ready.
export function PlotPage({ plot }: Props) {
  return (
    <main className="plotpage">
      <header className="plotpage__header">
        <h1 className="plotpage__title">{plot.title}</h1>
        {plot.subtitle && (
          <p className="plotpage__subtitle">
            {plot.subtitle.split("\n").map((line, i) => (
              <span key={i} className="plotpage__subtitle-line">
                {line}
              </span>
            ))}
          </p>
        )}
      </header>

      <div className="plotpage__stage">
        {plot.image ? (
          <img
            className="plotpage__image"
            src={plot.image}
            alt={plot.title}
            draggable={false}
          />
        ) : (
          <div className="plotpage__placeholder">
            {/* HTML-only plot (e.g. leaderboards) — content added later */}
            <span>{plot.tabLabel}</span>
          </div>
        )}
      </div>
    </main>
  );
}
