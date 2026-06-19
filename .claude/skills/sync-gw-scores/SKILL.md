---
name: sync-gw-scores
description: Sync / verify / re-bookmark WC live player scores for a gameweek. Use when the user says "sync gw scores", "update bookmark gw players data", "rescore a fixture", "did the scheduled jobs run?", "player points look stale", or after a match ends and data looks frozen. Handles - live sync, retro-scoring missed finished matches, force re-scoring an already-bookmarked fixture (post-FT FIFA corrections), and end-to-end verification against the FIFA/ESPN feeds.
---

# Sync GW scores — the one workflow for live-data drift

The live-scoring system is **self-healing by design**: every tick of any scheduler runs
`catch_up_scan` (`fpl_predictor/data/wc_live_ingest.py`), which scores live matches,
retro-scores any FINISHED match whose fixture doc lacks the `scoredFinal` bookmark,
then sets the bookmark. Bookmarked fixtures are SKIPPED forever. So:

- **Stale live match** → just trigger a tick (Step 2).
- **Finished match never scored** → a tick heals it automatically (Step 2).
- **Finished match scored too early / FIFA corrected points afterwards** → you must
  CLEAR the bookmark first (Step 3), then tick.

## Step 0 — Ground rules

- Python: `/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python` (bare python lacks firebase_admin).
- Prod Firestore: `firestore.client(database_id="gamedb")` with
  `GOOGLE_APPLICATION_CREDENTIALS=/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json`.
- Cron secret lives at `wc_config/cron.secret` (Firestore). Never commit it.
- WhoScored is BLOCKED from datacenter IPs: cloud ticks deliver FIFA points + ESPN
  stats only; **DefCon requires a tick from this Mac** (residential IP).
- Real league: `lg_mock_draft`. Its `scores/{gw}` doc holds live manager totals.

## Step 1 — Diagnose before touching anything (read-only)

Run a read-only audit and show it to the user:

```python
# for each fixture in the relevant date range / gw:
#   id, teams, kickoff, status, score, scoredFinal, scoredAt,
#   playerScores count, max(updatedAt)
# plus: wc_config/scan_state.lastScanAt  (when did ANY scheduler last tick)
# plus: tail -5 /tmp/wc_ingest.log       (Mac agent ticks)
# plus: gh run list --workflow wc-live-scores.yml --limit 5  (cloud ticks)
```

Compare stored data against the live feeds (also read-only):
`fetch_espn_match_stats("YYYYMMDD")` for status/score truth, `fetch_fifa_points()`
for current round points of 2-3 spot-check players. Decide which case you're in:

| Finding | Case | Action |
|---|---|---|
| Fixture live/finished, NOT bookmarked, data stale | missed tick | Step 2 only |
| Fixture bookmarked, stored points == FIFA now | already healed | report, stop |
| Fixture bookmarked, stored points != FIFA now | early bookmark / FIFA correction | Step 3 then Step 2 |

## Step 2 — Trigger a sync tick

Prefer the **Mac path** (full DefCon) when this Mac is on a residential network:

```bash
launchctl kickstart -k gui/$(id -u)/com.wc26.livescores   # one full tick now
sleep 50 && tail -2 /tmp/wc_ingest.log                    # confirm it ran
```

Cloud path (FIFA/ESPN only — fine for points, no DefCon), also what the user-facing
"Sync data" button calls:

```bash
KEY=$(GOOGLE_APPLICATION_CREDENTIALS=... .venv/bin/python -c "...read wc_config/cron.secret...")
curl -s -m 180 -X POST "https://fpl-analyzer-792eb.web.app/api/v1/wc/cron/ingest-live-scores?key=$KEY"
# response: {newlyFinalized, liveUpdated, alreadyBookmarked, whoscoredOk, datesScanned}
```

Note: the user endpoint `/sync-live-scores` (auth) is debounced 60s via
`scan_state.lastScanAt`; the secret-gated `/cron/...` endpoint is not.

## Step 3 — Force re-score a bookmarked fixture ("update the bookmark")

Only when Step 1 proved the stored points diverge from FIFA's current values
(e.g. the match was bookmarked minutes after FT and FIFA adjusted points later).
Confirm the fixture id with the user before clearing — this is the one
state-mutating step:

```python
db.collection("wc_fixtures").document(FID).update({"scoredFinal": firestore.DELETE_FIELD})
```

Then run a Step-2 tick: catch_up_scan sees a FINISHED, un-bookmarked fixture,
re-scores it from the freshest feeds (WhoScored if Mac, FIFA/ESPN if cloud), and
re-sets the bookmark. Idempotent — safe to repeat.

## Step 4 — Verify end to end (always; never claim success without this)

1. Fixture doc: `status` is `FT` (finished) or `LIVE`, `score` matches ESPN,
   `scoredFinal=True` for finished matches.
2. playerScores: count > 0; spot-check 2-3 players' `fantasyPoints` against
   `fetch_fifa_points()` round points (cloud-scored) — Mac-scored adds DefCon on top,
   so stored may exceed FIFA by each player's DefCon bonus; `breakdown` is itemized.
3. League totals: `leagues/lg_mock_draft/scores/{gw}.updatedAt` is fresh; if any
   manager's locked starter scored, their points moved.
4. `wc_players.gwPoints.{gw}` updated for the spot-check players.
5. Report a compact table: fixture, before → after points for the spot-checks,
   bookmark state, which feed scored it (`source` field: `whoscored+fifa` vs FIFA/ESPN).

## Known failure modes (check before inventing new theories)

- **Mac asleep / battery dead** → no local ticks; `pmset -g log | grep -E "Sleep|Wake"`.
- **GitHub Actions cron throttled** → 1-2 runs/day instead of */10; not a code bug.
- **Feed code mismatch** → a nation invisible to scoring. The verified alias table
  (all 48 teams, both feeds) is `ISO_ALIASES` in `wc_live_ingest.py`. If a NEW
  divergence appears (squad changes), diff feeds vs `wc_teams` and extend it.
- **WhoScored 403 from cloud** → expected (`whoscoredOk:false`); fallback handles it.
- **`ftScore` is ''** during live play — `finished` must come from `elapsed == "FT"`.
