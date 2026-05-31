import type { PlotConfig } from "../plots.config.ts";

interface Props {
  plots: PlotConfig[];
  activeId: string;
  onSelect: (id: string) => void;
}

// Step 1: text-label tabs. The live animated canvas previews (shared rAF,
// archetype renderers) are added in a later step — see TabPreview/tabAnim.
export function TabBar({ plots, activeId, onSelect }: Props) {
  return (
    <nav className="tabbar" role="tablist" aria-label="Plots">
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
