import { useEffect, useRef, useState, type RefObject } from "react";

/**
 * Track an element's content-box size, recomputed on resize via
 * ResizeObserver. Returns a ref to attach and the current {width, height}.
 * Used to fit plot overlays to the live container size.
 */
export function useElementSize<T extends HTMLElement>(): [
  RefObject<T>,
  { width: number; height: number }
] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Measure synchronously on mount so we have a correct size immediately,
    // not only after the ResizeObserver's first (sometimes delayed) callback.
    const r = el.getBoundingClientRect();
    setSize({ width: r.width, height: r.height });
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect;
      setSize({ width: cr.width, height: cr.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, size];
}
