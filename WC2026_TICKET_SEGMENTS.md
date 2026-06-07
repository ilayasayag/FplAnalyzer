# WC 2026 — Open Validation Tickets, Segmented for Parallel Agents

Purpose: hand the open work to multiple agents with minimal collisions. Each **segment** is a
self-contained workstream (its own tickets + files + acceptance). Read the **Platform Status**
first, then pick a segment.

GitHub issues: https://github.com/ilayasayag/FplAnalyzer/issues (all labeled `validation`).

---

## Platform status (as of session 9)

**Deployed (prod, live):**
- Hosting `dist/` at cache-bust **`?v=34`**; `api` Cloud Function (2nd gen) — both on project
  `fpl-analyzer-792eb`, Firestore **named DB `gamedb`** (NOT `(default)`).
- App URL: https://fpl-analyzer-792eb.web.app/ · API prefix `/api/v1/wc` (same-origin Hosting rewrite).

**Code / VCS:**
- Everything below lives on branch **`fix/player-scores-cg-index`** → **PR #42 (OPEN, not merged)**.
  `main` does NOT yet have these fixes. **Deployed-but-unmerged drift** — review + squash-merge #42 first.
- PR #42 contents (this session): playerScores collection-group index; `reset_simulation` deletes
  `playerScores` subcollections (no orphans); `apiCall` long-timeout option (was hard-aborting at 12s);
  past-GW lineup immutability (`get_lineup`: `gw < currentGw` ⇒ historical); `gw_history` snapshot now
  freezes `starting/bench/autoSubs`; `PointsScreen` renders a finished GW from the snapshot;
  **team-strength weighting** in the simulator; **week-by-week mock simulator** (`simulate_one_gw` +
  admin endpoints `/admin/leagues/<lid>/simulate-gw` and `/sim-reset` + Tweaks-panel buttons, panel
  now opens for `window.IS_ADMIN` in prod); **auto-subs swap not drop** (squad was shrinking 15→14).
- Test suite: **160 passing** — `PYTHONPATH=. /Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python -m pytest -q`
  (run from the worktree root, NOT the main repo).

**Prod mock-league data (`lg_mock_draft`, "WC 2026 Expert Mock Draft"):**
- 8 managers; the human test account is **`netanel@wc2026.local`** (uid `u_netanel`, an admin).
  Shai validated as **`yuval@wc2026.local`** (uid `u_yuval`, **NOT** an admin).
- State drifts as people sim; use the admin Tweaks panel **"Reset mock to GW1"** / **"Simulate next GW"**
  (⚙️ bottom-right, visible to admins) to get a clean state. `windowOverride` on the league doc forces
  the transfer-window phase for testing (`none|trade|free_agents|next_gw_bid`).

**How to run / test locally:**
- Backend tests: as above (repo venv lives in the MAIN repo, not the worktree).
- Frontend: Babel-in-browser, **no build step** — edit `draft_wc_design/*.jsx`, copy changed files to
  `dist/`, bump `?v=N` in `dist/index.html`, then `firebase deploy --only hosting`. `dist/` is git-ignored.
- Backend deploy: `firebase deploy --only functions:api` (predeploy copies `fpl_predictor/` into `functions/`).
- Firestore indexes: `firebase deploy --only firestore:gamedb` (NB: `--only firestore:indexes` is broken
  with the multi-DB array config in firebase-tools 15.x — target the DB name).

**Workflow rules (hard):**
- Never push to `main`; branch → PR. Squash-merge.
- Push with `gh auth switch --user ilayasayag`, then ALWAYS switch back: `gh auth switch --user ilay-asayag`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- SA key for prod data ops: `/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json`
  + `firebase_admin.initialize_app(options={"projectId":"fpl-analyzer-792eb"})` +
  `firestore.client(database_id="gamedb")`. Never commit secrets.

**Gotchas / landmines:**
- A GW is "played/locked" in the sim when `gw < league.currentGw` — NOT via `is_locked()` (that reads
  real fixture kickoff clocks the mock doesn't have). Any historical read must use the `currentGw` rule.
- Firebase Hosting caps proxied requests at ~60s; a slow sim can 504 even though it finished server-side.
- `playerScores` is a per-fixture subcollection; deleting a fixture doc does NOT cascade — always delete
  the subcollection too (see `reset_simulation`).
- Frontend bare-lexical vs `window.*` bug class (e.g. `ME` vs `window.ME`) keeps recurring — prefer
  `window.*` for anything an async loader overwrites.

---

## Ticket index (open)

| # | ID | Area | One-liner |
|---|----|----|----|
| 43 | VT-WC | Bracket/Nav | No WC-nations bracket view; dead top-nav links; league knockout-bracket seeding display bugs |
| 44 | VT-109 | Fixtures | Fixtures tab "No fixtures scheduled" for knockout GWs; phantom GW9 arrow |
| 45 | VT-110 | Status | Status all dashes incl Total Points; sidebar doesn't follow GW selector; dead-player count mismatch |
| 46 | VT-104 | Fixtures | Pick Team: eliminated-team players show fake opponents instead of `—` |
| 47 | VT-106 | PlayerHistory | Player modal History: OPPONENT always `—`; (GW1 dup rows — likely already fixed by orphan cleanup) |
| 48 | VT-111 | League | Standings: extra row (9 in 8-mgr league); "TOP 8" label wrong; rank mismatch across views |
| 49 | VT-Wishlist | Transfers | Wishlist auction never swaps ("no upcoming gameweek, window closed"); wishlist not visible |
| 50 | VT-PointsLock | Scoring | Points panel leaks swapped-in players into PAST GWs; need unique (mgr,gw,player) snapshot rows |
| 51 | VT-StatusFlicker | Status | Status data appears ~1s then re-renders to blank `—` |
| 52 | VT-PointsNoStats | Scoring | Points panel: players with no per-GW stats still show a (season-total) score |
| 53 | VT-LeagueGW | League | No per-player points within a GW in league view; teams-with-no-fixture listed; uneven points |

---

## Segments

> Segments are ordered by suggested priority (data correctness first). File overlaps are flagged so
> two agents don't edit the same component blindly.

### S1 — Scoring snapshot & Points panel  ·  tickets #50, #52, #47
**Goal:** every GW's points reconcile from an immutable per-(manager,gw,player) record; players who
didn't feature show 0; player history is correct.
- **Backend:** `fpl_predictor/game/wc_scoring.py` — `_snapshot_gw_history` (already freezes
  starting/bench/autoSubs + per-player points/stats; ensure no player appears twice per manager-gw),
  `apply_auto_subs` (swap fix shipped), `process_fixture`. `api_wc.py` — `get_player_scores`
  (`/players/{id}/scores`, opponent join is missing → #47), `get_gw_history`.
- **Frontend:** `draft_wc_design/screens-status.jsx` `PointsScreen`/`PointsListView`;
  `components.jsx` `Pitch`/`PlayerSlot` (the `GW3_POINTS[id]` season-total fallback at ~line 229 is the
  #52 culprit — for a finished GW it must resolve to 0, not the season total);
  `player-stats-modal.jsx` History tab (#47 opponent column).
- **Status:** PR #42 already (a) freezes the snapshot and (b) makes PointsScreen render finished GWs
  from it. Verify it fully closes #50; then kill the season-total fallback (#52) and join opponents (#47).
- **Coordinate:** shares `screens-status.jsx` with S3 (different component) and `components.jsx` with S4.

### S2 — League & Standings  ·  tickets #48, #53
**Goal:** exactly N rows, consistent rank everywhere, correct round label, per-player points in a GW.
- **Backend:** `fpl_predictor/game/wc_scoring.py` `_update_standings` (~L849: rows keyed by member id;
  the "9 rows in 8-mgr league" is a stray member doc in `leagues/lg_mock_draft/members` — data clean +
  guard). Knockout round label/qualifier-count source.
- **Frontend:** `draft_wc_design/screens-data.jsx` standings render (~L380–446: "TOP 8 ENTER
  QUARTER-FINALS" label is hardcoded vs `knockoutQualifiers`); `app.jsx` STANDINGS load (~L256–308) +
  the Status sidebar "Seed #N" source (rank-mismatch #48 BUG 3); add per-player GW drill-down (#53)
  reading the `gw_history` snapshot.
- **Data task:** remove the extra/stale member row from `members` (one-time prod migration).

### S3 — Status panel & manager summary  ·  tickets #45, #51
**Goal:** stable, correct Status numbers; sidebar follows the GW selector; consistent dead-player counts.
- **Frontend only:** `draft_wc_design/screens-status.jsx` `StatusScreen`; `shell.jsx`; `app.jsx`
  (standings/gw_history loaders + `forceUpdate` flicker). #51 is the appear-then-blank flicker
  (loader resolves with a missing key → falls to `—` default); #45 is dashes + sidebar headings not
  bound to the selector + banner(3)/sidebar(2) dead-count mismatch.
- **Coordinate:** shares `screens-status.jsx` (StatusScreen) with S1 (PointsScreen) and `app.jsx` with S2.

### S4 — Fixtures, schedule & per-player opponents  ·  tickets #44, #46
**Goal:** Fixtures tab shows knockout-GW matches; no phantom GW; eliminated players show `—`.
- **Backend:** `api_wc.py` `/fixtures` endpoint + `_enrich_fixtures_with_iso` (knockout fixtures exist —
  Pick Team uses them — but the Fixtures tab gets none → check the GW/round filter for #44).
- **Frontend:** `draft_wc_design/screens-data.jsx` `FixturesScreen` (~L211: fetch + the GW-nav cap for
  the phantom GW9); `components.jsx` `getNextFixtureOpponent` (#46: return `—` when the player's nation
  has no fixture for the GW / is eliminated, instead of a fallback string).
- **Coordinate:** shares `screens-data.jsx` with S2/S6 (different components) and `components.jsx` with S1.

### S5 — WC nations bracket & navigation  ·  ticket #43  (largest; mostly net-new)
**Goal:** a real 32→1 WC-nations bracket page; wire the dead top-nav; fix league-knockout bracket display.
- **Frontend:** new bracket view + `draft_wc_design/screens-bracket.jsx` (league bracket seeding/labels);
  wire the top-nav links (currently `href="#"`) in the app shell/HTML.
- **Backend/data:** `WC2026Client` group/knockout helpers already compute eliminations + bracket; surface
  them. Reconcile the "GW4 = R32 vs SEMI-FINALS" label inconsistency.
- **Mostly independent of S1–S4** (new files) → good candidate to run in parallel.

### S6 — Transfers & Wishlist  ·  ticket #49
**Goal:** an open free-agents window + submitted bids resolve into squad swaps; wishlist is visible.
- **Backend:** `fpl_predictor/game/wc_wishlist.py` `run_auction`; `wc_windows.py`
  `current_window_from_db` / upcoming-GW logic (the "No upcoming gameweek" guard fires after the sim
  advances currentGw — auction needs a valid upcoming GW + open window); `wc_squads.py`
  `sign_free_agent`; `api_wc.py` wishlist-bid endpoints.
- **Frontend:** `draft_wc_design/screens-data.jsx` wishlist/waivers tab (show pending bids while window
  open; surface saved bids read-only when closed). Overlaps the deferred EP7/GAP-700 isolation work.
- **Coordinate:** shares `screens-data.jsx` with S2/S4 and `wc_squads.py` with S1 (different methods).

---

## Suggested order & dependencies
1. **S1 + S2** first (data/scoring correctness — everything else reads these snapshots/standings).
2. **S3, S4, S6** in parallel after S1/S2 land (they consume the corrected data).
3. **S5** any time (independent new surface).
- Merge **PR #42 to `main`** before starting, so all agents branch from the fixed baseline.
- Each agent: own branch off `main`, own PR, keep to its segment's components to avoid clobbering the
  shared files (`screens-status.jsx`, `screens-data.jsx`, `components.jsx`, `app.jsx`, `wc_scoring.py`).
