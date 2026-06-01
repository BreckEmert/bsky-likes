import { dataToPixel, type Bounds, type Rect } from "../../lib/coords.ts";
import type { HistData } from "../../lib/useHistograms.ts";

interface Props {
  handle: string | null;
  density: Float32Array | null; // de-quantized per-bin density, or null
  hist: HistData | null; // for bin geometry
  bounds: Bounds | null;
  imgRect: Rect | null;
}

// Draws the selected user's popularity histogram as a bold blue polyline over
// the faint pre-rendered mass. x = bin-center (log value) via bounds [0,5];
// y = density via bounds [0,1.5] (clamped to match the PNG's ylim clip).
export function SvgLine({ handle, density, hist, bounds, imgRect }: Props) {
  if (!handle || !density || !hist || !bounds || !imgRect) return null;

  const { bins, xMinLog, xMaxLog } = hist;
  const step = (xMaxLog - xMinLog) / bins;
  const pts: string[] = [];
  for (let i = 0; i < bins; i++) {
    const xLogVal = xMinLog + (i + 0.5) * step;
    if (xLogVal < bounds.xMin || xLogVal > bounds.xMax) continue; // off-axis
    const y = Math.min(density[i], bounds.yMax); // clamp to ylim like the PNG
    const p = dataToPixel(bounds, imgRect, xLogVal, y);
    pts.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  }
  if (pts.length < 2) return null;
  const points = pts.join(" ");
  const BLUE = "#1d9bf0";

  return (
    <g className="svg-line">
      {/* dark halo behind for contrast over the faint mass */}
      <polyline points={points} fill="none" stroke="#0e1116" strokeWidth={5}
        strokeLinejoin="round" opacity={0.85} />
      <polyline points={points} fill="none" stroke={BLUE} strokeWidth={2.5}
        strokeLinejoin="round" />
    </g>
  );
}
