import { dataToPixel, type Bounds, type Rect } from "../../lib/coords.ts";

interface Props {
  handle: string | null;
  point: [number, number] | null; // resolved data coords, or null if absent
  bounds: Bounds | null;
  imgRect: Rect | null;
}

// Draws a ring + label at the selected handle's data point over the plot PNG.
// Format-agnostic: PlotPage resolves the point (from binary lookup) and passes
// it in. Renders nothing if the handle isn't on this plot or data isn't ready.
export function SvgPoint({ handle, point, bounds, imgRect }: Props) {
  if (!handle || !point || !bounds || !imgRect) return null;
  const { x, y } = dataToPixel(bounds, imgRect, point[0], point[1]);
  const PINK = "#ec4899";

  return (
    <g className="svg-point">
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
