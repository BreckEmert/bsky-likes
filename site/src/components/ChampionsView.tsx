import { useState } from "react";
import {
  useChampions,
  CLASS_COLOR,
  CLASS_LABEL,
  type ChampClass,
  type Champion,
} from "../lib/useChampions.ts";
import { MapTitleSwitch, type MapView } from "./MapTitleSwitch.tsx";
import { ProfileCard } from "./ProfileCard.tsx";

interface Props {
  view: MapView;
  onSwitch: (v: MapView) => void;
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
}

// "Who owns each tribe?" — a 2-level tree: tier-1 topics (rows) split into the
// champions that dominate each sub-community (cells, width ∝ community size,
// colored by class). Champions are picked by LIFT (distinctiveness), so the
// middle/lower-class "workhorses" surface instead of the usual megastars.
export function ChampionsView({ view, onSwitch, selectedHandle, onSelectHandle }: Props) {
  const data = useChampions();
  const [hover, setHover] = useState<{ c: Champion; x: number; y: number } | null>(null);
  // "topic" = champions grouped under their broad topic (cells ∝ size);
  // "community" = one row per fine-grained sub-community + its champion.
  const [layout, setLayout] = useState<"topic" | "community">("topic");

  if (!data) {
    return (
      <div className="champs">
        <MapTitleSwitch view={view} onSwitch={onSwitch} />
        <div className="champs__empty">
          No champions yet — run <code>python export_champions.py</code> to build
          them.
        </div>
      </div>
    );
  }

  const total = data.classCounts.upper + data.classCounts.middle + data.classCounts.lower;
  const midPct = total ? Math.round((data.classCounts.middle / total) * 100) : 0;

  return (
    <div className="champs">
      <MapTitleSwitch view={view} onSwitch={onSwitch} />

      <div className="champs__head">
        <div className="champs__intro">
          <div className="champs__title">
            Each community’s champion — the account it loves far more than the
            rest of Bluesky does.
          </div>
          <div className="champs__tech">
            Found by <em>lift</em>: a community’s like-rate for an account ÷ the
            whole site’s, so its true favorites outrank the megastars everyone
            likes.
          </div>
          <div className="champs__stat">
            <span className="champs__midchip">Middle-class workhorses</span> —{" "}
            {midPct}% of tribes are owned by an account that isn’t famous (under
            50k followers).
          </div>
          <div className="champs__toggle" role="tablist" aria-label="Champions layout">
            <button
              type="button"
              role="tab"
              aria-selected={layout === "topic"}
              className={"champs__toggle-b" + (layout === "topic" ? " is-on" : "")}
              onClick={() => setLayout("topic")}
            >
              By topic
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={layout === "community"}
              className={"champs__toggle-b" + (layout === "community" ? " is-on" : "")}
              onClick={() => setLayout("community")}
            >
              By community
            </button>
          </div>
        </div>
        <ul className="champs__legend">
          {(["upper", "middle", "lower"] as ChampClass[]).map((k) => (
            <li key={k}>
              <span className="champs__sw" style={{ background: CLASS_COLOR[k] }} />
              {CLASS_LABEL[k]}
            </li>
          ))}
        </ul>
      </div>

      <div className="champs__caption">
        {layout === "topic" ? (
          <>Each bar is a sub-community’s champion; widest = biggest community.</>
        ) : (
          <>
            Sorted by <b>lift</b> — how much more this community likes them than the
            rest of Bluesky (so a niche favorite can outrank a bigger star who’s
            liked everywhere).
          </>
        )}
      </div>

      <div className={"champs__tree" + (layout === "community" ? " champs__tree--flat" : "")}>
        {layout === "topic"
          ? data.topics.map((t) => {
              const sum = t.champions.reduce((s, c) => s + c.subSize, 0) || 1;
              // widest bar (biggest community) first, left-to-right
              const cells = [...t.champions].sort((a, b) => b.subSize - a.subSize);
              return (
                <div className="champrow" key={t.topic}>
                  <div
                    className="champrow__topic"
                    style={{ color: `rgb(${t.color[0]},${t.color[1]},${t.color[2]})` }}
                    title={t.name}
                  >
                    {t.name}
                  </div>
                  <div className="champrow__cells">
                    {cells.map((c, i) => (
                      <button
                        // a handle can champion two sub-communities (e.g. tobyfox),
                        // so the index keeps the key unique.
                        key={c.handle + "-" + i}
                        className={"champcell champcell--" + c.class}
                        style={{ ["--cw" as string]: String(c.subSize / sum) }}
                        onMouseEnter={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                        onMouseMove={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => onSelectHandle(c.handle)}
                      >
                        {c.subName && <span className="champcell__sub">{c.subName}</span>}
                        <span className="champcell__h">@{c.handle.replace(/\.bsky\.social$/, "")}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })
          : data.communities.map((co) => {
              // bar width ∝ lift, so the (lift-based) ranking is visible & monotonic
              const liftSum = co.champions.reduce((s, ch) => s + ch.lift, 0) || 1;
              return (
              <div className="champrow" key={co.sub}>
                <div
                  className="champrow__topic champrow__topic--wide"
                  style={{ color: `rgb(${co.color[0]},${co.color[1]},${co.color[2]})` }}
                  title={co.name}
                >
                  <span className="champrow__name">{co.name || "Unnamed community"}</span>
                  <span className="champrow__size">{co.subSize.toLocaleString()} users</span>
                </div>
                <div className="champrow__cells">
                  {co.champions.map((ch, i) => {
                    // reshape into the Champion the shared tooltip expects
                    const c: Champion = {
                      handle: ch.handle,
                      subName: co.name,
                      subSize: co.subSize,
                      supporters: ch.supporters,
                      lift: ch.lift,
                      followers: ch.followers,
                      class: ch.class,
                    };
                    return (
                      <button
                        key={ch.handle + "-" + i}
                        className={"champcell champcell--" + ch.class}
                        style={{ ["--cw" as string]: String(ch.lift / liftSum) }}
                        onMouseEnter={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                        onMouseMove={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => onSelectHandle(ch.handle)}
                      >
                        <span className="champcell__h">
                          @{ch.handle.replace(/\.bsky\.social$/, "")}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
              );
            })}
      </div>

      {hover && (
        <div
          className="champs__tip"
          style={{
            // clamp to the viewport so rightmost/bottom champions aren't offscreen
            left: Math.min(hover.x + 14, window.innerWidth - 332),
            top: Math.min(hover.y + 14, window.innerHeight - 90),
          }}
        >
          <div className="champs__tip-h">@{hover.c.handle}</div>
          {hover.c.subName && (
            <div className="champs__tip-sub">
              {layout === "community" ? "in" : "champion of"} {hover.c.subName}
            </div>
          )}
          {layout === "community" ? (
            // per-champion metrics that actually differ within a community:
            // how many of its members like them, lift, and their fame
            <div className="champs__tip-r">
              liked <b>{hover.c.lift}×</b> more than the rest of Bluesky · liked by{" "}
              <b>{Math.round((hover.c.supporters / hover.c.subSize) * 100)}%</b> of
              the community ({hover.c.supporters.toLocaleString()} of{" "}
              {hover.c.subSize.toLocaleString()}) ·{" "}
              <b>{hover.c.followers.toLocaleString()}</b> followers
            </div>
          ) : (
            <div className="champs__tip-r">
              rules <b>{hover.c.subSize.toLocaleString()}</b> users · liked{" "}
              <b>{hover.c.lift}×</b> more than average ·{" "}
              <b>{hover.c.followers.toLocaleString()}</b> followers
            </div>
          )}
        </div>
      )}

      <ProfileCard handle={selectedHandle} />
    </div>
  );
}
