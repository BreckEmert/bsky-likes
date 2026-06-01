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
    let raf = 0;
    // Measure synchronously on mount; if layout isn't settled yet (size 0),
    // retry on a few animation frames. Some headless/embedded renderers don't
    // emit the ResizeObserver's initial callback, so we can't rely on it alone.
    const measure = () => {
      const r = el.getBoundingClientRect();
      if (r.width && r.height) setSize({ width: r.width, height: r.height });
      else raf = requestAnimationFrame(measure);
    };
    measure();
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect;
      if (cr.width && cr.height) setSize({ width: cr.width, height: cr.height });
    });
    ro.observe(el);
    const onResize = () => measure();
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return [ref, size];
}
