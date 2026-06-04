import type { ReactNode } from "react";
import type { PlotConfig } from "../plots.config.ts";

interface Props {
  plots: PlotConfig[];
  activeId: string;
  onSelect: (id: string) => void;
  // Rendered as the first cell of the tab grid -- used on mobile to inline the
  // "Explore some plots" label so the first row is label + 2 tabs (hidden on
  // desktop, where the label is its own left column).
  leading?: ReactNode;
}

// Step 1: text-label tabs. The live animated canvas previews (shared rAF,
// archetype renderers) are added in a later step — see TabPreview/tabAnim.
export function TabBar({ plots, activeId, onSelect, leading }: Props) {
  return (
    <nav className="tabbar" role="tablist" aria-label="Plots">
      {leading && <div className="tabbar__lead">{leading}</div>}
      {plots.map((p) => (
        <button
          key={p.id}
          role="tab"
          aria-selected={p.id === activeId}
          className={"tab" + (p.id === activeId ? " tab--active" : "")}
          onClick={() => onSelect(p.id)}
        >
          <span className="tab__label">{p.tabLabel}</span>
        </button>
      ))}
    </nav>
  );
}
