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
import polars as pl
import pandas as pd

from bsky_likes import config
import export_web as ew

print("Loading per_liker / posts / users ...", flush=True)
per_liker = pl.read_parquet(config.PER_LIKER_PATH)

posts_df = (pl.scan_parquet(str(config.POSTS_PATH))
    .filter(pl.col("quote_count") >= 0)
    .filter(pl.col("post_created_at") >= pl.datetime(2023, 1, 1, time_zone="UTC"))
    .collect())
users_df = pl.read_parquet(config.USERS_PATH)
print(f"  per_liker={len(per_liker):,}  posts={len(posts_df):,}  users={len(users_df):,}",
      flush=True)

# --- per_liker-only lookups -------------------------------------------------
ew.export_activity(per_liker)
ew.export_typical_popularity(per_liker)
ew.export_leaderboards(per_liker, n=50)

# --- like-repost: author_eng (copied from Plot 5) ---------------------------
author_eng = (posts_df
    .group_by("post_author_did")
    .agg(
        pl.col("like_count").mean().alias("avg_likes"),
        pl.col("repost_count").mean().alias("avg_reposts"),
        pl.len().alias("n_posts"),
    )
    .filter(pl.col("n_posts") >= 5)
    .filter((pl.col("avg_likes") >= 1) & (pl.col("avg_reposts") >= 1)))
ew.export_like_repost(author_eng, users_df)

# --- punching: top-4000 + highlighted authors (copied from Plot 9 / 9.5) ----
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
author_stats = (posts_df
    .group_by("post_author_did")
    .agg(pl.col("like_count").sum().alias("total_likes"), pl.len().alias("n_posts"))
    .filter(pl.col("n_posts") >= 5)
    .join(users_df.select(["did", "handle", "followers_count"]),
          left_on="post_author_did", right_on="did", how="inner"))
author_df_full = author_stats.with_columns(
    (pl.col("total_likes") / pl.col("n_posts")).alias("likes_per_post"),
    (pl.col("total_likes") / pl.col("n_posts") / (pl.col("followers_count") + 1))
        .alias("engagement_ratio"),
).to_pandas()

top4000 = author_df_full.nlargest(4000, "total_likes")
highlighted = author_df_full[author_df_full["handle"].isin(HIGHLIGHT_HANDLES)]
missing = highlighted[~highlighted["handle"].isin(top4000["handle"].values)]
author_df = (pd.concat([top4000, missing], ignore_index=True)
             if len(missing) else top4000)
ew.export_punching(author_df)

print(f"\nLookups written -> {ew.SITE_PLOTS}", flush=True)
