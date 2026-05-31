# -*- coding: utf-8 -*-
"""Central configuration for the bsky-likes pipeline.

This module is side-effect free: it only declares constants. Anything that
needs the output directories to exist should create them itself (the `initial`
ingest mode does this).
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ----------------------------------------------------------------------------
# Identity
# ----------------------------------------------------------------------------
MY_HANDLE = "breckemert.bsky.social"

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
PROJECT_DIR = Path(r"F:/GitHub/bsky-likes-analysis/bsky_data")
LIKES_DIR   = PROJECT_DIR / "likes"
POSTS_PATH  = PROJECT_DIR / "posts.parquet"
USERS_PATH  = PROJECT_DIR / "users.parquet"

# Derived per-liker metrics (written by plots.py)
PER_LIKER_PATH = PROJECT_DIR / "per_liker.parquet"

# Plot output (sibling of the data dir, committed to the repo)
PLOTS_DIR = PROJECT_DIR.parent / "plots"

# Per-mode resumable state files (kept separate so modes never clobber each other)
STATE_PATH        = PROJECT_DIR / "state.json"          # initial
EXTEND_STATE_PATH = PROJECT_DIR / "extend_state.json"   # forward
UNCAP_STATE_PATH  = PROJECT_DIR / "uncap_state.json"    # backward

# ----------------------------------------------------------------------------
# Like collection
# ----------------------------------------------------------------------------
LIKES_PER_USER_CAP = 200
WINDOW_DAYS        = 120

# Frozen cutoff matching the original run (started ~May 22 2026; 22 - 120d).
# `backward` and `add-handles` use this so they stay aligned with the existing
# dataset instead of drifting as the wall clock advances.
WINDOW_CUTOFF = datetime(2026, 1, 22, tzinfo=timezone.utc)


def initial_window_cutoff():
    """Runtime cutoff for the `initial` mode.

    Preserves the original bsky_ingest.py behavior of `now - WINDOW_DAYS`,
    which is correct for a fresh full crawl. Distinct from the frozen
    WINDOW_CUTOFF used by the extension modes.
    """
    return datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)


# ----------------------------------------------------------------------------
# Set-A filtering (initial mode only)
# ----------------------------------------------------------------------------
MAX_FOLLOWERS_FOR_FOLLOWER_OF_MINE = 7000
MAX_FOLLOWS_FOR_FOLLOW_OF_MINE     = 300

# ----------------------------------------------------------------------------
# Variable-cap buckets (backward mode): span_days <= threshold -> extra likes
# ----------------------------------------------------------------------------
CAP_BUCKETS = [
    (14, 300),
    (21, 200),
    (28, 100),
]

# ----------------------------------------------------------------------------
# Concurrency / checkpointing
# ----------------------------------------------------------------------------
CONCURRENCY         = 8
APPVIEW_CONCURRENCY = 4
CHECKPOINT_EVERY    = 500

# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
APPVIEW = "https://public.api.bsky.app"

# ----------------------------------------------------------------------------
# Hand-picked handles for the `add-handles` mode (was bsky_ingest_supplement.py).
# Already present in the current dataset; kept here for reproducibility.
# ----------------------------------------------------------------------------
SUPPLEMENT_HANDLES = [
    "10x.bsky.social",
    "tszzl.bsky.social",
    "allenanie.bsky.social",
    "peterbhase.bsky.social",
    "assembly.bsky.social",
]

# ============================================================================
# CLEAN UNCAPPED SWEEP  (ingest.py sweep)  --  WIRED UP BUT NOT YET RUN
# ----------------------------------------------------------------------------
# A from-scratch, uncapped pull of every like back to SWEEP_SINCE, reusing the
# cached set_B population (no graph rebuild). Writes to a SEPARATE directory so
# its 4-column shards never mix with the existing capped 3-column shards.
# ============================================================================
SWEEP_SINCE      = datetime(2026, 1, 1, tzinfo=timezone.utc)
SWEEP_LIKES_DIR  = PROJECT_DIR / "likes_v2"
SWEEP_STATE_PATH = PROJECT_DIR / "sweep_state.json"

# ----------------------------------------------------------------------------
# SCHEMA NOTE -- `like_rkey` is captured by the pull workers but is NOT present
# in the data on disk yet.
#
# The likes schema now includes `like_rkey` (the like record's rkey, the last
# segment of at://<did>/app.bsky.feed.like/<rkey>). It can be passed straight
# back as a listRecords cursor, which makes future backward extension cheap
# (resume from a user's oldest captured like instead of re-paging everything).
#
# BUT the 3,168 shards already in LIKES_DIR predate this column and have only
# the original three columns. Therefore:
#   * Nothing in the CURRENT parquet exposes like_rkey -- do not rely on it
#     until a fresh pull has produced 4-column shards.
#   * A `sweep` writes to SWEEP_LIKES_DIR, keeping the two schemas in separate
#     directories. Re-running initial/forward/backward against LIKES_DIR would
#     instead create a 3-col/4-col MIX that pl.scan_parquet won't merge without
#     allow_missing_columns=True.
# ----------------------------------------------------------------------------
LIKES_RKEY_IN_EXISTING_SHARDS = False
