---
name: gw-end-validations
description: End-of-gameweek validation suite for the WC2026 league. Use when the user says "validate gw end", "gw-end-validations", "check the gw before locking", "are the points/defcon/h2h/wishlist right?", or after a GW's matches finish and before finalizing/locking. Read-only by default — runs all five checks (DefCon, manager points, lineups, H2H + 'מצטיין מחזור' bonus, wishlist pick order) and reports pass/fail. Also documents the guarded resync (DefCon) and finalize/lock (H2H + standings) mutations, each of which needs explicit user OK.
---

# GW-end validations — one pass before locking a gameweek

Run after a GW's fixtures are all FT, **before** finalizing/locking. Everything in
Step 1–2 is **read-only**. The mutations (Step 3 resync, Step 4 finalize/lock) each
require explicit user authorization — the prod DB is the holiest place (see
`memory/never-mutate-prod-windows.md`).

## Step 0 — Ground rules

- Python: `/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python` (bare python lacks `firebase_admin`).
- Prod Firestore is `gamedb`. Auth with the firebase-adminsdk SA (the active gcloud
  account `ilay.asayag@...` lacks Firestore perms):
  ```bash
  SA=firebase-adminsdk-fbsvc@fpl-analyzer-792eb.iam.gserviceaccount.com
  export FS_TOKEN=$(gcloud auth print-access-token --account="$SA")
  ```
  (or the SA JSON at `/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json`).
- Real league: `lg_mock_draft`. DefCon needs WhoScored — reachable from **this Mac**
  (residential IP), 403s from datacenter/cloud.

## Step 1 — Run the full suite (read-only)

```bash
FS_TOKEN=$(gcloud auth print-access-token --account="$SA") \
  .venv/bin/python scripts/gw_end_validate.py <gw> lg_mock_draft
```

Prints PASS/FAIL for each, exits non-zero on any hard FAIL:

| Check | What it asserts |
|---|---|
| **DefCon** | every UNLOCKED fixture's DEF/MID carry `defConActions`; `defConBonus` matches DEF≥10 / MID≥12; invariant `fantasyPoints == fifaPoints − fifaBonus + defConBonus`; no null DefCon where stats have components |
| **Points** | each manager's stored `scores/{gw}` total == recomputed Σ(starters)+captain×2 from our playerScores |
| **Managers** | a lineup exists per member, 11 starters, captain (if set) is in the XI |
| **H2H** | from `schedule/{gw}` + GW points: W=3 / D=1 / L=0, plus **+1 'מצטיין מחזור'** to the top GW scorer. Verifies STORED values if finalized, else PREVIEWS them |
| **Wishlist** | the auction order (`wc_wishlist._ordered_managers` over reset waiver priority) is **last-place-first** by standings |

## Step 2 — Deep DefCon freshness (read-only, this Mac only)

`gw_end_validate` confirms DefCon is *present and self-consistent*. To confirm it
matches the **final** WhoScored line (catches a bonus frozen from a mid-match
snapshot — a real failure mode when the at-FT re-parse 403'd and the scan fell
back to ESPN but still bookmarked `scoredFinal`):

```bash
FS_TOKEN=... .venv/bin/python scripts/dryrun_defcon_compare.py <gw>
# lists, per unlocked fixture, stored vs fresh-WhoScored defcon-actions; flags
# any that cross a DEF≥10/MID≥12 threshold ("BONUS FLIPS" = real point change)
```

WhoScored rate-limits after ~8 back-to-back fetches (transient 403); just re-run.
Raw action counts drift ±1 over time (Opta restatements) — **only threshold
crossings matter for points**.

## Step 3 — Resync stale DefCon (MUTATION — needs user OK)

Only if Step 2 shows mismatches (especially BONUS FLIPS). Re-scores each named
fixture from the FINAL WhoScored line:

```bash
FS_TOKEN=... .venv/bin/python scripts/resync_defcon.py <gw> <fid> [fid ...]
```

Safety baked in: skips `dataLocked` fixtures; `ingest_whoscored_fixture` writes
**only on a successful parse** (returns an error dict without writing when WhoScored
yields no rows) so a 403/parse failure leaves stored DefCon intact — **never nulls**.
It then runs one `refresh_pool_aggregates` to recompute season + manager totals.
Re-run Step 1–2 to confirm 0 mismatches.

## Step 4 — Finalize + lock the GW (MUTATION — needs explicit user OK)

`finalize_gw(lid, gw, db, wc_client)` (`fpl_predictor/game/wc_scoring.py`) is the
machine that applies H2H + the bonus + standings. It also **auto-subs, marks
lineups `locked`, advances `currentGw`, and writes a transfer-window audit doc** —
so confirm the GW should actually advance before running it.

Two gotchas specific to this league (verified 2026-06-18):

1. **`finalize_gw` Step 1 requires `processedForFantasy` on every fixture**, but our
   WhoScored/FIFA ingest never sets it, and the legacy `process_fixture` that *does*
   set it **re-scores from api-sports and would clobber our DefCon**. So set the flag
   WITHOUT re-scoring (our playerScores are already authoritative):
   ```python
   for fx in db.collection("wc_fixtures").where("gw","==",gw).stream():
       fx.reference.set({"processedForFantasy": True}, merge=True)
   ```
2. **`dataLocked` has no code writer** — "lock the games" is a direct field write you
   do explicitly after finalizing (locks the data against any further re-scoring):
   ```python
   for fx in db.collection("wc_fixtures").where("gw","==",gw).stream():
       fx.reference.set({"dataLocked": True}, merge=True)
   ```

Order: (a) confirm Step 1/2 green, (b) set `processedForFantasy`, (c) `finalize_gw`,
(d) set `dataLocked`, (e) `reset_waiver_priority_to_standings` so the next wishlist
order reflects the new standings, (f) re-run Step 1 — H2H now VERIFIES (not preview)
and DefCon fixtures show LOCKED.

Auto-finalize note: the background poller (`api_wc.py` ~L3290) auto-finalizes when
all fixtures are `processedForFantasy`, but it first calls `process_fixture` (api-sports,
no DefCon). Treat the poller as a landmine for this league until that path is pointed
at our scores — finalize manually per above.

## Step 5 — Wishlist order invariant (known bug as of 2026-06-18)

The pick order is **inverted**: `reset_waiver_priority_to_standings`
(`wc_waivers.py`) gives the WORST team `waiverPriority=1`, but
`wc_wishlist._ordered_managers` sorts `-waiverPriority` DESC → the BEST team picks
first. Spec is **last-place-first**. Fix = make `_ordered_managers` pick the
lowest `waiverPriority` first (ascending), matching normal waivers
(`wc_waivers.get_waiver_order`) and this league's intent. `gw_end_validate`'s
Wishlist check fails until that's fixed; re-run it to confirm the fix.
