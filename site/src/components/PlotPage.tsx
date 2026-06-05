import { useEffect, useState } from "react";
import type { PlotConfig } from "../plots.config.ts";
import {
  containRect,
  dataToPixel,
  identityBounds,
  type Bounds,
} from "../lib/coords.ts";
import { useElementSize } from "../lib/useElementSize.ts";
import { useBounds } from "../lib/useBounds.ts";
import { usePointData } from "../lib/usePointData.ts";
import { useLeaderboard } from "../lib/useLeaderboard.ts";
import { useHistograms } from "../lib/useHistograms.ts";
import { SearchBox } from "./SearchBox.tsx";
import { SvgPoint } from "./highlights/SvgPoint.tsx";
import { SvgPoints, type HLPoint } from "./highlights/SvgPoints.tsx";
import { SvgLine } from "./highlights/SvgLine.tsx";
import { ListRows } from "./highlights/ListRows.tsx";
import { FollowsHighlight, type FollowPicks } from "./FollowsHighlight.tsx";
import { ProfileCard } from "./ProfileCard.tsx";

const FOLLOW_PINK = "#ec4899";
const FOLLOW_USER = "#22d3ee"; // distinct-but-friendly cyan for the searched user

interface Props {
  plot: PlotConfig;
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
}

// "?debug" shows the image rect + a center crosshair; "?debug=X,Y" places it at
// data point (X, Y) — used to verify data->pixel alignment against a known point.
const params = new URLSearchParams(location.search);
const DEBUG = params.has("debug");
function debugPoint(): { x: number; y: number } | null {
  const v = params.get("debug");
  if (!v) return null;
  const [x, y] = v.split(",").map(Number);
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

// Phone viewport -> use the .mobile.png / .mobile.bounds.json variants (squarer,
// fills vertical space). The <picture> below downloads only the matching image;
// bounds are fetched per-viewport. 640px matches the CSS mobile breakpoint.
function useIsMobile(): boolean {
  const q = "(max-width: 640px)";
  const [m, setM] = useState(
    () => typeof window !== "undefined" && window.matchMedia(q).matches
  );
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

export function PlotPage({ plot, selectedHandle, onSelectHandle }: Props) {
  const [stageRef, stageSize] = useElementSize<HTMLDivElement>();
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const isMobile = useIsMobile();
  // Use the .mobile.png / .mobile.bounds.json variant on phones. If it 404s (a plot
  // not regenerated yet), fall back to the desktop asset so nothing breaks.
  const [mobileMissing, setMobileMissing] = useState(false);
  useEffect(() => setMobileMissing(false), [plot.id]);
  const useMobile = isMobile && !mobileMissing && !!plot.image;
  const imgSrc = useMobile ? plot.image!.replace(/\.png$/, ".mobile.png") : plot.image;
  const boundsUrl =
    useMobile && plot.bounds
      ? plot.bounds.replace(/\.bounds\.json$/, ".mobile.bounds.json")
      : plot.bounds;
  const bounds = useBounds(boundsUrl);
  // re-measure the image when the variant swaps (mobile/desktop differ in size)
  useEffect(() => setNatural(null), [isMobile, mobileMissing]);
  // Binary point data (handles + positions) for every searchable point plot
  // (svg-point and deck-scatter). One loader, one contract.
  const points = usePointData(plot.data?.handles, plot.data?.positions);
  // Leaderboards (list-row) loads ranked rows instead of a PNG + point data.
  const leaderboard = useLeaderboard(
    plot.highlight === "list-row" ? plot.data : undefined
  );
  // Per-user histograms for the svg-line plot (popularity-curve).
  const isLine = plot.highlight === "svg-line";
  const hist = useHistograms(
    isLine ? plot.data?.handles : undefined,
    isLine ? plot.data?.histograms : undefined,
    isLine ? plot.data?.histmeta : undefined
  );

  // "Highlight 15 you follow" feature (punching plot). Local to this plot, not
  // tied to the global selectedHandle.
  const isFollows = plot.highlight === "follows";
  const [followPicks, setFollowPicks] = useState<FollowPicks>({ user: null, picks: [] });

  useEffect(() => {
    setNatural(null);
    setFollowPicks({ user: null, picks: [] });
  }, [plot.id]);

  const imgRect = natural
    ? containRect(stageSize.width, stageSize.height, natural.w, natural.h)
    : null;

  // Resolve the followed picks (pink) + the user (cyan, "hero") to plot points.
  const followItems: HLPoint[] =
    isFollows && points
      ? [
          ...followPicks.picks.map((h) => ({ h, color: FOLLOW_PINK, big: false })),
          ...(followPicks.user
            ? [{ h: followPicks.user, color: FOLLOW_USER, big: true }]
            : []),
        ]
          .map(({ h, color, big }): HLPoint | null => {
            const p = points.get(h);
            return p ? { handle: h, point: p, color, big } : null;
          })
          .filter((x): x is HLPoint => x !== null)
      : [];

  const effBounds: Bounds | null =
    bounds ?? (natural ? identityBounds(natural.w, natural.h) : null);

  const handleIndex = points
    ? points.handles
    : hist
    ? hist.handles
    : leaderboard
    ? leaderboard.allHandles // search ANY ranked user, not just the shown 50s
    : [];
  const selectedPoint =
    points && selectedHandle ? points.get(selectedHandle) ?? null : null;
  const selectedDensity =
    hist && selectedHandle ? hist.get(selectedHandle) ?? null : null;

  const dp = debugPoint();
  const crosshair =
    DEBUG && imgRect && effBounds
      ? dataToPixel(
          effBounds,
          imgRect,
          dp ? dp.x : (effBounds.xMin + effBounds.xMax) / 2,
          dp ? dp.y : (effBounds.yMin + effBounds.yMax) / 2
        )
      : null;

  // Is the selected handle absent from this plot's data?
  const notHere =
    !!selectedHandle &&
    plot.searchable &&
    ((points !== null && !selectedPoint) || (hist !== null && !selectedDensity));

  // Leaderboard rank readout (was a hover overlay on the lists; now shown below
  // the search bar so it's legible and out of the way of the graph).
  const sel = selectedHandle?.toLowerCase() ?? null;
  const lbNote =
    plot.highlight === "list-row" && leaderboard && sel
      ? leaderboard.mostObscure.some((r) => r.handle === sel) ||
        leaderboard.mostMainstream.some((r) => r.handle === sel)
        ? null
        : (() => {
            const ranked = leaderboard.rankOf(sel);
            return ranked
              ? `@${sel} ranks #${ranked.rank.toLocaleString()} of ${leaderboard.total.toLocaleString()} by mainstreaminess (1 = likes the most viral)`
              : `@${sel} isn’t a ranked user (needs ≥50 likes)`;
          })()
      : null;

  return (
    <main className="plotpage">
      <header className="plotpage__header">
        <h1 className="plotpage__title">{plot.title}</h1>
        {plot.subtitle && (
          <p className="plotpage__subtitle">
            {plot.subtitle.split("\n").map((line, i) => (
              <span key={i} className="plotpage__subtitle-line">
                {line}
              </span>
            ))}
          </p>
        )}
      </header>

      <div className="plotpage__stage" ref={stageRef}>
        {plot.searchable && (
          <div className="plotpage__search">
            <SearchBox
              index={handleIndex}
              selected={selectedHandle}
              onSelect={onSelectHandle}
            />
            {notHere && (
              <div className="plotpage__nothere">
                @{selectedHandle} isn’t on this plot
              </div>
            )}
            {lbNote && <div className="plotpage__nothere">{lbNote}</div>}
          </div>
        )}

        {/* "Highlight 15 you follow" control (punching plot). */}
        {isFollows && (
          <div className="plotpage__search">
            <FollowsHighlight points={points} onPicks={setFollowPicks} />
          </div>
        )}

        {/* Profile card for the selected handle. Only on searchable plots —
            non-selectable plots (long-tail, wakes-up) shouldn't show it. The
            follows plot shows the entered user's card instead. */}
        {plot.searchable && <ProfileCard handle={selectedHandle} />}
        {isFollows && followPicks.user && <ProfileCard handle={followPicks.user} />}

        {plot.image ? (
          <img
            key={plot.id + (useMobile ? "-m" : "")}
            className={`plotpage__image plotpage__image--${plot.id}`}
            src={imgSrc ?? undefined}
            alt={plot.title}
            draggable={false}
            onError={() => useMobile && setMobileMissing(true)}
            onLoad={(e) =>
              setNatural({
                w: e.currentTarget.naturalWidth,
                h: e.currentTarget.naturalHeight,
              })
            }
          />
        ) : plot.highlight === "list-row" ? (
          <ListRows data={leaderboard} selectedHandle={selectedHandle} />
        ) : (
          <div className="plotpage__placeholder">
            <span>{plot.tabLabel} — built in a later step</span>
          </div>
        )}

        {imgRect && (
          <svg
            className="plotpage__overlay"
            width={stageSize.width}
            height={stageSize.height}
          >
            {/* svg-point and deck-scatter both highlight one point with the
                same ring (both load binary point data). deck.gl hover-any-point
                is a deferred enhancement; the search-highlight is identical. */}
            {isFollows && (
              <SvgPoints items={followItems} bounds={bounds} imgRect={imgRect} />
            )}
            {(plot.highlight === "svg-point" ||
              plot.highlight === "deck-scatter") && (
              <SvgPoint
                handle={selectedHandle}
                point={selectedPoint}
                bounds={bounds}
                imgRect={imgRect}
              />
            )}
            {plot.highlight === "svg-line" && (
              <SvgLine
                handle={selectedHandle}
                density={selectedDensity}
                hist={hist}
                bounds={bounds}
                imgRect={imgRect}
              />
            )}
            {DEBUG && (
              <rect
                x={imgRect.left}
                y={imgRect.top}
                width={imgRect.width}
                height={imgRect.height}
                fill="none"
                stroke="#1d9bf0"
                strokeDasharray="4 4"
                opacity={0.5}
              />
            )}
            {crosshair && (
              <g stroke="#ec4899" strokeWidth={2} fill="none">
                <line
                  x1={crosshair.x - 14}
                  y1={crosshair.y}
                  x2={crosshair.x + 14}
                  y2={crosshair.y}
                />
                <line
                  x1={crosshair.x}
                  y1={crosshair.y - 14}
                  x2={crosshair.x}
                  y2={crosshair.y + 14}
                />
                <circle cx={crosshair.x} cy={crosshair.y} r={11} />
              </g>
            )}
          </svg>
        )}
      </div>
    </main>
  );
}
