# -*- coding: utf-8 -*-
"""
diagnose_likerate.py — peek at WHY the "Like-rate" champion lens produces tiny,
counter-intuitive values (e.g. @emollick at 4.4 likes/post being the *highest*).

Run cell-by-cell in Spyder (# %% blocks). Each cell prints + plots something.

TL;DR hypothesis this script checks: our posts.parquet only contains posts that a
tracked user LIKED, so `npost` (posts-per-author in our table) is ~2% of the
account's real post count. So like_rate = community_likes / npost is computed over
a tiny, like-biased sample of posts -> a meaningless denominator.
"""
# %% imports + base aggregations -------------------------------------------------
import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from bsky_likes import config

SUB = 25  # the community to drill into (25 = "Atproto Tinkerers"); change freely

members = pl.read_parquet(config.PROJECT_DIR / "cluster_members_sub.parquet").select(
    ["liker_did", "sub"]
)
N = members.height
users = pl.read_parquet(
    config.USERS_PATH, columns=["did", "handle", "followers_count", "posts_count"]
).unique("did")

posts = pl.scan_parquet(str(config.POSTS_PATH))
likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(
    ["liker_did", "post_uri", "like_created_at"]
)

# per author: how many of their posts are in OUR table + their total like_count there
per_author_table = (
    posts.group_by("post_author_did")
    .agg(
        pl.len().alias("npost_table"),
        pl.col("like_count").sum().alias("likes_table"),
        pl.col("like_count").mean().alias("mean_global_likes_per_post"),
    )
    .collect(engine="streaming")
)
print("authors in posts.parquet:", f"{per_author_table.height:,}")

# %% MISSINGNESS: posts in our table vs the account's REAL posts_count ------------
# If posts.parquet were complete this ratio would be ~1.0. The claim is it's ~0.02.
miss = (
    per_author_table.join(users, left_on="post_author_did", right_on="did", how="left")
    .filter((pl.col("posts_count") > 0) & (pl.col("npost_table") >= 20))
    .with_columns((pl.col("npost_table") / pl.col("posts_count")).alias("coverage"))
)
cov = miss["coverage"].to_numpy()
print(f"posts-table coverage of real posts:  median={np.median(cov):.3f}  "
      f"mean={np.mean(cov):.3f}  p90={np.quantile(cov,0.9):.3f}")
plt.figure()
plt.hist(np.clip(cov, 0, 0.3), bins=60)
plt.axvline(np.median(cov), color="r", ls="--", label=f"median {np.median(cov):.3f}")
plt.xlabel("npost_table / real posts_count  (1.0 = we have all their posts)")
plt.ylabel("# accounts")
plt.title("Posts-table is a tiny, like-biased SAMPLE of real posts")
plt.legend(); plt.tight_layout(); plt.show()

# %% community like-rate: distribution + the denominator problem ------------------
cmap = members.filter(pl.col("sub") == SUB).select("liker_did")
base = (
    likes.join(cmap.lazy(), on="liker_did", how="inner")
    .join(posts.select(["post_uri", "post_author_did", "like_count"]), on="post_uri", how="inner")
)
# per author IN THIS COMMUNITY: total community likes (tl) + distinct likers (uf)
likers = (
    base.group_by("post_author_did")
    .agg(pl.len().alias("tl"), pl.col("liker_did").n_unique().alias("uf"))
    .collect(engine="streaming")
)
# global likes on those posts: collapse to one row PER POST first (else like_count,
# repeated on every like row, would be massively over-summed)
postlevel = (
    base.group_by(["post_author_did", "post_uri"])
    .agg(pl.first("like_count").alias("lc"))
    .group_by("post_author_did")
    .agg(pl.len().alias("npost_here"), pl.col("lc").sum().alias("global_likes_here"))
    .collect(engine="streaming")
)
comm = (
    likers.join(postlevel, on="post_author_did")
    .join(per_author_table, on="post_author_did")
    .join(users, left_on="post_author_did", right_on="did", how="left")
)
comm = comm.with_columns([
    (pl.col("tl") / pl.col("npost_table")).alias("like_rate"),          # the lens's metric
    (pl.col("tl") / pl.col("global_likes_here")).alias("community_share"),  # alt metric
])
sub_authors = comm.filter(pl.col("uf") >= 30)
print(f"\ncommunity {SUB}: {sub_authors.height} authors with >=30 local likers")
lr = sub_authors["like_rate"].to_numpy()
print(f"like_rate: median={np.median(lr):.1f}  max={np.max(lr):.1f}  "
      f"(top accounts are ~4 because npost is sampled, not real)")
plt.figure()
plt.hist(np.clip(lr, 0, 25), bins=50)
plt.xlabel("like_rate = community likes / npost_table")
plt.ylabel("# accounts"); plt.title(f"Like-rate distribution, community {SUB}")
plt.tight_layout(); plt.show()

# %% the smoking gun: top accounts, with the REAL post count alongside -----------
cols = ["handle", "tl", "npost_table", "posts_count", "like_rate",
        "global_likes_here", "community_share", "followers_count"]
print("\nTOP 10 by like_rate (with the median-posts gate the lens uses):")
gate = float(sub_authors["npost_table"].median())
print(sub_authors.filter(pl.col("npost_table") >= gate)
      .sort("like_rate", descending=True).select(cols).head(10).to_pandas().to_string())
print("\nTOP 10 by like_rate (NO gate -> 2-post flukes):")
print(sub_authors.sort("like_rate", descending=True).select(cols).head(10).to_pandas().to_string())

# %% an alternative that DOESN'T depend on the broken denominator ----------------
# "community_share" = of all the likes this account's (sampled) posts got, what
# fraction came from THIS community. Uses posts.like_count, not a post count.
print("\nTOP 10 by community_share (alt metric, >=30 likers & >=200 global likes):")
alt = sub_authors.filter(pl.col("global_likes_here") >= 200)
print(alt.sort("community_share", descending=True)
      .select(["handle", "community_share", "tl", "global_likes_here", "followers_count"])
      .head(10).to_pandas().to_string())

# %% TEMPORAL: is the rate dragged down by posts OLDER than the like-pull window? --
# Our likes only span a few months; posts older than that lost most of their likes
# before we started pulling, so their windowed like-rate is artificially ~0.
HANDLE = "gracekind.net"  # change to any account

win = (
    likes.select(pl.col("like_created_at").min().alias("mn"),
                 pl.col("like_created_at").max().alias("mx"))
    .collect(engine="streaming")
)
print(f"\nLIKE pull window: {win['mn'][0]}  ->  {win['mx'][0]}")

did = users.filter(pl.col("handle") == HANDLE)["did"][0]
gp = (posts.filter(pl.col("post_author_did") == did)
      .select(["post_uri", "post_created_at", "like_count"]).collect(engine="streaming"))
clk = (
    likes.join(cmap.lazy(), on="liker_did", how="inner")
    .join(posts.filter(pl.col("post_author_did") == did).select("post_uri"), on="post_uri", how="inner")
    .group_by("post_uri").agg(pl.len().alias("comm_likes")).collect(engine="streaming")
)
g = (gp.join(clk, on="post_uri", how="left").with_columns(pl.col("comm_likes").fill_null(0))
     .with_columns(pl.col("post_created_at").dt.truncate("1mo").alias("mo")))
by_mo = (g.group_by("mo").agg(
    pl.len().alias("posts"),
    pl.col("like_count").mean().alias("lifetime_per_post"),
    pl.col("comm_likes").mean().alias("windowed_per_post"),
).sort("mo").to_pandas())
print(by_mo.to_string())

fig, ax = plt.subplots()
ax.plot(by_mo["mo"], by_mo["lifetime_per_post"], "o-", label="lifetime likes/post")
ax.plot(by_mo["mo"], by_mo["windowed_per_post"], "s-", label="our-window community likes/post")
ax.axvspan(win["mn"][0], win["mx"][0], alpha=0.12, color="g", label="like-pull window")
ax.set_xlabel("post creation month"); ax.set_ylabel("avg likes / post")
ax.set_title(f"@{HANDLE}: old posts read ~0 in our window (likes predate the pull)")
ax.legend(); fig.autofmt_xdate(); plt.tight_layout(); plt.show()
