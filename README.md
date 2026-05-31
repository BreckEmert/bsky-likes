# Bluesky Likes Analysis

Measuring **taste mainstreaminess** on Bluesky: how popular are the posts a
user likes, relative to the user's own reach? The centerpiece is a
"basic-bitch index" — the degree to which someone's likes land on already-popular
posts, controlled for post popularity and the user's own follower count.

Inspired by Theo Sanderson's [Bluesky Map](https://bluesky-map.theo.io/).

## What it does

1. **Capture** the like behavior of every user within 2 follow-hops of a seed
   account (`@breckemert.bsky.social`).
2. **Enrich** each liked post with its global popularity (like / repost / reply /
   quote counts) and each user with their follower / follow / post counts.
3. **Analyze** the result — per-user mainstreaminess metrics plus ~10 exploratory
   plots.

## Data scope

- **Set A** = (your followers ∪ your follows), filtered to drop broad-audience
  intermediaries:
  - drop followers of mine with > 7,000 followers
  - drop follows of mine with > 300 follows
- **Set B** = the union of followers of everyone in the filtered set A.
- **Per user in B**: their most-recent ≤ 200 likes within a 120-day window.

## Repository layout

```
bsky_likes/          shared library
  config.py          all paths, caps, window cutoffs, concurrency, APPVIEW
  client.py          async HTTP client, DID→PDS resolution, pagination, ts parsing
  graph.py           set A / set B construction (initial crawl only)
  likes.py           per-user pull loops + orchestration + parquet sharding
  enrich.py          post / user enrichment via the public AppView
  state.py           resumable JSON checkpoint state
ingest.py            CLI entry point (initial | forward | backward | add-handles | sweep)
health_check.py      dataset integrity scan
plots.py             metrics + plots (runs top-to-bottom or as Spyder # %% cells)
plots/               generated figures (committed)
bsky_data/           dataset — gitignored (large; contains user DIDs)
```

## Dataset (`bsky_data/`, gitignored)

| File | Contents |
|---|---|
| `likes/part-*.parquet` | ~3,168 shards · ~74M like events · ~441k users · ~128 days |
| `posts.parquet` | ~19.9M enriched posts (like/repost/reply/quote counts) |
| `users.parquet` | ~1.35M profiles (follower/follow/post counts) |
| `per_liker.parquet` | derived per-user mainstreaminess metrics |
| `state.json`, `extend_state.json`, `uncap_state.json` | resumable ingest checkpoints |

`bsky_data/` is gitignored because it is large and embeds user DIDs. The
backup folders (`bsky_data BACKUP/`, etc.) and console logs (`*_run.txt`) are
ignored for the same reason.

## Ingest

A single CLI with four subcommands (replacing the original four scripts):

```bash
python ingest.py initial [--test-seconds N]   # full 2-hop crawl + enrich (foundational run)
python ingest.py forward                       # pull NEW likes since each user's last capture
python ingest.py backward                      # variable-cap backfill for heavy, short-span users
python ingest.py add-handles [HANDLE ...]      # append likes for specific handles
python ingest.py sweep [--since DATE] [--targets all-b|known-likers]   # clean UNCAPPED pull (NOT YET RUN)
```

- **`initial`** builds A→B and does the first full capture. `--test-seconds N`
  runs for N seconds then prints a full-run projection instead of enriching.
- **`forward`** extends each user's captures up to the present.
- **`backward`** raises the cap for users who hit 200 likes within a short span
  (≤14/21/28 days → +300/200/100 older likes).
- **`add-handles`** appends a hand-picked list of handles (defaults to
  `config.SUPPLEMENT_HANDLES`).

- **`sweep`** is a clean, **uncapped** re-pull of every like back to `--since`
  (default 2026-01-01), reusing the cached `set_B` so the social graph isn't
  rebuilt. It writes 4-column shards (see schema note) to a **separate**
  `likes_v2/` directory. **It has not been run** — it's wired up and ready, but
  uncapping means far more data than the current 74M, so it's a deliberate,
  large job.

The extension modes only **append** new shards and enrich **newly-seen** posts
and authors — they never rewrite existing shards or re-snapshot existing posts,
and each keeps its own resumable state file.

### Schema note: `like_rkey`

The pull workers now also capture **`like_rkey`** — the like record's rkey,
which can be passed straight back as a `listRecords` cursor to make future
backward extension cheap (resume from a user's oldest captured like instead of
re-paging everything). **This column is not in the existing data yet:** the
3,168 shards in `likes/` predate it and have only the original three columns
(`liker_did`, `post_uri`, `like_created_at`). Nothing should rely on
`like_rkey` until a fresh pull has produced 4-column shards — see
`config.LIKES_RKEY_IN_EXISTING_SHARDS` (currently `False`). The `sweep` mode
writes its 4-column shards to a separate directory specifically so the two
schemas never mix.

**Window cutoff:** `initial` uses `now − 120 days`; the extension modes use a
frozen cutoff (`2026-01-22`) so they stay aligned with the original dataset
instead of drifting as the clock advances. Both live in `bsky_likes/config.py`.

## Health check

```bash
python health_check.py 2>&1 | tee health_check.txt
```

Scans shard inventory & schema consistency, null/duplicate/format checks,
posts/users coverage, and cross-table integrity (URI-encoded author DIDs vs
`posts.parquet`). Note: it loads all like rows into memory, which is heavy on
the full dataset.

## Analysis

```bash
python plots.py
```

Computes four per-liker "mainstreaminess" scorers — mean raw popularity, mean
log-popularity, mean popularity-percentile, and mean IDF weight — and renders
9 figures to `plots/` (long-tail / Gini, Hipster Index, Power Curve,
like:repost manifold, Explore/Exploit leaderboards, engagement half-life,
follower-vs-taste, punching-above-weight, day/hour heatmap). The file is
organized into `# %%` cells for Spyder.

> Tip: if you hit a GUI-backend crash under Spyder, run `plots.py` from a
> plain terminal so matplotlib uses a non-interactive backend.

## Install

```bash
pip install -r requirements.txt
```

Python 3.12. Ingest needs `httpx` + `polars`; analysis additionally needs
`numpy`, `pandas`, `pyarrow`, `matplotlib`, and `scipy`.

## Status

Dataset captured and validated. Codebase consolidated into a shared
`bsky_likes` library behind a single ingest CLI.
