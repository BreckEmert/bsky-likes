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
        <div className="champs__stat">
          <b>Middle-class workhorses</b> — {midPct}% of tribes are owned by an
          account that isn’t famous (under 50k followers).
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

      <div className="champs__tree">
        {data.topics.map((t) => {
          const sum = t.champions.reduce((s, c) => s + c.subSize, 0) || 1;
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
                {t.champions.map((c) => (
                  <button
                    key={c.handle}
                    className={"champcell champcell--" + c.class}
                    style={{ flexGrow: c.subSize / sum }}
                    onMouseEnter={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                    onMouseMove={(e) => setHover({ c, x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => onSelectHandle(c.handle)}
                  >
                    <span className="champcell__h">@{c.handle.replace(/\.bsky\.social$/, "")}</span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {hover && (
        <div className="champs__tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <div className="champs__tip-h">@{hover.c.handle}</div>
          <div className="champs__tip-r">
            owns <b>{hover.c.subSize.toLocaleString()}</b> users · likes them{" "}
            <b>{hover.c.lift}×</b> more than average ·{" "}
            <b>{hover.c.followers.toLocaleString()}</b> followers
          </div>
        </div>
      )}

      <ProfileCard handle={selectedHandle} />
    </div>
  );
}
