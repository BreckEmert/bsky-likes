# ▶ RUN AFTER THE UNCAPPED SWEEP FINISHES

The `ingest.py sweep --targets clustered ...` pull writes uncapped likes to
`bsky_data/likes_v2/`. When it's done, rebuild the champions board on that clean
(un-capped, no 200/user bias) data. The global plots stay on the old capped
`likes/` — only the champions board needs the unbiased pull.

## 1. Rebuild champions from the sweep data

Git Bash:
```bash
cd F:/GitHub/bsky-likes-analysis
USE_SWEEP=1 python export_champions.py
```
PowerShell:
```powershell
cd F:/GitHub/bsky-likes-analysis
$env:USE_SWEEP=1; python export_champions.py; Remove-Item Env:\USE_SWEEP
```

- It should print **`likes source: likes_v2`** and **49/49 communities** per lens.
- If coverage drops below 49 (the `≥15-likes` superfan bar can be too high for the
  shorter sweep window), lower `FAN_MIN_LIKES` in `export_champions.py` (try 10,
  then 8) and re-run until it's 49/49 again.

### 1b. Refresh the champion profile pictures

The champion set changes with the new data, so re-fetch avatars:
```bash
python export_champion_avatars.py
```
Adds a fresh `avatars` map (handle -> CDN url) to champions.json via the public
AppView. ~15 batched calls; prints how many of the champions got an avatar.

## 2. Sanity-check

- `@markhamillofficial` should be in ~1 community under Loyalty/Devotion/
  Distinctiveness. He WILL top many communities under **Like-rate** — that's
  expected (like-rate is famous-skewed; we kept it knowingly). Watch whether the
  uncapped data makes it less absurd; if not, redefine or drop like-rate.
- Spot-check Atproto Tinkerers / SFF Bookworms look reasonable.

## 3. Commit + push (redeploys automatically)

```bash
git add site/public/explore/champions.json
git commit -m "Champions: rebuild on uncapped sweep data"
git push origin main
```

## Optional: refresh stale handles

Handles like `@codetard` are frozen at capture time (it has since renamed to
`vibe-coded.com`). The like-sweep does **not** re-fetch existing users' handles.
To refresh them, a separate user-enrich pass over the population is needed —
not wired to a CLI yet. Ask Claude to add a `refresh-users` step if you want
current handles/display-names on the board.
