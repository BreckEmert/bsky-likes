import { useEffect, useState } from "react";
import type { PlotConfig } from "../plots.config.ts";
import {
  containRect,
  dataToPixel,
  identityBounds,
  type Bounds,
} from "../lib/coords.ts";
import { useElementSize } from "../lib/useElementSize.ts";
import { useBounds } from "../lib/useBounds.ts";

interface Props {
  plot: PlotConfig;
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
}

// Debug overlay toggled by URL: "?debug" shows the image rect + a center
// crosshair; "?debug=X,Y" places the crosshair at data point (X, Y). Used to
// verify data->pixel alignment against a known point in a PNG (build step 2).
const params = new URLSearchParams(location.search);
const DEBUG = params.has("debug");
function debugPoint(): { x: number; y: number } | null {
  const v = params.get("debug");
  if (!v) return null;
  const [x, y] = v.split(",").map(Number);
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

export function PlotPage({ plot }: Props) {
  const [stageRef, stageSize] = useElementSize<HTMLDivElement>();
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const bounds = useBounds(plot.bounds);

  // Reset measured natural size when the plot (and thus the image) changes.
  useEffect(() => setNatural(null), [plot.id]);

  const imgRect = natural
    ? containRect(stageSize.width, stageSize.height, natural.w, natural.h)
    : null;

  // Real bounds.json once exported; identity fallback meanwhile so the overlay
  // plumbing is verifiable before the real PNGs/bounds exist.
  const effBounds: Bounds | null =
    bounds ?? (natural ? identityBounds(natural.w, natural.h) : null);

  const dp = debugPoint();
  const crosshair =
    DEBUG && imgRect && effBounds
      ? dataToPixel(
          effBounds,
          imgRect,
          dp ? dp.x : (effBounds.xMin + effBounds.xMax) / 2,
          dp ? dp.y : (effBounds.yMin + effBounds.yMax) / 2
        )
      : null;

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

      <div className="plotpage__stage" ref={stageRef}>
        {plot.image ? (
          <img
            key={plot.id}
            className="plotpage__image"
            src={plot.image}
            alt={plot.title}
            draggable={false}
            onLoad={(e) =>
              setNatural({
                w: e.currentTarget.naturalWidth,
                h: e.currentTarget.naturalHeight,
              })
            }
          />
        ) : (
          <div className="plotpage__placeholder">
            {/* HTML-only plot (e.g. leaderboards): no PNG. Real content (ranked
                lists / deck layers) is added in a later build step. */}
            <span>{plot.tabLabel} — built in a later step</span>
          </div>
        )}

        {/* Overlay: matches the displayed image rect; highlight layers (SVG /
            deck.gl) mount here in later steps. For now: optional debug aids. */}
        {imgRect && (
          <svg
            className="plotpage__overlay"
            width={stageSize.width}
            height={stageSize.height}
          >
            {DEBUG && (
              <rect
                x={imgRect.left}
                y={imgRect.top}
                width={imgRect.width}
                height={imgRect.height}
                fill="none"
                stroke="#1d9bf0"
                strokeDasharray="4 4"
                opacity={0.5}
              />
            )}
            {crosshair && (
              <g stroke="#ec4899" strokeWidth={2} fill="none">
                <line
                  x1={crosshair.x - 14}
                  y1={crosshair.y}
                  x2={crosshair.x + 14}
                  y2={crosshair.y}
                />
                <line
                  x1={crosshair.x}
                  y1={crosshair.y - 14}
                  x2={crosshair.x}
                  y2={crosshair.y + 14}
                />
                <circle cx={crosshair.x} cy={crosshair.y} r={11} />
              </g>
            )}
          </svg>
        )}
      </div>
    </main>
  );
}
