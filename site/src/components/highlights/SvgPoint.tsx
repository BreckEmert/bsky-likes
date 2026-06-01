import { dataToPixel, type Bounds, type Rect } from "../../lib/coords.ts";
import type { PointLookup } from "../../lib/useLookup.ts";

interface Props {
  handle: string | null;
  lookup: PointLookup | null;
  bounds: Bounds | null;
  imgRect: Rect | null;
}

// Draws a ring + label at the selected handle's data point over the plot PNG.
// Renders nothing if the handle isn't present on this plot, or data isn't ready.
// (Meant to be placed inside the PlotPage overlay <svg>.)
export function SvgPoint({ handle, lookup, bounds, imgRect }: Props) {
  if (!handle || !lookup || !bounds || !imgRect) return null;
  const xy = lookup[handle.toLowerCase()];
  if (!xy) return null;

  const { x, y } = dataToPixel(bounds, imgRect, xy[0], xy[1]);
  const PINK = "#ec4899";

  return (
    <g className="svg-point">
      {/* halo for contrast over the dense plot */}
      <circle cx={x} cy={y} r={13} fill="none" stroke="#0e1116" strokeWidth={5} opacity={0.85} />
      <circle cx={x} cy={y} r={13} fill="none" stroke={PINK} strokeWidth={2.5} />
      <circle cx={x} cy={y} r={2.5} fill={PINK} />
      <text
        x={x + 17}
        y={y - 12}
        fontSize={13}
        fontWeight={600}
        fill={PINK}
        stroke="#0e1116"
        strokeWidth={3}
        paintOrder="stroke"
      >
        @{handle}
      </text>
    </g>
  );
}
