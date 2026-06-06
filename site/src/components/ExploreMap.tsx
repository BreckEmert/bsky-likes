import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { OrthographicView, LinearInterpolator } from "@deck.gl/core";
import { ScatterplotLayer, BitmapLayer, TextLayer } from "@deck.gl/layers";
import { useExploreData } from "../lib/useExploreData.ts";
import { useRegions, type Region } from "../lib/useRegions.ts";
import { useElementSize } from "../lib/useElementSize.ts";
import { SearchBox } from "./SearchBox.tsx";
import { ProfileCard } from "./ProfileCard.tsx";
import { MapAtmosphere } from "./MapAtmosphere.tsx";
import { MapTitleSwitch, type MapView } from "./MapTitleSwitch.tsx";
import { asset } from "../lib/asset.ts";

interface Props {
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
  // "user" = leave the camera where the user left it; "pretty" = glide to a
  // preset framing (used while the plots are in focus). Switching back to
  // "user" restores exactly the view they were last on.
  framing?: "user" | "pretty";
  mapView: MapView;
  onSwitchView: (v: MapView) => void;
}

// When the plots take focus, only the bottom slice of the map stays on screen.
// We pan the camera DOWN by this many vh (keeping the user's x + zoom) so the
// content they had centered lands in that slice -- instead of whatever random
// dots happened to be at the bottom. When the plots take focus only the map's
// bottom ~tabbar-tall slice stays visible (at the TOP of the screen). To land
// the user's focal point in that slice we shift the camera target by the EXACT
// distance from the canvas center to the slice center: (viewportH - 2*tabbar)/2
// pixels, converted to world units (negative = y-down). Earlier magic "+35vh"
// overshot into the empty void below the data.
const TABBAR_PX = 88; // --tabbar-h (the peek slice height)
function sliceOffsetWorld(zoom: number): number {
  const px = (window.innerHeight - 2 * TABBAR_PX) / 2;
  return -px / Math.pow(2, zoom);
}

interface VS {
  target: [number, number, number];
  zoom: number;
}

// LOD: points.bin is STRATIFIED (blue-noise) order -- any prefix is spread
// evenly across the field, so the overview traces the whole footprint (and
// matches the color layer) instead of just the dense cores. We reveal more
// from one GPU buffer as you zoom (Theo's snappy pattern).
//   numVisible = LOD_BASE * growth^zoomDelta,  growth chosen so the count
//   reaches the full point set EXACTLY at the max zoom (zoomDelta == ZOOM_SPAN)
// -- a smooth ramp across the whole range, no single "everything appears" jump.
const LOD_BASE = 20000;   // overview ~= one point per occupied cell (even)
const ZOOM_SPAN = 6;      // max zoom == fit + ZOOM_SPAN (keep in sync below)
const MIN_ZOOM_PCT = 18;  // floor the zoom-out here (was the fit, 0%); too far out
const LOD_FULL_PCT = 63;  // zoom % at which the full point set is shown
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
// The map fly-to between map<->plots must use the SAME easing (and duration) as
// the section slide in App.tsx, or the camera lags the scrolling window. App's
// slide is CSS cubic-bezier(.33,0,.2,1); evaluate that exact curve here.
function cubicBezier(p1x: number, p1y: number, p2x: number, p2y: number) {
  const cx = 3 * p1x, bx = 3 * (p2x - p1x) - cx, ax = 1 - cx - bx;
  const cy = 3 * p1y, by = 3 * (p2y - p1y) - cy, ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  const dsx = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    let t = x;
    for (let i = 0; i < 6; i++) {
      const e = sx(t) - x;
      if (Math.abs(e) < 1e-5) break;
      const d = dsx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    return sy(clamp(t, 0, 1));
  };
}
const SLIDE_MS = 850; // keep in sync with App.tsx stage slide
const SLIDE_EASE = cubicBezier(0.33, 0, 0.2, 1); // keep in sync with App.tsx
// MONOTONIC label LOD: precompute, per label, the zoom at which it first stops
// overlapping every HIGHER-priority (bigger) label. Then at runtime show labels
// whose reveal-zoom <= current zoom. Zooming in only ever ADDS labels (never
// removes), so there's no flip-flop -- unlike a per-frame greedy declutter,
// which "frees" a small label whenever a bigger one happens to get dropped.
function labelReveals(labels: Region[], sizeBase: number): Map<Region, number> {
  const PAD = 6; // px breathing room
  const halfW = (r: Region) => {
    const fs = clamp(sizeBase + 3 * Math.log10(r.size), sizeBase, sizeBase + 12);
    return (r.name.length * fs * 0.52 + PAD) / 2; // pixels
  };
  const halfH = (r: Region) => {
    const fs = clamp(sizeBase + 3 * Math.log10(r.size), sizeBase, sizeBase + 12);
    return (fs + PAD) / 2; // pixels
  };
  const sorted = [...labels].sort((a, b) => b.size - a.size); // priority: bigger first
  const reveal = new Map<Region, number>();
  for (let i = 0; i < sorted.length; i++) {
    const L = sorted[i];
    let rz = -Infinity; // the biggest label always shows
    for (let j = 0; j < i; j++) {
      const H = sorted[j];
      const dx = Math.abs(L.x - H.x);
      const dy = Math.abs(L.y - H.y);
      // boxes overlap in x while zoom < log2((wL+wH)/dx); they separate (in 2D)
      // as soon as EITHER axis separates -> sep zoom = min(zx, zy).
      const zx = dx > 0 ? Math.log2((halfW(L) + halfW(H)) / dx) : Infinity;
      const zy = dy > 0 ? Math.log2((halfH(L) + halfH(H)) / dy) : Infinity;
      rz = Math.max(rz, Math.min(zx, zy));
    }
    reveal.set(L, rz);
  }
  return reveal;
}

// Hand-placed annotations for the empty "voids" in the like-space -- faint gray
// italic. (data coords, tune by eye.) The handles here are casual number-suffixed
// accounts with diffuse, mainstream likes -- no niche, hence the gap between the
// strong clusters. Shown at ALL zooms in the SAME gray styling + name (it persists
// when you zoom in instead of vanishing, but stays a gray annotation -- it does not
// brighten to white or rename to a community).
const VOID_LABELS: { name: string; x: number; y: number }[] = [
  { name: "The Normie Void", x: 1.4, y: 4.62 },
];

export function ExploreMap({ selectedHandle, onSelectHandle, framing = "user", mapView, onSwitchView }: Props) {
  const data = useExploreData();
  const regions = useRegions();
  // Reveal-zoom per label, computed once per tier (stable across pan/zoom).
  const reveals = useMemo(
    () => ({
      1: labelReveals(regions.filter((r) => (r.tier ?? 1) === 1), 13),
      2: labelReveals(regions.filter((r) => (r.tier ?? 1) === 2), 11),
    }),
    [regions]
  );
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [viewState, setViewState] = useState<VS | null>(null);
  const viewStateRef = useRef<VS | null>(null); // always-latest, for fly-to
  const flyingRef = useRef(false); // true during a fly-to transition (suppress echo/clamp)
  const savedViewRef = useRef<VS | null>(null); // the user's view, saved before a "pretty" reframe
  const framingMounted = useRef(false); // skip the initial framing effect run
  const fromDotRef = useRef(false); // true when the selection came from clicking a map dot
  const [hover, setHover] = useState<{ handle: string; x: number; y: number } | null>(null);
  const [colorMode, setColorMode] = useState<"continuum" | "topics">("topics");
  // top-right "Limitations & Notes" -- expanded on wide screens, collapsed to a
  // compact pill on narrower ones (<=1100px) where the centered title would
  // otherwise slide under the open panel.
  const [notesOpen, setNotesOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth > 1100
  );
  // Open the notes while the cluster map is the focused view; collapse them once
  // you drop into the plots (framing flips to "pretty"). Desktop only -- on
  // narrow/mobile it stays the compact pill. The panel itself is a fixed overlay,
  // unaffected by the map's pan/zoom/fly.
  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth <= 1100) return;
    setNotesOpen(framing !== "pretty");
  }, [framing]);
  // The FIRST profile selection (none -> selected) collapses the notes to clear
  // the top-right for the profile card; later selection changes don't.
  const prevSelRef = useRef<string | null>(selectedHandle);
  useEffect(() => {
    const was = prevSelRef.current;
    prevSelRef.current = selectedHandle;
    if (!was && selectedHandle) setNotesOpen(false);
  }, [selectedHandle]);
  const initialZoom = useRef(0);
  const minZoomRef = useRef(0);
  const [zoomRange, setZoomRange] = useState<{ min: number; max: number } | null>(null);

  // Fit the whole field once data + container size are known.
  useEffect(() => {
    if (!data || !size.width || !size.height || viewState) return;
    const { xMin, xMax, yMin, yMax } = data.bounds;
    const z =
      Math.log2(Math.min(size.width / (xMax - xMin), size.height / (yMax - yMin))) - 0.2;
    initialZoom.current = z; // detail (LOD/labels) stays anchored to the fit = 0%
    // Floor the zoom-OUT at MIN_ZOOM_PCT (the fit was too far out) and cap zoom-in
    // at the full span. Detail percentages still measure from the fit, so the
    // most-zoomed-out view looks exactly like today's 18%.
    const minZoom = z + (MIN_ZOOM_PCT / 100) * ZOOM_SPAN;
    minZoomRef.current = minZoom;
    setZoomRange({ min: minZoom, max: z + ZOOM_SPAN });
    const init: VS = { target: [(xMin + xMax) / 2, (yMin + yMax) / 2, 0], zoom: minZoom };
    viewStateRef.current = init;
    setViewState(init);
    // Arm the framing effect now that the map is ready -- otherwise its "skip the
    // first run" guard (which the async mount run never reaches) would eat the
    // user's FIRST plot click instead of the mount, leaving the slice on the
    // empty bottom of the field.
    framingMounted.current = true;
  }, [data, size, viewState]);

  // Center the selected handle. NEVER changes zoom (the user pans/zooms freely),
  // and clicking a dot on the map doesn't move at all -- it's already visible.
  // Only a SEARCH selection pans to bring the result on screen.
  useEffect(() => {
    if (!data || !viewState) return;
    const sel = selectedHandle?.toLowerCase();
    if (!sel || !data.index.has(sel)) return;
    if (fromDotRef.current) {
      fromDotRef.current = false; // clicked a visible dot -> just highlight it
      return;
    }
    const i = data.index.get(sel)!;
    const px = data.points[2 * i];
    const py = data.points[2 * i + 1];
    const zoom = viewStateRef.current?.zoom ?? viewState.zoom; // keep current zoom
    savedViewRef.current = { target: [px, py, 0], zoom };
    // While the plots are focused, only a slice of the map shows at the top, so
    // bias y by the slice shift to land the user inside it.
    const shift = framing === "pretty" ? sliceOffsetWorld(zoom) : 0;
    const dest: VS = { target: [px, py + shift, 0], zoom };
    flyingRef.current = true;
    setViewState({
      ...dest,
      transitionDuration: 750,
      transitionInterpolator: new LinearInterpolator(["target", "zoom"]),
      // Cubic ease-in-out -> a smooth bezier-ish glide from where the camera is
      // now straight to the target (no relocate, no overshoot).
      transitionEasing: (t: number) =>
        t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
      onTransitionEnd: () => {
        flyingRef.current = false;
        setViewState(dest);
      },
    } as never);
    // Safety: clear the flag even if the transition is interrupted.
    window.setTimeout(() => (flyingRef.current = false), 900);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedHandle, data]);

  // Reframe when navigating between the map and the plots. Heading to the
  // plots: remember the user's current view, then glide to the pretty preset.
  // Heading back: glide to exactly where they were. Reuses the fly-to machinery
  // (flyingRef suppresses the pan-clamp / frame echo during the glide).
  // useLayoutEffect (not useEffect) so the camera glide is kicked off in the
  // SAME frame the section starts sliding -> they animate together, not the map
  // lagging until the slide is nearly done.
  useLayoutEffect(() => {
    if (!data || !viewState) return;
    // Skip the first run (mount): don't reframe before the user navigates.
    if (!framingMounted.current) {
      framingMounted.current = true;
      return;
    }
    const b = data.bounds;
    let dest: VS;
    if (framing === "pretty") {
      const cur = viewStateRef.current ?? viewState;
      savedViewRef.current = cur;
      const sel = selectedHandle?.toLowerCase();
      if (sel && data.index.has(sel)) {
        // A profile is searched: center IT in the visible slice. At its (high)
        // zoom the slice offset is small, so it stays on the data.
        const i = data.index.get(sel)!;
        const dy = sliceOffsetWorld(cur.zoom);
        dest = {
          target: [data.points[2 * i], data.points[2 * i + 1] + dy, 0],
          zoom: cur.zoom,
        };
      } else {
        // No search: shift so the user's CENTER lands in the visible slice --
        // without this the slice shows the empty bottom of the field below them
        // (the "black window").
        const dy = sliceOffsetWorld(cur.zoom);
        dest = { target: [cur.target[0], cur.target[1] + dy, 0], zoom: cur.zoom };
      }
    } else {
      dest = savedViewRef.current ?? {
        target: [(b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2, 0],
        zoom: minZoomRef.current,
      };
    }
    flyingRef.current = true;
    setViewState({
      ...dest,
      transitionDuration: SLIDE_MS,
      transitionInterpolator: new LinearInterpolator(["target", "zoom"]),
      transitionEasing: SLIDE_EASE,
      onTransitionEnd: () => {
        flyingRef.current = false;
        setViewState(dest);
      },
    } as never);
    window.setTimeout(() => (flyingRef.current = false), 1000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [framing]);

  const zoomDelta = viewState ? Math.max(0, viewState.zoom - initialZoom.current) : 0;
  const numVisible = useMemo(() => {
    if (!data || !viewState) return 0;
    // growth so the count reaches data.n at LOD_FULL_PCT of the zoom range
    // (capped at data.n by the min() for any further zoom-in).
    const fullDelta = (LOD_FULL_PCT / 100) * ZOOM_SPAN;
    const growth = Math.pow(data.n / LOD_BASE, 1 / fullDelta);
    return Math.min(data.n, Math.round(LOD_BASE * Math.pow(growth, zoomDelta)));
  }, [data, viewState, zoomDelta]);
  // Tiny crisp dots at the overview (the density background carries the color
  // there); grow gently as you zoom in for hover/click. Halve them on phones --
  // the same pixel radius reads far too thick/bright on a small screen.
  const isMobile = size.width > 0 && size.width < 640;
  const mobileScale = isMobile ? 0.5 : 1;
  const pointRadius = clamp(0.35 + 0.45 * zoomDelta, 0.35, 4.5) * mobileScale;
  const zoomPct = Math.round((zoomDelta / ZOOM_SPAN) * 100);
  // Density-color background: full until ~15% zoom, then linear out to nothing
  // by ~50% (so ~62% at 27%, ~35% at 37%, ~11% at 46%), leaving just the dots.
  const FADE_START_PCT = 15;
  const FADE_END_PCT = 50;
  const bgOpacity =
    clamp((FADE_END_PCT - zoomPct) / (FADE_END_PCT - FADE_START_PCT), 0, 1) * 0.95;
  // Two label tiers across zoom, hard-swapped at ~36% (no fade -- a crisp cut
  // reads better than the crossfade). Tier 1 (broad) on the overview; tier 2
  // (finer sub-topics) once you've zoomed past the threshold.
  const TIER_SWAP_PCT = 36;
  // How far each label's topic color is pulled toward white. ~0.82 = mostly
  // white with a soft, recognizable hue.
  const LABEL_WHITE = 0.82;
  const tier1Opacity = zoomPct < TIER_SWAP_PCT ? 1 : 0;
  const tier2Opacity = zoomPct >= TIER_SWAP_PCT ? 1 : 0;
  // Glow edge: the single faint disc has a hard circular boundary that reads
  // crisp when zoomed in but harsh on the overview. Feather it as you zoom out
  // by stacking wider, fainter concentric haloes. 0 (clean line) at >=63% zoom,
  // ramping to full feather by ~18%.
  const GLOW_CLEAN_PCT = 75;
  const GLOW_SOFT_PCT = 18;
  const glowSpread = clamp(
    (GLOW_CLEAN_PCT - zoomPct) / (GLOW_CLEAN_PCT - GLOW_SOFT_PCT),
    0,
    1
  );
  // ONE circle drives both layers: `circle` is the glow/bloom radius, and the crisp
  // dot is a FRACTION of it (`dotPct`) that grows with zoom. So at low zoom the dot
  // is a small core inside a big topic bloom; as you zoom in the dot grows to fill
  // the circle and the glow recedes to a thin halo -> the point gets "specific".
  const circle = clamp(pointRadius * 3.5, 2.2 * mobileScale, 16) * 0.8;
  const dotPct = clamp(0.1 + zoomPct / 240, 0.1, 0.425);
  // Topic glow shrinks toward the crisp dot as you zoom IN, MEETING it (radius ==
  // dot radius, so the bloom vanishes) at GLOW_FADE_PCT. Below that it blooms; at or
  // above it only the specific dot shows. glowMul: ~1 zoomed out -> dotPct at >=60%.
  const GLOW_FADE_PCT = 60;
  const glowScale = clamp(
    (GLOW_FADE_PCT - zoomPct) / (GLOW_FADE_PCT - MIN_ZOOM_PCT),
    0,
    1
  );
  const glowMul = dotPct + (1 - dotPct) * glowScale;

  // The raw continuum palette reads a little flat, so push saturation up (more) and
  // brightness up (a bit less). Saturation = lerp away from per-pixel luminance.
  // Drives the Continuum dots, glow, AND the recolored legend keys below.
  const colorsBoosted = useMemo(() => {
    if (!data) return null;
    const SAT = 1.25, BRIGHT = 1.1;
    const src = data.colors, len = src.length;
    const out = new Uint8Array(len);
    const cl = (v: number) => (v < 0 ? 0 : v > 255 ? 255 : Math.round(v));
    for (let i = 0; i < len; i += 3) {
      const r = src[i], g = src[i + 1], b = src[i + 2];
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      out[i] = cl((lum + (r - lum) * SAT) * BRIGHT);
      out[i + 1] = cl((lum + (g - lum) * SAT) * BRIGHT);
      out[i + 2] = cl((lum + (b - lum) * SAT) * BRIGHT);
    }
    return out;
  }, [data]);

  // Per-topic average CONTINUUM color. In Continuum mode the legend keys recolor to
  // the gradient (each topic tinted by where its dots sit), so the same topic legend
  // stays useful in both modes. Keyed by the topic's "r,g,b" color string.
  const legendContinuum = useMemo(() => {
    if (!data?.legend || !data.colorsTopic) return null;
    const ct = data.colorsTopic, co = colorsBoosted ?? data.colors, n = data.n;
    const acc = new Map<string, [number, number, number, number]>();
    for (let i = 0; i < n; i++) {
      const k = ct[3 * i] + "," + ct[3 * i + 1] + "," + ct[3 * i + 2];
      let a = acc.get(k);
      if (!a) { a = [0, 0, 0, 0]; acc.set(k, a); }
      a[0] += co[3 * i]; a[1] += co[3 * i + 1]; a[2] += co[3 * i + 2]; a[3]++;
    }
    const out = new Map<string, [number, number, number]>();
    for (const [k, a] of acc)
      if (a[3]) out.set(k, [Math.round(a[0] / a[3]), Math.round(a[1] / a[3]), Math.round(a[2] / a[3])]);
    return out;
  }, [data, colorsBoosted]);

  const layers = useMemo(() => {
    if (!data || !numVisible) return [];
    const b = data.bounds;
    const continuum = colorsBoosted ?? data.colors;
    const activeColors =
      colorMode === "topics" && data.colorsTopic ? data.colorsTopic : continuum;
    // The GLOW uses a smoothed, locally-DOMINANT topic color in Topics mode, so a
    // few off-topic dots can't muddy a cluster's bloom (the crisp dots below keep
    // their true per-account color). Continuum keeps the (boosted) positional palette.
    const glowColors =
      colorMode === "topics"
        ? data.colorsTopicDom ?? data.colorsTopic ?? data.colors
        : continuum;
    const out: unknown[] = [
      // Smooth density-color field behind the dots; fades out as you zoom in.
      new BitmapLayer({
        id: "density",
        image: asset("/explore/density.png"),
        bounds: [b.xMin, b.yMin, b.xMax, b.yMax],
        opacity: bgOpacity,
        updateTriggers: { opacity: [bgOpacity] },
      }),
      // Soft glow: large, faint dots under the crisp points. Overlap in dense
      // clusters accumulates -> the cluster shapes softly bloom (structure-led).
      // Feather the hard outer edge INWARD as you zoom out, keeping the max glow
      // radius AND center brightness fixed: concentric discs that shrink inward
      // (glowSpread) so the outer annulus thins out -- removing glow from the
      // outside, not ballooning it. Clean single disc at >=63% zoom; soft by ~18%.
      // dot glow OFF on phones (quick patch to compare looks); desktop keeps it.
      ...(isMobile ? [] : (glowSpread <= 0.01
        ? [{ id: "glow", rMul: 1, op: 0.06 }]
        : [0, 0.22, 0.44, 0.66].map((k, idx) => ({
            id: idx === 0 ? "glow" : `glow-i${idx}`,
            rMul: 1 - k * glowSpread, // outer disc stays at R; the rest pull in
            op: 0.06 / 4, // 4 stacked -> ~same center alpha as the single 0.06 disc
          }))
      ).map(
        (g) =>
          new ScatterplotLayer({
            id: g.id,
            data: {
              length: numVisible,
              attributes: {
                getPosition: { value: data.points, size: 2 },
                getFillColor: { value: glowColors, size: 3 },
              },
            },
            getRadius: circle * glowMul * g.rMul,
            radiusUnits: "pixels",
            radiusMinPixels: 2.2 * mobileScale * glowMul * g.rMul,
            opacity: g.op,
            pickable: false,
            updateTriggers: {
              getRadius: [circle, glowSpread, glowMul],
              getFillColor: [colorMode],
            },
          })
      )),
      new ScatterplotLayer({
        id: "points",
        data: {
          length: numVisible,
          attributes: {
            getPosition: { value: data.points, size: 2 },
            getFillColor: { value: activeColors, size: 3 },
          },
        },
        // the crisp dot is a fraction of the same circle (grows with zoom), so
        // community colors stay visible inside the topic's dominant-colored bloom.
        getRadius: circle * dotPct,
        radiusUnits: "pixels",
        radiusMinPixels: 0.5 * mobileScale,
        opacity: 0.85,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 220],
        updateTriggers: { getRadius: [circle, dotPct], getFillColor: [colorMode] },
      }),
    ];
    const sel = selectedHandle?.toLowerCase();
    if (sel && data.index.has(sel)) {
      const i = data.index.get(sel)!;
      const selPos: [number, number] = [data.points[2 * i], data.points[2 * i + 1]];
      out.push(
        new ScatterplotLayer({
          id: "selection",
          data: [{ position: selPos }],
          getPosition: (d: { position: [number, number] }) => d.position,
          getRadius: 11,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: [236, 72, 153, 255],
          getLineWidth: 3,
          lineWidthUnits: "pixels",
          pickable: false,
        })
      );
    }
    // Region labels in two zoom-gated tiers (broad overview -> finer at ~37%).
    const labelTier = (tier: number, opacity: number, sizeBase: number, sizeScale = 1) => {
      if (!regions.length || opacity <= 0 || !viewState) return;
      const rz = reveals[tier as 1 | 2];
      const rs = regions.filter(
        (r) =>
          (r.tier ?? 1) === tier &&
          // tier-1 (broad overview labels) ALWAYS show -- positioned by their
          // manual offsets in regions.json, no auto-declutter. Only tier-2 keeps
          // the progressive zoom-reveal (there are ~49 of them).
          (tier !== 1 ? (rz.get(r) ?? -Infinity) <= viewState.zoom : true)
      );
      if (!rs.length) return;
      out.push(
        new TextLayer({
          id: `regions-t${tier}`,
          data: rs,
          getPosition: (r: Region) => [r.x, r.y],
          getText: (r: Region) => r.name,
          getSize: (r: Region) =>
            sizeScale * clamp(sizeBase + 3 * Math.log10(r.size), sizeBase, sizeBase + 12),
          sizeUnits: "pixels",
          // Tint each label with its own topic/dot color, but pulled most of the
          // way to white (LABEL_WHITE) so the map reads as mostly-white text with
          // a soft hue that matches the field underneath -- evens the whole thing
          // out without hurting legibility over the dark halo.
          getColor: (r: Region) => {
            const c = r.color ?? [240, 246, 252];
            const w = LABEL_WHITE;
            return [
              Math.round(c[0] * (1 - w) + 255 * w),
              Math.round(c[1] * (1 - w) + 255 * w),
              Math.round(c[2] * (1 - w) + 255 * w),
              255,
            ];
          },
          fontFamily: '"DejaVu Sans", system-ui, sans-serif',
          fontWeight: 700,
          characterSet: "auto",
          // Soft dark halo (SDF outline) instead of a solid box -- a subtle glow
          // for legibility over the colorful field, no rectangle.
          fontSettings: { sdf: true, buffer: 12, radius: 18 },
          outlineWidth: 7,
          outlineColor: [6, 9, 14, 235],
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
          opacity,
          pickable: false,
          updateTriggers: { opacity: [opacity], getText: [rs.length], getSize: [sizeScale, sizeBase] },
        })
      );
    };
    // On phones the labels read too large -- shrink tier-1 (topic) titles 25%
    // and tier-2 (community) titles 10%.
    labelTier(1, tier1Opacity, 13, isMobile ? 0.75 : 1); // broad: fades out by ~38%
    labelTier(2, tier2Opacity, 11, isMobile ? 0.9 : 1); // finer: fades in ~30-40%

    // Void annotations -- faint gray italic, shown at ALL zooms in one consistent
    // style (persists on zoom-in instead of vanishing, but stays gray + same name).
    if (VOID_LABELS.length) {
      out.push(
        new TextLayer({
          id: "voids",
          data: VOID_LABELS,
          getPosition: (d: { x: number; y: number }) => [d.x, d.y],
          getText: (d: { name: string }) => d.name,
          getSize: 22, // same as the region labels; only gray + italic set it apart
          sizeUnits: "pixels",
          getColor: [150, 161, 173, 178], // gray, ~70% alpha
          fontFamily: '"DejaVu Sans", system-ui, sans-serif',
          fontWeight: "italic 400" as unknown as number, // -> "italic 400 ..px.." font string
          fontSettings: { sdf: true, buffer: 8, radius: 12 },
          outlineWidth: 4,
          outlineColor: [6, 9, 14, 160],
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
          pickable: false,
        })
      );
    }
    return out;
  }, [data, numVisible, selectedHandle, pointRadius, bgOpacity, regions, reveals, tier1Opacity, tier2Opacity, colorMode, glowSpread, circle, dotPct, glowMul, colorsBoosted, isMobile]);

  return (
    <div className="exploremap" ref={ref}>
      {viewState && (
        <DeckGL
          views={new OrthographicView({})}
          // Expand the hover/click hit area around the cursor so tiny dots are
          // easy to catch (acts like an invisible larger circle per point).
          pickingRadius={12}
          controller={
            (zoomRange
              ? { minZoom: zoomRange.min, maxZoom: zoomRange.max }
              : true) as never
          }
          viewState={viewState as never}
          onViewStateChange={((e: { viewState: VS }) => {
            const vs = e.viewState;
            viewStateRef.current = vs;
            // Clamp panning to (padded) bounds -- but NOT mid-fly: clamping the
            // interpolating target is what fought the interpolator and caused
            // the overshoot. During a fly we echo deck's frames untouched (keeps
            // the LOD/zoom following smoothly), and clamp only on user panning.
            if (data && !flyingRef.current) {
              const b = data.bounds;
              const px = (b.xMax - b.xMin) * 0.06;
              const py = (b.yMax - b.yMin) * 0.06;
              vs.target = [
                clamp(vs.target[0], b.xMin - px, b.xMax + px),
                clamp(vs.target[1], b.yMin - py, b.yMax + py),
                0,
              ];
            }
            setViewState(vs);
          }) as never}
          layers={layers as never}
          onHover={(info: { index: number; x: number; y: number }) => {
            const h = data && info.index >= 0 ? data.handles[info.index] : null;
            if (h) setHover({ handle: h, x: info.x, y: info.y });
            else setHover(null);
          }}
          onClick={(info: { index: number }) => {
            if (data && info.index >= 0 && data.handles[info.index]) {
              fromDotRef.current = true; // don't fly the camera for a dot click
              onSelectHandle(data.handles[info.index]);
            }
          }}
        />
      )}
      {viewState && (
        <>
          <MapAtmosphere variant="soft" />
          <MapAtmosphere variant="screen" />
        </>
      )}
      {!data && <div className="exploremap__status">loading map…</div>}

      {/* Title / view switcher -- always visible so you can switch any time. */}
      {data && <MapTitleSwitch view={mapView} onSwitch={onSwitchView} />}

      {/* Top-right stack: data caveats, then the selected profile card BELOW them
          (so the card slides down/up as the notes expand/collapse). Clicking
          anywhere in the notes toggles them. */}
      {data && (
        <div className="maptopright">
          <div
            className={"mapnotes" + (notesOpen ? " is-open" : "")}
            role="button"
            tabIndex={0}
            aria-expanded={notesOpen}
            onClick={() => setNotesOpen((v) => !v)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setNotesOpen((v) => !v);
              }
            }}
          >
            <div className="mapnotes__head">
              <span>Limitations &amp; Notes</span>
              <span className="mapnotes__chev">{notesOpen ? "–" : "+"}</span>
            </div>
            {notesOpen && (
              <ul className="mapnotes__list">
                <li>
                  Each account is represented by <strong>who they like</strong>, not
                  from <strong>what that account itself posts</strong>.
                </li>
                <li>
                  Limited to <strong>my extended network</strong> (~221k accounts, two
                  hops out), not all of Bluesky.
                </li>
                <li>
                  <strong>English-language</strong> accounts only, it doesn't cluster
                  as well otherwise.
                </li>
                <li>
                  Data was collected over two separate pulls on different date windows.
                  Counts may slightly differ if a popular post goes outside of those,
                  sorry!
                </li>
                <li>
                  Some viz drop low-signal accounts, e.g. the like/repost plot needs
                  1+ repost per post and 5+ posts.
                </li>
              </ul>
            )}
          </div>
          <ProfileCard handle={selectedHandle} />
        </div>
      )}

      <div className="exploremap__search">
        <SearchBox
          index={data ? data.handles : []}
          selected={selectedHandle}
          onSelect={onSelectHandle}
        />
      </div>

      {data && data.colorsTopic && (
        <div className="exploremap__colormode">
          <div className="cmode__seg">
            <button
              className={colorMode === "topics" ? "is-on" : ""}
              onClick={() => setColorMode("topics")}
            >
              Colorful
            </button>
            <button
              className={colorMode === "continuum" ? "is-on" : ""}
              onClick={() => setColorMode("continuum")}
            >
              Continuum
            </button>
          </div>
          {data.legend && (
            <ul className="cmode__legend">
              {data.legend.map((t) => {
                const key = `${t.color[0]},${t.color[1]},${t.color[2]}`;
                const c =
                  colorMode === "continuum" && legendContinuum
                    ? legendContinuum.get(key) ?? t.color
                    : t.color;
                return (
                  <li key={t.id}>
                    <span
                      className="cmode__swatch"
                      style={{ background: `rgb(${c[0]},${c[1]},${c[2]})` }}
                    />
                    {t.name}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {hover && (
        <div className="exploremap__tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          @{hover.handle}
        </div>
      )}

      {/* Zoom / LOD readout so it's easy to point at "what's happening here". */}
      {data && viewState && (
        <div className="exploremap__zoom">
          zoom {zoomPct}%
          <span className="exploremap__zoom-sep">·</span>
          {numVisible.toLocaleString()} / {data.n.toLocaleString()} profiles
        </div>
      )}
    </div>
  );
}
