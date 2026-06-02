import { useEffect, useState } from "react";

export interface TopicLegend {
  id: number;
  name: string;
  color: [number, number, number];
  size: number;
}

export interface ExploreData {
  points: Float32Array; // [x0,y0,x1,y1,...] sorted by followers desc (LOD order)
  colors: Uint8Array; // position-continuum [r,g,b,...] parallel
  colorsTopic: Uint8Array | null; // per-point tier-1 topic color (2nd layer), or null
  legend: TopicLegend[] | null; // topic id -> name + color
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
    const opt = (url: string, kind: "buf" | "json") =>
      fetch(url).then((r) => (r.ok ? (kind === "buf" ? r.arrayBuffer() : r.json()) : null)).catch(() => null);
    Promise.all([
      fetch("/explore/points.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/colors.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/handles.bin").then((r) => r.arrayBuffer()),
      fetch("/explore/meta.json").then((r) => r.json()),
      opt("/explore/colors_topic.bin", "buf"),
      opt("/explore/topic_legend.json", "json"),
    ])
      .then(([pb, cb, hb, meta, ctb, legend]) => {
        if (cancelled) return;
        const handles = parseHandles(hb);
        const index = new Map<string, number>();
        for (let i = 0; i < handles.length; i++) index.set(handles[i], i);
        setData({
          points: new Float32Array(pb),
          colors: new Uint8Array(cb),
          colorsTopic: ctb ? new Uint8Array(ctb as ArrayBuffer) : null,
          legend: (legend as TopicLegend[] | null) ?? null,
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
