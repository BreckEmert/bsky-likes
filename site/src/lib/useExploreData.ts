import { useEffect, useState } from "react";

export interface ExploreData {
  points: Float32Array; // [x0,y0,x1,y1,...] sorted by followers desc (LOD order)
  colors: Uint8Array; // [r,g,b,...] parallel
  handles: string[]; // parallel, lowercased
  index: Map<string, number>;
  n: number;
  bounds: { xMin: number; xMax: number; yMin: number; yMax: number };
}

function parseHandles(buf: ArrayBuffer): string[] {
  const dv = new DataView(buf);
  const count = dv.getUint32(0, true);
  const offsets = new Uint32Array(buf, 4, count + 1);
  const start = 4 + (count + 1) * 4;
  const u8 = new Uint8Array(buf);
  const dec = new TextDecoder();
  const out = new Array<string>(count);
  for (let i = 0; i < count; i++)
    out[i] = dec.decode(u8.subarray(start + offsets[i], start + offsets[i + 1]));
  return out;
}

/** Load the exploration map's binary point data (points + colors + handles). */
export function useExploreData(): ExploreData | null {
  const [data, setData] = useState<ExploreData | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/explore/points.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/colors.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/handles.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/meta.json").then((r) => r.json()),
    ])
      .then(([pb, cb, hb, meta]) => {
        if (cancelled) return;
        const handles = parseHandles(hb);
        const index = new Map<string, number>();
        for (let i = 0; i < handles.length; i++) index.set(handles[i], i);
        setData({
          points: new Float32Array(pb),
          colors: new Uint8Array(cb),
          handles,
          index,
          n: meta.numPoints,
          bounds: meta.bounds,
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return data;
}
