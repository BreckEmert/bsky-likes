import { useEffect, useMemo, useRef, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { OrthographicView, LinearInterpolator } from "@deck.gl/core";
import { ScatterplotLayer, BitmapLayer, TextLayer } from "@deck.gl/layers";
import { useExploreData } from "../lib/useExploreData.ts";
import { useRegions, type Region } from "../lib/useRegions.ts";
import { useElementSize } from "../lib/useElementSize.ts";
import { SearchBox } from "./SearchBox.tsx";
import { ProfileCard } from "./ProfileCard.tsx";

interface Props {
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
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
const LOD_FULL_PCT = 63;  // zoom % at which the full point set is shown
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function ExploreMap({ selectedHandle, onSelectHandle }: Props) {
  const data = useExploreData();
  const regions = useRegions();
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [viewState, setViewState] = useState<VS | null>(null);
  const [hover, setHover] = useState<{ handle: string; x: number; y: number } | null>(null);
  const initialZoom = useRef(0);
  const [zoomRange, setZoomRange] = useState<{ min: number; max: number } | null>(null);

  // Fit the whole field once data + container size are known.
  useEffect(() => {
    if (!data || !size.width || !size.height || viewState) return;
    const { xMin, xMax, yMin, yMax } = data.bounds;
    const z =
      Math.log2(Math.min(size.width / (xMax - xMin), size.height / (yMax - yMin))) - 0.2;
    initialZoom.current = z;
    // Cap zoom so users can't get lost: no zoom-out past the fit; bounded in.
    setZoomRange({ min: z, max: z + ZOOM_SPAN });
    setViewState({ target: [(xMin + xMax) / 2, (yMin + yMax) / 2, 0], zoom: z });
  }, [data, size, viewState]);

  // Fly to the selected handle's point (from search or another tab's selection).
  useEffect(() => {
    if (!data || !viewState) return;
    const sel = selectedHandle?.toLowerCase();
    if (!sel || !data.index.has(sel)) return;
    const i = data.index.get(sel)!;
    setViewState({
      target: [data.points[2 * i], data.points[2 * i + 1], 0],
      zoom: Math.max(viewState.zoom, initialZoom.current + ZOOM_SPAN),
      transitionDuration: 800,
      transitionInterpolator: new LinearInterpolator(["target", "zoom"]),
    } as never);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedHandle, data]);

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
  // there); grow gently as you zoom in for hover/click.
  const pointRadius = clamp(0.35 + 0.45 * zoomDelta, 0.35, 4.5);
  const zoomPct = Math.round((zoomDelta / ZOOM_SPAN) * 100);
  // Density-color background: full until ~15% zoom, then linear out to nothing
  // by ~50% (so ~62% at 27%, ~35% at 37%, ~11% at 46%), leaving just the dots.
  const FADE_START_PCT = 15;
  const FADE_END_PCT = 50;
  const bgOpacity =
    clamp((FADE_END_PCT - zoomPct) / (FADE_END_PCT - FADE_START_PCT), 0, 1) * 0.95;
  // Region labels orient you at the overview; fade them out once you're zoomed
  // in enough to be inspecting individuals (~35% -> 70%).
  const labelOpacity = clamp((70 - zoomPct) / (70 - 35), 0, 1);

  const layers = useMemo(() => {
    if (!data || !numVisible) return [];
    const b = data.bounds;
    const out: unknown[] = [
      // Smooth density-color field behind the dots; fades out as you zoom in.
      new BitmapLayer({
        id: "density",
        image: "/explore/density.png",
        bounds: [b.xMin, b.yMin, b.xMax, b.yMax],
        opacity: bgOpacity,
        updateTriggers: { opacity: [bgOpacity] },
      }),
      new ScatterplotLayer({
        id: "points",
        data: {
          length: numVisible,
          attributes: {
            getPosition: { value: data.points, size: 2 },
            getFillColor: { value: data.colors, size: 3 },
          },
        },
        getRadius: pointRadius,
        radiusUnits: "pixels",
        radiusMinPixels: 0.4,
        opacity: 0.85,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 220],
        updateTriggers: { getRadius: [pointRadius] },
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
    // Region labels (cluster centroids), on top, fading with zoom.
    if (regions.length && labelOpacity > 0) {
      out.push(
        new TextLayer({
          id: "regions",
          data: regions,
          getPosition: (r: Region) => [r.x, r.y],
          getText: (r: Region) => r.name,
          getSize: (r: Region) => clamp(12 + 4 * Math.log10(r.size), 14, 30),
          sizeUnits: "pixels",
          getColor: [255, 255, 255, 235],
          fontFamily: '"DejaVu Sans", system-ui, sans-serif',
          fontWeight: 700,
          characterSet: "auto",
          background: true,
          getBackgroundColor: [10, 13, 18, 165],
          backgroundPadding: [7, 4, 7, 4],
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
          opacity: labelOpacity,
          pickable: false,
          updateTriggers: { opacity: [labelOpacity] },
        })
      );
    }
    return out;
  }, [data, numVisible, selectedHandle, pointRadius, bgOpacity, regions, labelOpacity]);

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
            // Clamp panning to (padded) data bounds so users can't drift into
            // the void; the controller already clamps zoom to min/max.
            const vs = e.viewState;
            if (data) {
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
            if (data && info.index >= 0)
              setHover({ handle: data.handles[info.index], x: info.x, y: info.y });
            else setHover(null);
          }}
          onClick={(info: { index: number }) => {
            if (data && info.index >= 0) onSelectHandle(data.handles[info.index]);
          }}
        />
      )}
      {!data && <div className="exploremap__status">loading map…</div>}

      <div className="exploremap__search">
        <SearchBox
          index={data ? data.handles : []}
          selected={selectedHandle}
          onSelect={onSelectHandle}
        />
      </div>
      <ProfileCard handle={selectedHandle} />

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
          {numVisible.toLocaleString()} / {data.n.toLocaleString()} pts
        </div>
      )}
    </div>
  );
}
