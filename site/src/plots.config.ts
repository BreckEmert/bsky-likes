// Single source of truth for the deck. Adding/removing/reordering a plot =
// editing this file. Shapes mirror SITE_BUILD_GUIDE.md.
import { asset } from "./lib/asset.ts";

export type HighlightKind =
  | "deck-scatter"
  | "svg-point"
  | "svg-line"
  | "list-row"
  | "follows" // punch in your handle -> highlight 15 random accounts you follow
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
const RAW_PLOTS: PlotConfig[] = [
  {
    id: "typical-popularity",
    tabLabel: "Typical Popularity",
    title: "What's the typical popularity of posts we like?",
    subtitle:
      "Higher = a few things we liked blew up\nBottom-left = we've liked nothing popular",
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
    title: "Our like-to-repost ratios",
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
    tabLabel: "Popularity Rankings",
    title: "Who likes the most (and least) popular posts?",
    subtitle:
      "bar length = the average popularity of the posts they like (log of like-count)",
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
    tabLabel: "Like Timing",
    title: "How fast do posts get liked?",
    subtitle:
      "post age at the moment it's liked — search anyone to see how fast THEIR posts get picked up",
    image: "/plots/half-life.png",
    bounds: "/plots/half-life.bounds.json",
    searchable: true,
    tabAnim: "spotlight-points",
    highlight: "svg-line",
    data: {
      handles: "/plots/half-life.handles.bin",
      histograms: "/plots/half-life.histograms.bin",
      histmeta: "/plots/half-life.histmeta.json",
    },
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
    title: "Likes vs followers — every liked account",
    subtitle: "punch in your handle to light up 15 random accounts you follow",
    image: "/plots/punching.png",
    bounds: "/plots/punching.bounds.json",
    searchable: false, // uses the follows control instead of the handle search
    tabAnim: "spotlight-points",
    highlight: "follows",
    data: {
      handles: "/plots/punching.handles.bin",
      positions: "/plots/punching.positions.bin",
    },
  },
  {
    id: "wakes-up",
    tabLabel: "Activity by Hour",
    title: "When Bluesky Wakes Up",
    subtitle:
      "likes by hour of day (UTC) across the week — the base skews US/Europe, so it peaks in the American afternoon",
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
    subtitle:
      "a Lorenz curve — the deeper it bows below the diagonal, the more unequal: a sliver of posts gets most of the likes",
    image: "/plots/long-tail.png",
    searchable: false,
    tabAnim: "draw-curve",
    highlight: null,
  },
];

// Tab order, independent of the authoring order above. Kept explicit so the
// reading flow (popularity -> ratios -> timing -> reach -> inequality) is easy
// to re-tune without moving big config blocks around.
const PLOT_ORDER = [
  // 3 like plots first ...
  "like-repost",
  "half-life",
  "punching",
  // ... then the 3 popularity plots ...
  "typical-popularity",
  "popularity-curve",
  "leaderboards",
  // ... then the rest.
  "wakes-up",
  "long-tail",
  "activity",
];
const ORDERED = PLOT_ORDER.map(
  (id) => RAW_PLOTS.find((p) => p.id === id)!
).filter(Boolean);

// Resolve every asset URL (image / bounds / data.*) against the deploy base, so
// the site works at the domain root OR a sub-path. Authoring above stays as
// clean "/plots/..." paths.
export const PLOTS: PlotConfig[] = ORDERED.map((p) => ({
  ...p,
  image: p.image ? asset(p.image) : p.image,
  bounds: p.bounds ? asset(p.bounds) : p.bounds,
  data: p.data
    ? Object.fromEntries(Object.entries(p.data).map(([k, v]) => [k, asset(v)]))
    : p.data,
}));
