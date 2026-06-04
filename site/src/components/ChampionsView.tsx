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
import { SearchBox } from "./SearchBox.tsx";
import { useChampionMembers } from "../lib/useChampionMembers.ts";

interface Props {
  view: MapView;
  onSwitch: (v: MapView) => void;
  selectedHandle: string | null;
  onSelectHandle: (h: string | null) => void;
}

// The lead stat in the tooltip, phrased for the active lens (each lens ranks by a
// different thing, so we surface that thing first).
function leadStat(metric: string, c: Champion) {
  const pct = Math.round(c.share * 100);
  switch (metric) {
    case "loyalty":
      return (
        <>
          <b>{pct}%</b> of their superfans are right here ({c.superfans.toLocaleString()} of{" "}
          {c.globalSuperfans.toLocaleString()})
        </>
      );
    case "devotion":
      return (
        <>
          <b>{c.superfans.toLocaleString()}</b> superfans here (liked 15+ of their posts)
        </>
      );
    case "distinct":
      return (
        <>
          liked <b>{c.lift}×</b> more than the rest of Bluesky
        </>
      );
    case "likerate":
      return (
        <>
          <b>{c.likeRate.toLocaleString()}</b> avg likes per post from this community
        </>
      );
    default:
      return null;
  }
}

// "Who does each community rally around?" — switch the LENS (loyalty / devotion /
// distinctiveness / like-rate) and the LAYOUT (by topic / by community). Each lens
// is a precomputed variant; the radio just swaps the data.
export function ChampionsView({ view, onSwitch, selectedHandle, onSelectHandle }: Props) {
  const data = useChampions();
  const [hover, setHover] = useState<{ c: Champion; x: number; y: number } | null>(null);
  const [metric, setMetric] = useState<string | null>(null);
  const [layout, setLayout] = useState<"topic" | "community">("topic");
  // user-search: floats the searched user's community/topic to the top.
  // handles.bin is already cached from the cluster map, so this is cheap.
  const [searchHandle, setSearchHandle] = useState<string | null>(null);
  const members = useChampionMembers(true);

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

  const activeId =
    metric ?? data.metrics.find((m) => m.default)?.id ?? data.metrics[0].id;
  const active = data.variants[activeId];
  const blurb = data.metrics.find((m) => m.id === activeId)?.blurb ?? "";

  const cc = active.classCounts;
  const total = cc.upper + cc.middle + cc.lower || 1;
  const nonFamousPct = Math.round(((cc.middle + cc.lower) / total) * 100);

  // resolve the searched handle -> its sub + topic, and float those rows up
  const matchedSub =
    searchHandle != null ? members?.subOf.get(searchHandle.toLowerCase()) : undefined;
  const subToTopic = new Map<number, number>();
  active.communities.forEach((c) => subToTopic.set(c.sub, c.topic));
  const matchedTopic = matchedSub != null ? subToTopic.get(matchedSub) : undefined;
  const notInCommunity = searchHandle != null && members != null && matchedSub == null;
  const orderedTopics =
    matchedTopic == null
      ? active.topics
      : [
          ...active.topics.filter((t) => t.topic === matchedTopic),
          ...active.topics.filter((t) => t.topic !== matchedTopic),
        ];
  const orderedCommunities =
    matchedSub == null
      ? active.communities
      : [
          ...active.communities.filter((c) => c.sub === matchedSub),
          ...active.communities.filter((c) => c.sub !== matchedSub),
        ];

  return (
    <div className="champs">
      <MapTitleSwitch view={view} onSwitch={onSwitch} />

      <div className="champs__head">
        <div className="champs__intro">
          <div className="champs__title">Who does each community rally around?</div>
          <div className="champs__stat">
            <span className="champs__midchip">{nonFamousPct}% non-famous</span> — under
            this lens, that share of communities are led by an account with under 50k
            followers.
          </div>
          <div className="champs__controls">
            <div className="champs__toggle" role="tablist" aria-label="Ranking lens">
              {data.metrics.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="tab"
                  aria-selected={m.id === activeId}
                  className={"champs__toggle-b" + (m.id === activeId ? " is-on" : "")}
                  onClick={() => setMetric(m.id)}
                >
                  {m.label}
                </button>
              ))}
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
          <div className="champs__search">
            <SearchBox
              index={members?.handles ?? []}
              selected={searchHandle}
              onSelect={setSearchHandle}
            />
            {notInCommunity && (
              <div className="champs__nomatch">
                @{searchHandle} isn’t in a clustered community
              </div>
            )}
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

      <div className="champs__caption">{blurb}</div>

      <div className={"champs__tree" + (layout === "community" ? " champs__tree--flat" : "")}>
        {layout === "topic"
          ? orderedTopics.map((t) => {
              const sum = t.champions.reduce((s, c) => s + c.subSize, 0) || 1;
              // widest bar (biggest community) first, left-to-right
              const cells = [...t.champions].sort((a, b) => b.subSize - a.subSize);
              return (
                <div
                  className={"champrow" + (t.topic === matchedTopic ? " champrow--match" : "")}
                  key={t.topic}
                >
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
          : orderedCommunities.map((co) => {
              // by-community bar ∝ the active lens's ranking value, so the order is visible
              const vsum = co.champions.reduce((s, ch) => s + ch.value, 0) || 1;
              return (
                <div
                  className={"champrow" + (co.sub === matchedSub ? " champrow--match" : "")}
                  key={co.sub}
                >
                  <div
                    className="champrow__topic champrow__topic--wide"
                    style={{ color: `rgb(${co.color[0]},${co.color[1]},${co.color[2]})` }}
                    title={co.name}
                  >
                    <span className="champrow__name">{co.name || "Unnamed community"}</span>
                    <span className="champrow__size">{co.subSize.toLocaleString()} users</span>
                  </div>
                  <div className="champrow__cells">
                    {co.champions.map((ch, i) => (
                      <button
                        key={ch.handle + "-" + i}
                        className={"champcell champcell--" + ch.class}
                        style={{ ["--cw" as string]: String(ch.value / vsum) }}
                        onMouseEnter={(e) => setHover({ c: ch, x: e.clientX, y: e.clientY })}
                        onMouseMove={(e) => setHover({ c: ch, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => onSelectHandle(ch.handle)}
                      >
                        <span className="champcell__h">@{ch.handle.replace(/\.bsky\.social$/, "")}</span>
                      </button>
                    ))}
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
            top: Math.min(hover.y + 14, window.innerHeight - 96),
          }}
        >
          <div className="champs__tip-h">@{hover.c.handle}</div>
          {hover.c.subName && (
            <div className="champs__tip-sub">
              {layout === "community" ? "in" : "champion of"} {hover.c.subName}
            </div>
          )}
          <div className="champs__tip-r">
            {leadStat(activeId, hover.c)} · <b>{hover.c.followers.toLocaleString()}</b>{" "}
            followers
          </div>
        </div>
      )}

      <ProfileCard handle={selectedHandle} />
    </div>
  );
}
