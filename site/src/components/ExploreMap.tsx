import { useEffect, useMemo, useRef, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { OrthographicView, LinearInterpolator } from "@deck.gl/core";
import { ScatterplotLayer, BitmapLayer } from "@deck.gl/layers";
import { useExploreData } from "../lib/useExploreData.ts";
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

// LOD: at the overview show only the most-prominent N points (sorted by
// followers); reveal ~2.4x more per zoom level from one GPU buffer (Theo's
// snappy pattern). Lower base + gentler ramp = the reveal is clearly visible
// across the whole zoom range.
const LOD_BASE = 12000;
const LOD_GROWTH = 2.4;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function ExploreMap({ selectedHandle, onSelectHandle }: Props) {
  const data = useExploreData();
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
    setZoomRange({ min: z, max: z + 6 });
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
      zoom: Math.max(viewState.zoom, initialZoom.current + 6),
      transitionDuration: 800,
      transitionInterpolator: new LinearInterpolator(["target", "zoom"]),
    } as never);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedHandle, data]);

  const zoomDelta = viewState ? Math.max(0, viewState.zoom - initialZoom.current) : 0;
  const numVisible = useMemo(() => {
    if (!data || !viewState) return 0;
    return Math.min(data.n, Math.round(LOD_BASE * Math.pow(LOD_GROWTH, zoomDelta)));
  }, [data, viewState, zoomDelta]);
  // Crisp small dots at the overview (the density background carries the color
  // there); grow a bit as you zoom in for hover/click.
  const pointRadius = clamp(1.0 + 0.45 * zoomDelta, 1.0, 6.0);
  // Density-color background fades out by ~3/4 of the way in, leaving just dots.
  const bgOpacity = clamp(1 - zoomDelta / 4.5, 0, 1) * 0.95;

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
        radiusMinPixels: 1,
        opacity: 0.72,
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
    return out;
  }, [data, numVisible, selectedHandle, pointRadius, bgOpacity]);

  return (
    <div className="exploremap" ref={ref}>
      {viewState && (
        <DeckGL
          views={new OrthographicView({})}
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
    </div>
  );
}
