# -*- coding: utf-8 -*-
"""
export_lookups.py

Emit ONLY the per-handle search lookups for the website, without the slow,
memory-heavy full plots.py run. The lookups depend only on per_liker plus
cheap posts_df aggregations -- none of them need the 74M-row likes x posts join
that makes plots.py slow and OOM-prone. So this runs in ~1-2 min.

Produces (into site/public/plots/):
  activity.handles.bin + activity.positions.bin       (Plot 8, ~440k)
  typical-popularity.handles.bin + .positions.bin     (Plot 2, ~440k)
  leaderboards.json                                   (Plot 6)
  punching.lookup.json                                (Plot 9.5, ~4k)
  like-repost.lookup.json                             (Plot 5)

NOTE (tech debt to reconcile): the author-frame computations below are copied
verbatim from the Plot 5 and Plot 9/9.5 cells in plots.py so the lookups match
the plotted points exactly. If these ever drift from plots.py the highlights
will mis-align. A later refactor should factor these frames into one shared
helper used by both files.
"""
import sys, time
print("[0] interpreter started; importing libraries...", flush=True)
sys.stdout.flush()
_t = time.time()

import polars as pl
print(f"[1] polars imported ({time.time()-_t:.1f}s)", flush=True)
import pandas as pd
print(f"[2] pandas imported ({time.time()-_t:.1f}s)", flush=True)
from bsky_likes import config
print(f"[3] config imported ({time.time()-_t:.1f}s)", flush=True)
import export_web as ew
print(f"[4] export_web imported ({time.time()-_t:.1f}s)", flush=True)

print("[5] loading per_liker.parquet ...", flush=True)
per_liker = pl.read_parquet(config.PER_LIKER_PATH)
print(f"[6] per_liker loaded: {len(per_liker):,} rows ({time.time()-_t:.1f}s)", flush=True)

# Only the columns the author aggregations need (drops the big post_uri string
# column ~ half the bytes off disk): post_author_did, like_count, repost_count,
# plus quote_count + post_created_at for the clean filter.
print("[7] loading posts.parquet (5 of 7 columns) ...", flush=True)
posts_df = (pl.scan_parquet(str(config.POSTS_PATH))
    .select(["post_author_did", "like_count", "repost_count",
             "quote_count", "post_created_at"])
    .filter(pl.col("quote_count") >= 0)
    .filter(pl.col("post_created_at") >= pl.datetime(2023, 1, 1, time_zone="UTC"))
    .collect())
print(f"[8] posts loaded: {len(posts_df):,} rows ({time.time()-_t:.1f}s)", flush=True)
users_df = pl.read_parquet(config.USERS_PATH)
print(f"[9] users loaded: {len(users_df):,} rows ({time.time()-_t:.1f}s)", flush=True)

# --- per_liker-only lookups -------------------------------------------------
ew.export_activity(per_liker)
ew.export_typical_popularity(per_liker)
ew.export_leaderboards(per_liker, n=50)

# --- ONE 20M-row groupby feeds both like-repost and punching ----------------
# (Both the Plot 5 author_eng and the Plot 9/9.5 author frame group posts_df by
# author; doing it once roughly halves the heavy work.)
print("author aggregation (single groupby)...", flush=True)
agg = posts_df.group_by("post_author_did").agg(
    pl.col("like_count").mean().alias("avg_likes"),
    pl.col("repost_count").mean().alias("avg_reposts"),
    pl.col("like_count").sum().alias("total_likes"),
    pl.len().alias("n_posts"),
)

# like-repost (Plot 5 axes/filters): post_author_did, avg_likes, avg_reposts
author_eng = agg.filter(
    (pl.col("n_posts") >= 5)
    & (pl.col("avg_likes") >= 1) & (pl.col("avg_reposts") >= 1))
ew.export_like_repost(author_eng, users_df)
print("like-repost done", flush=True)

# punching (Plot 9/9.5): top-4000 by total_likes + highlighted authors
HIGHLIGHT_HANDLES = {
    "jcsalterego.bsky.social", "cee.wtf", "avikdey.bsky.social",
    "hankgreen.bsky.social", "ceej.online", "jefferyharrell.bsky.social",
    "invert.bsky.social", "juniorhoncho.bsky.social", "lastnpcalex.agency",
    "aly.codes", "segyges.bsky.social", "moultano.bsky.social",
    "seanmcarroll.bsky.social", "sincerely.cam", "searyanc.dev",
    "jdp.extropian.net", "timkellogg.me", "gracekind.net",
    "contrapoints.bsky.social", "3blue1brown.com", "standupmaths.bsky.social",
    "hern.bsky.social", "10x.bsky.social", "zswitten.bsky.social",
    "dave.9000ish.uk", "phillipcarter.dev", "tszzl.bsky.social",
}
author_df_full = (agg
    .filter(pl.col("n_posts") >= 5)
    .join(users_df.select(["did", "handle", "followers_count"]),
          left_on="post_author_did", right_on="did", how="inner")
    .with_columns((pl.col("total_likes") / pl.col("n_posts")).alias("likes_per_post"))
    .to_pandas())

top4000 = author_df_full.nlargest(4000, "total_likes")
highlighted = author_df_full[author_df_full["handle"].isin(HIGHLIGHT_HANDLES)]
missing = highlighted[~highlighted["handle"].isin(top4000["handle"].values)]
author_df = (pd.concat([top4000, missing], ignore_index=True)
             if len(missing) else top4000)
ew.export_punching(author_df)
print("punching done", flush=True)

print(f"\nLookups written -> {ew.SITE_PLOTS}", flush=True)
