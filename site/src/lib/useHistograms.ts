import { useEffect, useState } from "react";

export interface HistData {
  bins: number;
  xMinLog: number;
  xMaxLog: number;
  /** de-quantized density for a handle's histogram, or undefined if absent */
  get(handle: string): Float32Array | undefined;
  handles: string[];
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

/**
 * Load per-user histograms for the svg-line plot (handles + uint8 histograms +
 * meta). De-quantizes density on access. Returns null until loaded.
 */
export function useHistograms(
  handlesUrl: string | undefined,
  histUrl: string | undefined,
  metaUrl: string | undefined
): HistData | null {
  const [data, setData] = useState<HistData | null>(null);

  useEffect(() => {
    setData(null);
    if (!handlesUrl || !histUrl || !metaUrl) return;
    let cancelled = false;
    Promise.all([
      fetch(handlesUrl).then((r) => r.arrayBuffer()),
      fetch(histUrl).then((r) => r.arrayBuffer()),
      fetch(metaUrl).then((r) => r.json()),
    ])
      .then(([hb, qb, meta]) => {
        if (cancelled) return;
        const handles = parseHandles(hb);
        const q = new Uint8Array(qb);
        const bins: number = meta.bins;
        const dmax: number = meta.densityMax;
        const index = new Map<string, number>();
        for (let i = 0; i < handles.length; i++) index.set(handles[i], i);
        setData({
          bins,
          xMinLog: meta.xMinLog,
          xMaxLog: meta.xMaxLog,
          handles,
          get(handle: string) {
            const i = index.get(handle.toLowerCase());
            if (i === undefined) return undefined;
            const out = new Float32Array(bins);
            for (let b = 0; b < bins; b++) out[b] = (q[i * bins + b] / 255) * dmax;
            return out;
          },
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [handlesUrl, histUrl, metaUrl]);

  return data;
}
