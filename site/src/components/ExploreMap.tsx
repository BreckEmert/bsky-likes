import { useEffect, useMemo, useRef, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { OrthographicView, LinearInterpolator } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
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

// LOD: render only the first N points (sorted by followers) when zoomed out,
// 4x more per zoom level — all from one GPU buffer (Theo's snappy pattern).
const LOD_BASE = 40000;

export function ExploreMap({ selectedHandle, onSelectHandle }: Props) {
  const data = useExploreData();
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [viewState, setViewState] = useState<VS | null>(null);
  const [hover, setHover] = useState<{ handle: string; x: number; y: number } | null>(null);
  const initialZoom = useRef(0);

  // Fit the whole field once data + container size are known.
  useEffect(() => {
    if (!data || !size.width || !size.height || viewState) return;
    const { xMin, xMax, yMin, yMax } = data.bounds;
    const z =
      Math.log2(Math.min(size.width / (xMax - xMin), size.height / (yMax - yMin))) - 0.2;
    initialZoom.current = z;
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

  const numVisible = useMemo(() => {
    if (!data || !viewState) return 0;
    const d = Math.max(0, viewState.zoom - initialZoom.current);
    return Math.min(data.n, Math.round(LOD_BASE * Math.pow(4, d)));
  }, [data, viewState]);

  const layers = useMemo(() => {
    if (!data || !numVisible) return [];
    const out: unknown[] = [
      new ScatterplotLayer({
        id: "points",
        data: {
          length: numVisible,
          attributes: {
            getPosition: { value: data.points, size: 2 },
            getFillColor: { value: data.colors, size: 3 },
          },
        },
        getRadius: 1.6,
        radiusUnits: "pixels",
        radiusMinPixels: 1,
        opacity: 0.72,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 220],
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
  }, [data, numVisible, selectedHandle]);

  return (
    <div className="exploremap" ref={ref}>
      {viewState && (
        <DeckGL
          views={new OrthographicView({})}
          controller={true}
          viewState={viewState as never}
          onViewStateChange={(e: { viewState: unknown }) => setViewState(e.viewState as VS)}
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
