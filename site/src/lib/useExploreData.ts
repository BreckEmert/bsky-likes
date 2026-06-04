import { useEffect, useState } from "react";
import { asset } from "./asset.ts";
import { expandHandle } from "./binary.ts";

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

// Display-only removals (no re-export needed). The cluster seeds are small
// outer islands -- we drop the seed + everything within a small radius of it;
// the individuals are dropped exactly. Calibrated to the map's x-span.
const REMOVE_CLUSTERS = [
  "jirkar.bsky.social",
  "elephantbike.bsky.social",
  "jeannedarquer.bsky.social",
  "benjoux.bsky.social",
  "ankelsocks.bsky.social",
  "fungistan.bsky.social",
  "vellure.bsky.social",
  "pompelo.bsky.social",
  "orifolger.bsky.social",
  "sykkelpippi.bsky.social",
];
const REMOVE_INDIVIDUALS = ["vdorr.bsky.social", "adraj.bsky.social"];
const REMOVE_RADIUS_FRAC = 0.035; // of x-span; these islands are isolated

interface RawData {
  points: Float32Array;
  colors: Uint8Array;
  colorsTopic: Uint8Array | null;
  handles: string[];
}

/** Drop the configured island clusters (by radius) + individuals (exact). */
function applyRemovals(
  d: RawData,
  bounds: { xMin: number; xMax: number }
): RawData {
  const { points, handles } = d;
  const idx = new Map<string, number>();
  for (let i = 0; i < handles.length; i++) idx.set(handles[i], i);
  const r = REMOVE_RADIUS_FRAC * (bounds.xMax - bounds.xMin);
  const r2 = r * r;
  const remove = new Uint8Array(handles.length);
  // Cluster seeds -> remove seed + neighbours within r.
  const seeds: Array<[number, number]> = [];
  for (const h of REMOVE_CLUSTERS) {
    const i = idx.get(h);
    if (i !== undefined) seeds.push([points[2 * i], points[2 * i + 1]]);
  }
  if (seeds.length) {
    for (let i = 0; i < handles.length; i++) {
      const x = points[2 * i];
      const y = points[2 * i + 1];
      for (const [sx, sy] of seeds) {
        const dx = x - sx;
        const dy = y - sy;
        if (dx * dx + dy * dy <= r2) {
          remove[i] = 1;
          break;
        }
      }
    }
  }
  // Individuals -> exact.
  for (const h of REMOVE_INDIVIDUALS) {
    const i = idx.get(h);
    if (i !== undefined) remove[i] = 1;
  }

  const keep: number[] = [];
  for (let i = 0; i < handles.length; i++) if (!remove[i]) keep.push(i);
  if (keep.length === handles.length) return d; // nothing matched

  const m = keep.length;
  const points2 = new Float32Array(m * 2);
  const colors2 = new Uint8Array(m * 3);
  const colorsTopic2 = d.colorsTopic ? new Uint8Array(m * 3) : null;
  const handles2 = new Array<string>(m);
  for (let j = 0; j < m; j++) {
    const i = keep[j];
    points2[2 * j] = points[2 * i];
    points2[2 * j + 1] = points[2 * i + 1];
    colors2[3 * j] = d.colors[3 * i];
    colors2[3 * j + 1] = d.colors[3 * i + 1];
    colors2[3 * j + 2] = d.colors[3 * i + 2];
    if (colorsTopic2 && d.colorsTopic) {
      colorsTopic2[3 * j] = d.colorsTopic[3 * i];
      colorsTopic2[3 * j + 1] = d.colorsTopic[3 * i + 1];
      colorsTopic2[3 * j + 2] = d.colorsTopic[3 * i + 2];
    }
    handles2[j] = handles[i];
  }
  return { points: points2, colors: colors2, colorsTopic: colorsTopic2, handles: handles2 };
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
    out[i] = expandHandle(dec.decode(u8.subarray(start + offsets[i], start + offsets[i + 1])));
  return out;
}

/** Load the exploration map's binary point data (points + colors + handles). */
export function useExploreData(): ExploreData | null {
  const [data, setData] = useState<ExploreData | null>(null);
  useEffect(() => {
    let cancelled = false;
    const opt = (url: string, kind: "buf" | "json") =>
      fetch(asset(url)).then((r) => (r.ok ? (kind === "buf" ? r.arrayBuffer() : r.json()) : null)).catch(() => null);
    // handles.bin is ~40% smaller now (".bsky.social" suffix stripped), so the
    // map's first load is already much lighter -- one fetch keeps deck's canvas
    // sizing happy (the deferred two-stage load raced the element measurement).
    Promise.all([
      fetch(asset("/explore/points.bin")).then((r) => r.arrayBuffer()),
      fetch(asset("/explore/colors.bin")).then((r) => r.arrayBuffer()),
      fetch(asset("/explore/handles.bin")).then((r) => r.arrayBuffer()),
      fetch(asset("/explore/meta.json")).then((r) => r.json()),
      opt("/explore/colors_topic.bin", "buf"),
      opt("/explore/topic_legend.json", "json"),
    ])
      .then(([pb, cb, hb, meta, ctb, legend]) => {
        if (cancelled) return;
        const f = applyRemovals(
          {
            points: new Float32Array(pb),
            colors: new Uint8Array(cb),
            colorsTopic: ctb ? new Uint8Array(ctb as ArrayBuffer) : null,
            handles: parseHandles(hb),
          },
          meta.bounds
        );
        const index = new Map<string, number>();
        for (let i = 0; i < f.handles.length; i++) index.set(f.handles[i], i);
        setData({
          points: f.points,
          colors: f.colors,
          colorsTopic: f.colorsTopic,
          legend: (legend as TopicLegend[] | null) ?? null,
          handles: f.handles,
          index,
          n: f.handles.length,
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
