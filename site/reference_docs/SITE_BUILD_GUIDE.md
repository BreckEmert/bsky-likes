# Bluesky Likes — Interactive Site Build Guide (v2, decisions locked)

## What you're building

A simple, beautiful, single-purpose static website presenting ~9 data visualizations about Bluesky "like" behavior.  Each visualization is its own page.  Pages switch via a horizontal tab bar at the top, where **each tab is a small live animated preview** of that plot's visual style, with a short literal label on top.  The active plot fills the bottom ~90% of the viewport.

The defining feature is **search-to-highlight**: the user types a Bluesky handle, and the current plot highlights where that user falls.  The selection is **persistent across tabs** — searching one handle then switching tabs shows that same person highlighted on every plot where they appear.

Keep the site SUPER simple.  No backend, no auth, no router library, no state-management library.  Static site, one search box, tab switching, highlight.  That's the whole product.

---

## THE most important architectural rule

**Do NOT reimplement the matplotlib charts in a JS charting library.**

Each plot's *aggregate layer* (hexbins, density clouds, scatter masses, curves, axes, in-plot quotes) is pre-rendered in Python as a high-DPI transparent PNG.  The site displays that PNG as the plot background.  The site draws ONLY the *highlight layer* (and, for the large scatters, an interactive point layer) on top, aligned to the image via shared coordinate bounds.

Your JS job is never "recreate this colormap/hexbin/curve."  It is only: "given a user's (x, y) in data units, draw a ring/dot/line at the correct pixel over this image."  The plots will look identical to the Python originals because they ARE the originals.

The Python side (the user's `bsky_analyze.py`, provided to you, plus the export module `bsky_export_web.py`) produces per plot:
1. `<plot>.png` — rendered aggregate layer, transparent background, **title and subtitle suppressed** (those are rendered as HTML), in-plot quotes/annotations KEPT.
2. `<plot>.bounds.json` — `{ "xMin","xMax","yMin","yMax","xLog","yLog", "plotArea": {"left","top","right","bottom"} }` where `plotArea` is the pixel rectangle inside the PNG where data actually lives (inside the axes, from matplotlib `ax.get_position()` x figure pixel size).  This is what you map data coords into.
3. A per-plot lookup of searchable entities -> data coords (JSON for small plots, binary for large; see table).

Coordinate mapping (`lib/coords.ts`): `dataX -> (log10 if xLog) -> fraction across [xMin,xMax] -> pixel across [plotArea.left, plotArea.right]`.  Y the same, remembering image Y is top-down.

---

## Tech stack

- **Vite + React + TypeScript.**  No Next.js (static, no SSR benefit).
- **deck.gl** for the plots that have individually-interactive points (hover any point + search): Plots 7, 8, 9.  Use `OrthographicView` + `ScatterplotLayer`.  GPU rendering + GPU picking means hundreds of thousands of hoverable points cost effectively nothing.
- **Plain SVG/Canvas overlay** for plots where only the highlighted entity is interactive: Plots 2, 3, 5.
- **Plain HTML/CSS** for the leaderboards (Plot 6) and the static plots (1, 10).
- One stylesheet, dark theme.  Plot colors live in the PNGs.
- Deploy: static host.  `vite build` -> `dist/`.

Allowed dependencies: `react`, `react-dom`, `vite`, `typescript`, `deck.gl` (+ peers), optionally `d3-scale`.  Nothing else.

---

## Layout

```
+-------------------------------------------------------+
| [ glow  ][ ~~~~  ][ grid  ][ bars  ]   <- tab bar     |  ~10% height
| [Follows][Popular][Activity][ Most &]   each tab is   |
| [vs Tast][ Curve ][by Hour ][  Least]   a live mini   |
|                                          animation     |
| +---------------------------------------------------+ |
| |  [ search handle... ]                             | |
| |                                                   | |
| |          PLOT (PNG + highlight/deck layer)        | |  ~90% height
| |                                                   | |
| +---------------------------------------------------+ |
+-------------------------------------------------------+
```

- Tab bar across the top; horizontally scrollable on mobile.  Active tab visually distinct (brighter border/label).
- The plot PNG is letterboxed (`object-fit: contain`) so it never distorts.  The overlay (SVG or deck canvas) is positioned to exactly match the PNG's *displayed* rectangle; recompute on resize.
- Optional HTML header (title + subtitle) above the plot — see "Titles" below.
- Search box top-left over the plot, with an autocomplete dropdown.  Hidden on non-searchable plots (1, 10).

---

## Animated tab previews

Each tab background is a small looping animation themed to the plot's visual type, with the label text overlaid (readable, e.g. white text with a subtle shadow).  These are decorative — NOT real data.

Archetypes (build as a small set of reusable canvas renderers, assign one per plot):
- **spotlight-points** — scattered glowing dots; a soft radial "spotlight" drifts across, brightening dots under it.  For scatters: Plots 7, 8, 9.
- **hex-glow** — a faint hex/blob field with bins gently pulsing brightness.  For hexbins: Plots 2, 5.
- **drifting-lines** — several faint curved lines shimmering / sliding.  For Plot 3 (Power Curve).
- **draw-curve** — a single curve that repeatedly draws itself left-to-right and fades.  For Plot 1 (Long Tail / Lorenz).
- **pulse-grid** — a small grid of cells pulsing like the DoW x hour heatmap, a wave moving across.  For Plot 10.
- **rising-bars** — a few ranked bars growing/reordering.  For Plot 6 (Leaderboards).

PERFORMANCE: do NOT run 9 independent `requestAnimationFrame` loops.  Use ONE shared rAF tick that updates all visible tab canvases.  Pause animation for tabs scrolled out of view (IntersectionObserver) and when `document.hidden`.  Keep each canvas tiny (e.g. 160x64 CSS px, devicePixelRatio-aware).  These are ambient; cap effective FPS ~30.

---

## The uniform plot abstraction

Every plot page is the same component shape, configured from a manifest:

```ts
// plots.config.ts — single source of truth
export const PLOTS = [
  {
    id: "long-tail",
    tabLabel: "Attention Inequality",
    title: "How unequal is attention on Bluesky?",
    subtitle: null,
    image: "/plots/long-tail.png",
    searchable: false,
    tabAnim: "draw-curve",
    highlight: null,
  },
  {
    id: "activity",
    tabLabel: "Followers vs Taste",
    title: "Bluesky users are so kind <3",
    subtitle: "the more popular we are\nthe less popular the content we like",
    image: "/plots/activity.png",
    bounds: "/plots/activity.bounds.json",
    searchable: true,
    tabAnim: "spotlight-points",
    highlight: "deck-scatter",        // hover-any-point + search
    data: { handles: "/plots/activity.handles.bin", positions: "/plots/activity.positions.bin" },
  },
  // ... etc
];
```

Adding/removing/reordering a plot = editing this one file.

The shared `PlotPage` handles: showing the image, fitting the overlay to the displayed image rect, the search box, coordinate mapping, resize, and dispatching to the right highlight renderer based on `highlight`.

Highlight strategies:
- `"deck-scatter"` (Plots 7, 8, 9): deck.gl `ScatterplotLayer` of all points in world coords over the PNG; `onHover` -> tooltip; search/selection -> a separate ring layer + `LinearInterpolator` fly-to.  Persistent selection = keep the ring layer's data across tab switches.
- `"svg-point"` (Plots 2, 5): an absolutely-positioned SVG; selection draws a ring + label at `mapToPixel(user.x, user.y)`.
- `"svg-line"` (Plot 3): selection draws the user's own histogram as a bright polyline over the faint pre-rendered mass.  Lookup gives `handle -> Float32Array`.
- `"list-row"` (Plot 6): HTML lists; selection scrolls the user's row into view and flashes it; if absent from the shown top/bottom N, show "ranked #X of N".
- `null`: no search, static image only (Plots 1, 10).

---

## Search mechanics

- One global handle index built from the union of all plots' lookups (lowercased, `.bsky.social` normalized).
- Substring autocomplete, top ~20 matches, instant at our scale.  Strip leading `@`; match with or without `.bsky.social`.
- On select: store the selected handle in app state (persists across tabs).  Each plot's highlight renderer reads the current selection and draws it (or shows "not present on this plot").
- For deck plots, selecting also animates the view to center on the point.

---

## deck.gl specifics (Plots 7, 8, 9)

Mirror the reference `index.html` the user has (Theo Sanderson's map — same library, same patterns):
- `new deck.Deck({ views: new deck.OrthographicView({flipY:false}), controller:true, ... })`.
- Base points from a binary attribute buffer, NOT an array of objects:
  `data: { length: N, attributes: { getPosition: { value: Float32Array, size: 2 } } }`.
- World coordinates MUST match the PNG's data area.  Set the initial view so that the data bounds map onto the PNG's `plotArea` rectangle.  Verify with a known point (the user can mark a sentinel handle whose pixel position you eyeball against the PNG).
- The PNG (axes, labels, hexbin shading, quote) is the background; deck draws interactive points on top in the same world space.  If the PNG already shows the full point mass and you only need hover + highlight, you may draw points with low opacity or only draw them for picking — but for Plot 8 the user explicitly wants every point individually hoverable, so render them.
- Plot 8 ~440k points: sort points by follower count descending so a level-of-detail "show top N when zoomed out" works (`LOD_BASE * 4^zoomDelta`), exactly as in the reference file.
- Hover: `onHover` -> handle via `info.index` -> small tooltip; optionally lazy-fetch live profile from `https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=HANDLE` (reference file shows the pattern).  Keep this optional/behind a flag — it hits the network.
- Highlight ring: separate `ScatterplotLayer` (stroked, unfilled) + `TextLayer` label for the selected handle; pink, distinct from hover white.

---

## Titles, subtitles, quotes (decision: HYBRID)

- **Baked into the PNG:** in-plot movie quotes and annotations (Gekko, the Hybrid, Shannon, Warhol, Ratatouille, G-Man, the Explore/Exploit panel labels).  matplotlib positions these within the plot; leave them in the image.
- **Rendered as HTML:** the title and subtitle, as a crisp header above the plot.  Reasons: razor-sharp at any DPI, selectable/accessible/indexable, restyle without re-rendering, and the tab shows a short label while the header shows the full question.
- Therefore the Python export MUST suppress title/subtitle in the figure (do not call `set_title`/suptitle for those) but KEEP the quotes/annotations, and save with a transparent background and the axes starting at the figure edge (tight, minimal margins).

LOCKED content (render title/subtitle exactly; quotes are in the PNG):

| id | tabLabel (<=3 words) | Title (HTML header) | Subtitle (HTML) |
|---|---|---|---|
| long-tail | Attention Inequality | How unequal is attention on Bluesky? | — |
| typical-popularity | Typical Popularity | What's the typical popularity of posts you like? | Higher y = a few things you've liked blew up<br>Bottom-left = you've literally liked nothing popular |
| popularity-curve | Popularity Curve | How popular are the posts we like? | each blue line = one user's histogram of how popular their liked posts are |
| like-repost | Like/Repost Ratio | Your like-to-repost ratios | upper-left posts are reposted but not liked |
| leaderboards | Most & Least | Who likes the most (and least) popular posts? | — |
| half-life | Engagement Age | Engagement Half-Life | How fresh is a post when it gets liked? |
| activity | Followers vs Taste | Bluesky users are so kind <3 | the more popular we are<br>the less popular the content we like |
| punching | Likes vs Followers | Top 4,000 liked accounts (+ N highlighted) | — |
| wakes-up | Activity by Hour | When Bluesky Wakes Up | — |

(Plot 4 deleted.  Plot 9/9.5 merged into `punching`; it shows the base scatter with the gold-ringed highlighted authors baked into the PNG, "Anyone can cook." quote in the PNG.)

NOTE the `<3` in the Activity title is literal text the user wants (a typed heart), not an emoji — render it as the characters `<3`.  Do not "fix" it.

---

## Data contract & sizes

| id | Background | Searchable | Hover any pt | Highlight | Lookup format |
|---|---|---|---|---|---|
| long-tail | png | no | no | none | — |
| typical-popularity | png (hexbin) | yes | no | svg-point | binary (~440k): handles.bin + positions.bin ([mean,median]) |
| popularity-curve | png (density) | yes | no | svg-line | binary: handles.bin + histograms.bin (Float32 per user) |
| like-repost | png (hexbin) | yes (author) | no | svg-point | json: handle->[likeRatio,repostRatio] |
| leaderboards | html | yes | n/a | list-row | json: ordered rows {handle, value} |
| half-life | png | yes | yes | deck-scatter | binary: handles.bin + positions.bin |
| activity | png (axes/shading) | yes | YES | deck-scatter | binary (~440k): handles.bin + positions.bin, sorted by followers desc |
| punching | png (~4k + gold rings baked) | yes (author) | yes | deck-scatter | json: handle->[followers,likesPerPost] |
| wakes-up | png (heatmap) | no | no | none | — |

Binary format (reuse the reference file's scheme):
- `handles.bin`: `uint32 count`, `(count+1)` `uint32` offsets, then UTF-8 handle bytes.  Entity i <-> index i.
- `positions.bin` / `histograms.bin`: parallel `Float32Array`, same ordering.

---

## Deliverable structure

```
site/
  public/plots/
    long-tail.png
    typical-popularity.png   .bounds.json  .handles.bin  .positions.bin
    popularity-curve.png     .bounds.json  .handles.bin  .histograms.bin
    like-repost.png          .bounds.json  .lookup.json
    leaderboards.json
    half-life.png            .bounds.json  .handles.bin  .positions.bin
    activity.png             .bounds.json  .handles.bin  .positions.bin
    punching.png             .bounds.json  .lookup.json
    wakes-up.png
  src/
    main.tsx
    App.tsx                 // tab bar (animated previews) + active plot + global selection state
    plots.config.ts
    components/
      TabBar.tsx
      TabPreview.tsx        // canvas mini-animation, archetype-driven, shared rAF
      PlotPage.tsx          // image + overlay/deck + search; dispatches highlight strategy
      SearchBox.tsx
      DeckScatter.tsx       // deck.gl plots (7,8,9)
      highlights/
        SvgPoint.tsx        // 2,5
        SvgLine.tsx         // 3
        ListRows.tsx        // 6
    lib/
      coords.ts             // data<->pixel, log/linear, image-fit rect
      binary.ts             // load handles.bin / positions.bin / histograms.bin
      tabAnim.ts            // shared rAF + archetype renderers
  index.html
  package.json
```

---

## Build order

1. Scaffold.  Tab bar with animated previews + `plots.config.ts`, switching between static PNGs only (no search).  Confirm layout + responsive + the shared-rAF animation perf.
2. `coords.ts` + `PlotPage` image display with correct letterbox fit and a debug crosshair mapping a hardcoded (x,y) -> pixel; verify alignment against a known point in a PNG.
3. `SearchBox` + ONE small searchable plot end-to-end (`like-repost`, json + svg-point).  Prove search->highlight->persist-across-tabs on this one before generalizing.
4. Binary loading; wire `typical-popularity` (svg-point, 440k binary) and `popularity-curve` (svg-line, histograms).
5. `DeckScatter` for `activity` (440k, hover + search + fly-to + LOD), then reuse for `half-life` and `punching`.
6. `leaderboards` list-row.
7. Polish: persistent selection across all tabs, "not present here" notes, mobile, loading states.

Get ONE plot fully working end-to-end (image + search + highlight + resize + persist) before doing the rest.  Everything else is a variation on that proven pattern.

---

## Questions resolved (for reference, do not re-ask)
- Plot 8: BOTH hover-any-point and search-highlight (deck.gl handles both with no perf cost).
- Tab labels: literal, <=3 words (table above).
- Selection persists across tabs: YES.
- Titles/subtitles: HTML header; quotes baked in PNG.  Export suppresses title/subtitle, keeps quotes, transparent bg.
