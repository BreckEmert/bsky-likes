import { dataToPixel, type Bounds, type Rect } from "../../lib/coords.ts";

export interface HLPoint {
  handle: string;
  point: [number, number]; // data coords
  color: string;
  big?: boolean; // the "hero" (the searched user) -- a touch larger
}

interface Props {
  items: HLPoint[];
  bounds: Bounds | null;
  imgRect: Rect | null;
  compact?: boolean; // phones: smaller label font so the small plot isn't crowded
}

// Draws a ring + label for each highlighted point over the plot PNG. Same look
// as SvgPoint but for a set (the sampled follows in pink + the user in a
// distinct color).
export function SvgPoints({ items, bounds, imgRect, compact = false }: Props) {
  if (!bounds || !imgRect || !items.length) return null;
  const fs = compact ? { big: 11, normal: 9.5 } : { big: 13, normal: 11.5 };
  return (
    <g className="svg-points">
      {items.map((it) => {
        const { x, y } = dataToPixel(bounds, imgRect, it.point[0], it.point[1]);
        const r = it.big ? 13 : 9.5;
        return (
          <g key={it.handle}>
            <circle cx={x} cy={y} r={r} fill="none" stroke="#0e1116" strokeWidth={4.5} opacity={0.85} />
            <circle cx={x} cy={y} r={r} fill="none" stroke={it.color} strokeWidth={it.big ? 2.8 : 2.2} />
            <circle cx={x} cy={y} r={it.big ? 2.6 : 2.1} fill={it.color} />
            <text
              x={x + r + 4}
              y={y - r + 2}
              fontSize={it.big ? fs.big : fs.normal}
              fontWeight={it.big ? 700 : 600}
              fill={it.color}
              stroke="#0e1116"
              strokeWidth={3}
              paintOrder="stroke"
            >
              @{it.handle}
            </text>
          </g>
        );
      })}
    </g>
  );
}
