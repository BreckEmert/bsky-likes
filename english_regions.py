# -*- coding: utf-8 -*-
"""
english_regions.py  —  language-controlled, TOPICAL regions

Finding: our like-map is one big English progressive mass + small non-English
language pockets. Forcing many clusters mostly re-discovers the language split.
To get TOPICAL labels we first remove non-English accounts, then re-cluster.

Method (uses whom-you-like as the language signal, which covers empty-bio users
via their cluster, unlike per-bio detection):
  matrix -> TF-IDF -> SVD(50)   [cached to disk; reruns are instant]
  KMeans(K_LANG)                 fine pass: language groups -> near-pure clusters
  sample bios/cluster + langdetect -> drop clusters whose bios are majority
    non-English  => English-only user set
  KMeans(TOPIC_K) on the English users -> topical regions
  render check PNG + sample 30 bios/topic -> cluster_bios_en.json (for naming)

Run:  python english_regions.py
"""
import json
import time
import urllib.parse
import urllib.request
import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

from bsky_likes import config

MIN_USER_LIKES = 50
MIN_POST_LIKERS = 4
SVD_DIM = 50
K_LANG = 140          # iter-0 fine pass (catches the big native-bio languages cleanly)
K_LANG_FINE = 340     # later iters: finer, to isolate small native-bio islands
LANG_SAMPLE = 18      # bios sampled per fine cluster for language detection
# Seed accounts flagged as sitting in non-English "outer islands" whose members
# write English bios (so language detection can't catch them). We drop each
# seed's fine-grained cluster (the island), unless it lands in a large cluster
# (i.e. it's actually English-core-embedded -> skip, don't nuke the core).
SEED_ISLANDS = ["wickedwookie.bsky.social", "egbertl.bsky.social",
                "crbelottilm.bsky.social", "hunosp.bsky.social", "lukree.bsky.social"]
SEED_ISLAND_MAXSIZE = 2500   # only treat a seed's cluster as an island if <= this
TOPIC_K = 10          # topical clusters among English users
TOPIC_SAMPLE = 30     # bios sampled per topical cluster for naming
SEED = 0
APPVIEW = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"
COORDS = config.PROJECT_DIR / "umap_coords.parquet"
Z_CACHE = config.PROJECT_DIR / "umap_tfidf_Z.npy"
DID_CACHE = config.PROJECT_DIR / "umap_tfidf_dids.json"
EN_CACHE = config.PROJECT_DIR / "english_dids.json"   # cached English user set
MEMBERS_OUT = config.PROJECT_DIR / "cluster_members_en.parquet"
REGIONS_RAW = config.PROJECT_DIR.parent / "umap_regions_en_raw.json"
BIOS_OUT = config.PROJECT_DIR.parent / "cluster_bios_en.json"
PNG_OUT = config.PLOTS_DIR / "english_topics.png"

t0 = time.time()
def el(): return f"{time.time()-t0:.1f}s"

# ---- TF-IDF SVD embedding (cached) ----------------------------------------
if Z_CACHE.exists() and DID_CACHE.exists():
    Z = np.load(Z_CACHE)
    dids = json.loads(DID_CACHE.read_text())
    print(f"[1] loaded cached Z {Z.shape} ({el()})", flush=True)
else:
    print("[1] building matrix + TF-IDF SVD...", flush=True)
    per_liker = pl.read_parquet(config.PER_LIKER_PATH)
    eu = per_liker.filter((pl.col("n_likes") > MIN_USER_LIKES) & pl.col("handle").is_not_null()
                          ).select(["liker_did", "handle"])
    likes = pl.scan_parquet(str(config.LIKES_DIR / "part-*.parquet")).select(["liker_did", "post_uri"])
    post_counts = (likes.group_by("post_uri").agg(pl.len().alias("c"))
                   .filter(pl.col("c") >= MIN_POST_LIKERS).collect(engine="streaming"))
    edges = (likes.join(eu.lazy().select("liker_did"), on="liker_did", how="inner")
             .join(post_counts.lazy().select("post_uri"), on="post_uri", how="inner")
             .collect(engine="streaming"))
    uids = eu["liker_did"].to_list(); urow = {d: i for i, d in enumerate(uids)}
    pcol = {p: j for j, p in enumerate(post_counts["post_uri"].to_list())}
    rows = np.fromiter((urow[d] for d in edges["liker_did"].to_list()), np.int32, len(edges))
    cols = np.fromiter((pcol[p] for p in edges["post_uri"].to_list()), np.int32, len(edges))
    X = csr_matrix((np.ones(len(edges), np.float32), (rows, cols)), shape=(len(uids), len(pcol)))
    keepm = np.asarray((X != 0).sum(axis=1)).ravel() >= 3
    X = X[keepm]; kept = [d for d, k in zip(uids, keepm) if k]
    Z = normalize(TruncatedSVD(SVD_DIM, random_state=SEED).fit_transform(TfidfTransformer().fit_transform(X)))
    dids = kept
    np.save(Z_CACHE, Z); DID_CACHE.write_text(json.dumps(dids))
    print(f"[1] Z {Z.shape} built + cached ({el()})", flush=True)

handle_of = dict(zip(pl.read_parquet(config.PER_LIKER_PATH)["liker_did"].to_list(),
                     pl.read_parquet(config.PER_LIKER_PATH)["handle"].to_list()))
handles = [handle_of.get(d, "") for d in dids]

coords = pl.read_parquet(COORDS)
cmap = {d: (x, y) for d, x, y in zip(coords["liker_did"].to_list(),
                                     coords["x"].to_list(), coords["y"].to_list())}
xy = np.array([cmap.get(d, (np.nan, np.nan)) for d in dids])

rng = np.random.default_rng(SEED)
prof_cache = {}

def fetch_bios(hs):
    """handle(lower) -> desc for a list of handles, via public AppView."""
    out = {}
    todo = [h for h in set(hs) if h.lower() not in prof_cache]
    for i in range(0, len(todo), 25):
        batch = todo[i:i+25]
        url = APPVIEW + "?" + "&".join("actors=" + urllib.parse.quote(h) for h in batch)
        req = urllib.request.Request(url, headers={"User-Agent": "bsky-likes-analysis/1.0"})
        got = []
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    got = json.load(r).get("profiles", []); break
            except Exception:
                time.sleep(1.0 * (attempt + 1))
        for p in got:
            prof_cache[(p.get("handle") or "").lower()] = (p.get("description") or "") + " " + (p.get("displayName") or "")
        time.sleep(0.1)
    for h in hs:
        out[h] = prof_cache.get(h.lower(), "")
    return out

# ---- language pass (cached) -----------------------------------------------
if EN_CACHE.exists():
    en_set = set(json.loads(EN_CACHE.read_text()))
    en_mask = np.array([d in en_set for d in dids])
    print(f"[2] loaded cached English set: {en_mask.sum():,} users ({el()})", flush=True)
else:
    def cluster_lang(handles_):
        """-> (dominant_lang, dominant_fraction, english_fraction, n_detections)."""
        langs = []
        for h in handles_:
            txt = prof_cache.get(h.lower(), "").strip()
            if len(txt) < 8:
                continue
            try:
                langs.append(detect(txt))
            except Exception:
                pass
        if not langs:
            return "??", 0.0, 1.0, 0
        top = max(set(langs), key=langs.count)
        return top, langs.count(top) / len(langs), langs.count("en") / len(langs), len(langs)

    # ITERATIVE drop: each pass re-clusters the survivors, so non-English that
    # didn't form a pure cluster last time re-concentrates and gets caught.
    # Append to the drop list until a pass removes < 0.4% of all users.
    print(f"[2] iterative language filter (K={K_LANG}, drop clusters whose dominant "
          f"language is non-English)...", flush=True)
    N = len(dids)
    alive = np.ones(N, bool)
    lang_tot = {}
    for it in range(7):
        idx = np.where(alive)[0]
        if len(idx) < 3000:
            break
        K = K_LANG if it == 0 else K_LANG_FINE      # finer after iter 0
        lab = KMeans(n_clusters=K, n_init=3, random_state=SEED).fit_predict(Z[idx])
        samp = {c: [handles[i] for i in rng.choice(idx[lab == c],
                    size=min(LANG_SAMPLE, int((lab == c).sum())), replace=False) if handles[i]]
                for c in range(K)}
        fetch_bios(sorted({h for hs in samp.values() for h in hs}))
        drop = np.zeros(N, bool); itlang = {}
        for c in range(K):
            top, top_frac, en, ndet = cluster_lang(samp[c])
            # drop only if a NON-English language is the clear plurality
            if ndet >= 6 and top != "en" and top_frac >= 0.45 and en < 0.5:
                drop[idx[lab == c]] = True
                itlang[top] = itlang.get(top, 0) + int((lab == c).sum())
        nd = int(drop.sum())
        alive &= ~drop
        for k, v in itlang.items():
            lang_tot[k] = lang_tot.get(k, 0) + v
        print(f"    iter {it} (K={K}): dropped {nd:,} ({sorted(itlang.items(), key=lambda x:-x[1])[:8]}) "
              f"-> {alive.sum():,} alive ({el()})", flush=True)
        if nd < 0.0015 * N:
            break

    # --- seed-island removal: drop each flagged seed's fine cluster -----------
    print("[2b] seed-island removal...", flush=True)
    idx = np.where(alive)[0]
    flab = KMeans(n_clusters=K_LANG_FINE, n_init=3, random_state=SEED).fit_predict(Z[idx])
    hl = [(handles[i] or "").lower() for i in range(N)]
    for seed in SEED_ISLANDS:
        try:
            si = hl.index(seed)
        except ValueError:
            print(f"    {seed}: not in dataset", flush=True); continue
        if not alive[si]:
            print(f"    {seed}: already removed", flush=True); continue
        pos = np.where(idx == si)[0]
        if not len(pos):
            continue
        c = flab[pos[0]]; members = idx[flab == c]
        if len(members) <= SEED_ISLAND_MAXSIZE:
            alive[members] = False
            print(f"    {seed}: dropped island of {len(members):,}", flush=True)
        else:
            print(f"    {seed}: in large cluster ({len(members):,}) -> English-core, skipped", flush=True)

    en_mask = alive
    print(f"[2] kept {en_mask.sum():,} English; dropped {(~en_mask).sum():,} non-English "
          f"({lang_tot} + seed islands) ({el()})", flush=True)
    EN_CACHE.write_text(json.dumps([dids[i] for i in np.where(en_mask)[0]]))

# ---- topical pass on English users ----------------------------------------
print(f"[3] KMeans({TOPIC_K}) topical pass on English users...", flush=True)
Zen = Z[en_mask]; iden = np.where(en_mask)[0]
topic = KMeans(n_clusters=TOPIC_K, n_init=6, random_state=SEED).fit_predict(Zen)

# export members + regions
mem_did = [dids[i] for i in iden]; mem_h = [handles[i] for i in iden]
pl.DataFrame({"liker_did": mem_did, "handle": mem_h, "topic": topic}).write_parquet(MEMBERS_OUT)
regions = []
for c in range(TOPIC_K):
    m = topic == c; gi = iden[m]
    pts = xy[gi]; pts = pts[~np.isnan(pts[:, 0])]
    regions.append({"id": int(c), "x": float(pts[:, 0].mean()), "y": float(pts[:, 1].mean()),
                    "size": int(m.sum())})
REGIONS_RAW.write_text(json.dumps(regions))

# render check PNG (topical colors on the existing nebula)
plt.rcParams.update({"figure.facecolor": "#0e1116", "axes.facecolor": "#0e1116"})
fig, ax = plt.subplots(figsize=(16, 16))
pal = plt.get_cmap("tab20")(np.arange(20))
col = pal[topic % 20]
gi = iden
ax.scatter(xy[gi, 0], xy[gi, 1], c=col, s=2, alpha=0.5, linewidths=0)
for c in range(TOPIC_K):
    m = topic == c; pts = xy[iden[m]]; pts = pts[~np.isnan(pts[:, 0])]
    ax.text(pts[:, 0].mean(), pts[:, 1].mean(), str(c), color="white", fontsize=13,
            ha="center", va="center")
ax.set_title(f"English-only topical KMeans({TOPIC_K})", color="#e6edf3")
ax.set_xticks([]); ax.set_yticks([])
fig.savefig(PNG_OUT, dpi=110, facecolor="#0e1116")

# ---- sample bios per topic for naming -------------------------------------
print("[4] sampling bios per topic for naming...", flush=True)
tsamp = {c: [mem_h[i] for i in rng.choice(np.where(topic == c)[0],
             size=min(TOPIC_SAMPLE, (topic == c).sum()), replace=False) if mem_h[i]]
         for c in range(TOPIC_K)}
fetch_bios(sorted({h for hs in tsamp.values() for h in hs}))
out = []
for c in range(TOPIC_K):
    blist = [{"handle": h, "desc": prof_cache.get(h.lower(), "").strip()} for h in tsamp[c]]
    blist = [b for b in blist if b["desc"]]
    out.append({"id": c, "size": int((topic == c).sum()), "bios": blist})
BIOS_OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"[OK] {MEMBERS_OUT.name}, {REGIONS_RAW.name}, {BIOS_OUT.name}, {PNG_OUT.name} "
      f"({el()} total)", flush=True)
