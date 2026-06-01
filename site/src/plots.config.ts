// Single source of truth for the deck. Adding/removing/reordering a plot =
// editing this file. Shapes mirror SITE_BUILD_GUIDE.md.

export type HighlightKind =
  | "deck-scatter"
  | "svg-point"
  | "svg-line"
  | "list-row"
  | null;

export type TabAnim =
  | "draw-curve"
  | "hex-glow"
  | "drifting-lines"
  | "rising-bars"
  | "spotlight-points"
  | "pulse-grid";

export interface PlotConfig {
  id: string;
  tabLabel: string;        // <= 3 words, shown on the tab
  title: string;           // HTML header (rendered crisp, not baked in PNG)
  subtitle: string | null; // "\n" allowed; rendered as <br>
  image: string | null;    // background PNG; null for HTML-only plots
  bounds?: string;         // /plots/<id>.bounds.json (searchable plots)
  searchable: boolean;
  tabAnim: TabAnim;
  highlight: HighlightKind;
  // Lookup assets, wired per highlight strategy as we build each plot:
  data?: Record<string, string>;
}

// NOTE: image paths currently point at PLACEHOLDER PNGs (the matplotlib output
// with titles still baked in). They will be replaced by the title-suppressed,
// transparent export PNGs from bsky_export_web.py. Leaderboards is HTML-only.
export const PLOTS: PlotConfig[] = [
  {
    id: "typical-popularity",
    tabLabel: "Typical Popularity",
    title: "What's the typical popularity of posts you like?",
    subtitle:
      "Higher y = a few things you've liked blew up\nBottom-left = you've literally liked nothing popular",
    image: "/plots/typical-popularity.png",
    bounds: "/plots/typical-popularity.bounds.json",
    searchable: true,
    tabAnim: "hex-glow",
    highlight: "svg-point",
    data: {
      handles: "/plots/typical-popularity.handles.bin",
      positions: "/plots/typical-popularity.positions.bin",
    },
  },
  {
    id: "popularity-curve",
    tabLabel: "Popularity Curve",
    title: "How popular are the posts we like?",
    subtitle:
      "each blue line = one user's histogram of how popular their liked posts are",
    image: "/plots/popularity-curve.png",
    bounds: "/plots/popularity-curve.bounds.json",
    searchable: true,
    tabAnim: "drifting-lines",
    highlight: "svg-line",
    data: {
      handles: "/plots/popularity-curve.handles.bin",
      histograms: "/plots/popularity-curve.histograms.bin",
      histmeta: "/plots/popularity-curve.histmeta.json",
    },
  },
  {
    id: "like-repost",
    tabLabel: "Like/Repost Ratio",
    title: "Your like-to-repost ratios",
    subtitle: "upper-left posts are reposted but not liked",
    image: "/plots/like-repost.png",
    bounds: "/plots/like-repost.bounds.json",
    searchable: true,
    tabAnim: "hex-glow",
    highlight: "svg-point",
    data: {
      handles: "/plots/like-repost.handles.bin",
      positions: "/plots/like-repost.positions.bin",
    },
  },
  {
    id: "leaderboards",
    tabLabel: "Most & Least",
    title: "Who likes the most (and least) popular posts?",
    subtitle: null,
    image: null,
    searchable: true,
    tabAnim: "rising-bars",
    highlight: "list-row",
    data: {
      rows: "/plots/leaderboards.json",
      handles: "/plots/leaderboards.handles.bin",
      values: "/plots/leaderboards.values.bin",
    },
  },
  {
    id: "half-life",
    tabLabel: "Engagement Age",
    title: "Engagement Half-Life",
    subtitle: "How fresh is a post when it gets liked?",
    image: "/plots/half-life.png",
    // Aggregate histogram — no per-handle (x,y), so not searchable. (Guide
    // imagined a deck-scatter here; revisit if we want a per-user variant.)
    searchable: false,
    tabAnim: "spotlight-points",
    highlight: null,
  },
  {
    id: "activity",
    tabLabel: "Followers vs Taste",
    title: "Bluesky users are so kind <3",
    subtitle:
      "the more popular we are\nthe less popular the content we like",
    image: "/plots/activity.png",
    bounds: "/plots/activity.bounds.json",
    searchable: true,
    tabAnim: "spotlight-points",
    highlight: "deck-scatter",
    data: {
      handles: "/plots/activity.handles.bin",
      positions: "/plots/activity.positions.bin",
    },
  },
  {
    id: "punching",
    tabLabel: "Likes vs Followers",
    title: "Top 4,000 liked accounts",
    subtitle: null,
    image: "/plots/punching.png",
    bounds: "/plots/punching.bounds.json",
    searchable: true,
    tabAnim: "spotlight-points",
    highlight: "deck-scatter",
    data: {
      handles: "/plots/punching.handles.bin",
      positions: "/plots/punching.positions.bin",
    },
  },
  {
    id: "wakes-up",
    tabLabel: "Activity by Hour",
    title: "When Bluesky Wakes Up",
    subtitle: null,
    image: "/plots/wakes-up.png",
    searchable: false,
    tabAnim: "pulse-grid",
    highlight: null,
  },
  {
    // Non-searchable (no per-user selection) — placed last to match plots.py.
    id: "long-tail",
    tabLabel: "Attention Inequality",
    title: "How unequal is attention on Bluesky?",
    subtitle: null,
    image: "/plots/long-tail.png",
    searchable: false,
    tabAnim: "draw-curve",
    highlight: null,
  },
];
