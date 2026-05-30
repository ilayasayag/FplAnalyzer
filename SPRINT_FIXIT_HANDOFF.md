# WC 2026 Fantasy — Implementation Handoff (end-to-end)

**Audience:** the implementation (worker) agent.
**Reviewer:** the manager/review agent validates each phase against its **✅ Acceptance** checks before the next phase starts.
**Base branch:** `fix/mock-league-crash-and-seeding` (Phase 0 already committed here at `d122b2c`).
**Work branch:** create `fix/data-truth-and-schema` off the current HEAD of `fix/mock-league-crash-and-seeding`.
**Do not** start a phase until the previous phase's Acceptance checks pass and are committed.

---

## 0. Orientation (read before touching anything)

- **Repo:** `/Users/ilay/RiderProjects/fpl_analyzer`
- **Backend:** Flask blueprint `fpl_predictor/api_wc.py` (`/api/v1/wc/…`); game engine in `fpl_predictor/game/wc_*.py`; data client `fpl_predictor/data/wc_api.py` (`API_KEY` lives here — the single source of truth, loaded from `secrets.json`/`FOOTBALL_API_KEY`).
- **Frontend:** `draft_wc_design/` — vanilla React via Babel-in-browser, **no npm/build**. Globals are defined in `data.jsx` and overridden at runtime in `app.jsx`.
- **DB:** Firestore named database `gamedb` (project `fpl-analyzer-792eb`). Admin SDK bypasses security rules.
- **Production:** Firebase **Cloud Functions** — `functions/main.py` wraps the Flask `app` in `https_fn.on_request`. Serverless: instances freeze between requests. (This drove the Phase 0 poller decision.)
- **Emulator:** Firestore `localhost:8080`, Auth `localhost:9099`.
- **Tests:** `test_simulation.py` (Simulations 1–5) — **the regression gate for every phase**:
  ```bash
  export FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FPL_TESTING=true
  .venv/bin/python test_simulation.py
  ```
  All 5 must print success at the end.

### The product: TWO platforms in parallel (core requirement)
We run two environments, ideally as **two leagues in one `gamedb`**, switched via the existing `activeLid` mechanism (manager decision — topology option (a)):

- **Platform A — Simulation / "time machine" (`lg_sim`).** A fully seeded league with all GWs simulated via the *real* engine. The UI must let you step **forward/back GW-by-GW** and see standings, scores, lineups, and bracket **as they were at that GW**. For confidence/demo — watch a whole season play out. (Built in **Phase A**.)
- **Platform B — Real draft (`lg_real`).** The actual product: **7 managers**, **empty of results** before June, status `pre_draft`/`drafting`, but with the **full confirmed player pool of all 48 WC teams**, filterable by nation, and a **draft flow validated not to crash**. (Built in **Phase B**.)

### Framing facts (do not lose these)
1. **Today = 2026-05-30; WC kickoff ≈ June 2026.** No real fixture/score data can exist yet. The goal is **single-source-of-truth: every screen reads from the DB** (seeded now → real later via the *same* queries), NOT "replace fake with real."
2. **WC-progress modeling:** design the schema *full* (group standings + team advancement) but **populate minimal** (just `eliminated`) for now; backfill when real results arrive (manager decision).

### Ground rules
1. Stage files **by name** — never `git add .` (a previous `git add .` swept 14k lines).
2. One commit per numbered step; clear messages.
3. After every phase, run the full test suite — it must still pass.
4. Never commit `secrets.json`, `draft_wc_design/firebase.jsx`, `__pycache__/`, or anything under `scratch/`.
5. New env var / index → document it in this file under the relevant phase.

### Manager decisions locked in (2026-05-30)
- **League scope:** one persistent real league for the friend group (Platform B).
- **Production runtime:** stay on **Cloud Functions**; live scoring driven by **Cloud Scheduler → `POST /admin/process-live-fixtures`**, NOT an in-process daemon. (Phase 0 made the import-time poller opt-in.)
- **Platform topology:** two leagues in one `gamedb` (`lg_sim` + `lg_real`).
- **Player pool:** complete all 48 teams now from api-sports.io, mark squads `provisional`, refresh when FIFA confirms (~early June). Needed for Platform B.
- **WC modeling:** design full, populate `eliminated` only.

---

## ✅ Phase 0 — SECURITY — **DONE** (committed `d122b2c`)

Already landed on `fix/mock-league-crash-and-seeding`. Listed here so you don't redo it and so you know the new helpers/flags exist:

- **Backdoor removed.** `/admin/seed-test-leagues` no longer accepts `?secret=<api-key>`. It now calls `_require_admin()` (auth + `wc_config/tournament.adminUids` allowlist) and refuses to run against production unless `WC_ALLOW_PROD_SEED=true` (emulator always allowed).
- **New helper `_require_admin()`** (`api_wc.py`, just after `_require_auth`): **fail-closed**, with a single exception — a fresh emulator with no `adminUids` yet is allowed (bootstrap), so local dev can seed. Use this helper for any new admin route.
- **`save_config` fail-open fixed** — it now uses `_require_admin()` too (previously any authed user passed when `adminUids` was empty). Phase 0 closed this; do not reopen it.
- **Seed self-registers admin:** the seed writes the seeding user's uid into `adminUids`, so the bootstrap gate self-closes after first run.
- **API key de-hardcoded** in `populate_emulator_real_squads.py` (imports `API_KEY` from `wc_api`).
- **Import-time poller is opt-in:** `api.py` only auto-starts the daemon when `WC_ENABLE_POLLER=true` (and not `FPL_TESTING`). `run_server` (local dev) still starts it explicitly. Cloud Functions no longer spawns threads on cold start.

**New env vars:** `WC_ALLOW_PROD_SEED` (allow seeding against prod), `WC_ENABLE_POLLER` (long-running hosts only).
**Outstanding (user-owned, non-blocking):** add the real production admin Firebase UID to `wc_config/tournament.adminUids`. The emulator bootstrap means this does not block any phase.

---

## Phase 1 — Truth in data (biggest visible win)

### Problem
1. **Silent fallback:** every real fetch in `app.jsx` is guarded `if (data && data.length > 0)`, so a failed/empty fetch quietly keeps the mock global — you can't tell real from fake on screen.
2. **Inline hardcoded literals** baked into JSX — no query feeds them, so seeding the DB does nothing for these.

### P1.1 — Fail *loud*, with a 3-state data-source banner
In `draft_wc_design/app.jsx` + `shell.jsx`, drive a banner off real fetch state:
- **down** — a critical fetch (league details, players, standings) failed → ⚠️ "DEMO DATA — backend not reached."
- **simulated** — backend OK and the active league is `lg_sim` (or any league whose results are seeded/simulated) → "Simulated data."
- **live** — backend OK and real results exist (post-kickoff) → no banner / "Live."
Set `window.__DATA_SOURCE__` to one of `down|simulated|live` at the end of `loadInitialData()` (and in its `catch`). Render in `shell.jsx` TopBar. This makes mock **visible**; it does not remove it yet.

### P1.2 — Replace inline literals with fetched values (or explicit empty/loading states)
Per screen: bind to the real global (populated by `app.jsx`) or, if no source exists yet, render `—` / "No data". **Never invent new fake values.**

| Screen / file | Lines | Hardcoded thing → required change |
|---|---|---|
| `screens-status.jsx` | 74, 79–80 | "65" GW pts, "7th", "179 fpts" → `STANDINGS.find(s=>s.uid===ME)` (rank, fpts) + live GW score; else `—`. |
| `screens-status.jsx` | 90–104 | day timeline → bind to real fixtures or drop; no fake dates. |
| `screens-status.jsx` | 143–149 | "Standout XI" hardcoded ids+pts → bind to real top scorers or remove. |
| `screens-status.jsx` | 426–434 | hardcoded GW4 fixtures → bind to `SCHEDULE`/real fixtures or remove. |
| `screens-status.jsx` | 272–274 | synthesized mins/g/a → real `playerScores.stats` (Phase 3.5) or `—`. |
| `shell.jsx` | 34–38 | TopBar "Ilay Asayag" → real `user.displayName`; `GW{currentGw}` from real tournament state (Phase 3.1). |
| `shell.jsx` | 106–167 | Sidebar "Seed #7", "65", "179", "Portugal/Group C", "WC26-Q7XN", "out of 10" → `STANDINGS`/`LEAGUE.inviteCode`/`LEAGUE.maxMembers`/real squad; `—` if missing. |
| `player-stats-modal.jsx` | 296–375 | entire history/fixtures/ICT synthesized → blocked on Phase 3.5. For now: "Detailed stats coming soon", not synthetic rows. |
| `screens-data.jsx` | 381–382 | fabricated H2H scores `50+((gw+i)*7)%30` → real `scores/{gw}` per manager; unplayed GW shows `—`. |
| `screens-data.jsx` / `screens-bracket.jsx` | 338 | hardcoded `oppMap {ARG:"ECU",…}` → real fixture opponent or omit column. |
| `screens-bracket.jsx` | 12–28 | dead `qfResults`/`sfResults` ("Lock in 36h") keyed `qf1` not real `qf_1v8` → delete; drive off `BRACKET.rounds`. |
| `screens-bracket.jsx` | 121–145 | "Path to Glory" (Tiki-Taka FC, Jul 1–4) → bind to `BRACKET` or remove. |
| `screens-bracket.jsx` | 218–235, 598–602 | "Window 3 · THE BIG ONE", fixed dates, fake transfer history → `WINDOW`/`transactions` or remove. |
| `screens-draft.jsx` | 302–315 | "10 managers", "#7/10", "179", "65" → real `LEAGUE.maxMembers` + standings. |
| `screens-draft.jsx` | 362–375 | fake "Friends are playing" list → real `MANAGERS` or remove. |

### ✅ Phase 1 Acceptance
- [ ] API **stopped** → "down" banner on every screen. API **running + real seeded league** → banner reflects `simulated`/`live`; numbers on Status/Sidebar/Standings/Schedule/Bracket match Firestore (reviewer spot-checks 5).
- [ ] `grep -rn "179\|Tiki-Taka\|WC26-Q7XN\|Lock in 36h\|THE BIG ONE\|Ilay Asayag" draft_wc_design/` → nothing.
- [ ] Player modal shows a placeholder, not synthetic history.
- [ ] Full test suite still passes.

---

## Phase 2 — One source of truth for scoring

### Problem
`seed_mock_league` (`api_wc.py` ~line 1054) contains a **second** `compute_player_points` (`api_wc.py:1321`) that duplicates `wc_scoring.py:compute_player_points` and writes `scores`/`standings`/`knockout` **directly**, bypassing `finalize_gw`. Seeded data diverges from the live engine (auto-subs, captain, bonus, H2H tiebreaks).

### P2.1 — Seed via the real engine
- Delete the local `compute_player_points` inside `seed_mock_league`.
- Seed writes only **raw inputs**: `wc_fixtures` (with `score`, `processedForFantasy=false`) and per-fixture `playerScores` produced by the **engine** path (`process_fixture`), then call `finalize_gw(lid, gw, db, wc_client)` for each GW.
- Remove direct `.set()` to `scores/{gw}`, `standings/current`, `knockout/bracket` — those must come from `finalize_gw`/`seed_knockout`/`advance_knockout_bracket`.
- Net effect: seeded standings/bracket are **identical** to a real run. (This is also the foundation Phase A's per-GW snapshots build on.)

### P2.2 — Collapse the three seeding paths
Three exist today: `seed_mock_league` (in the API), `populate_emulator_real_squads.py`, `populate_production_real_squads.py`. Consolidate into **one** module `fpl_predictor/seed/seed_league.py` with `emulator` vs `production` flag; the admin endpoint calls into it instead of holding ~450 lines.

### ✅ Phase 2 Acceptance
- [ ] `grep -n "def compute_player_points" fpl_predictor/api_wc.py` → nothing (only the engine copy in `wc_scoring.py` remains).
- [ ] Seeded `standings/current` + `knockout/bracket` are produced by `finalize_gw`/`seed_knockout` (verify via log line or that the seed no longer `.set()`s those paths).
- [ ] New test: seed GW1–3 via engine path → standings equal Simulation 1's values for the same inputs.
- [ ] Full test suite still passes.

---

## Phase 3 — Schema depth (the "deep DB lookup")

### Target schema (converge on this)
```
wc_config/tournament         { rules, adminUids[], winner, topScorer }
wc_gameweeks/{gw}            { gw, wcRound, label, startDate, endDate, isKnockout, locked }   ← NEW (3.1)
wc_teams/{teamId}            { id, name, isoCode, group,
                               status: "group"|"advanced"|"eliminated",   ← NEW (3.2)
                               roundReached, eliminatedAfterGw }
wc_group_standings/{group}   { group, teams:[{teamId,P,W,D,L,GF,GA,GD,Pts,rank}] }  ← NEW (3.2)
wc_players/{playerId:int}    { id:int, name, position(1-4), teamId, teamIso, totalPoints, draftRank }
wc_fixtures/{fixtureId:int}  { id, gw, wcRound, homeTeam{}, awayTeam{}, score{}, status, processedForFantasy }
  └─ playerScores/{playerId:int}  { gw, fantasyPoints, stats{minutes,goals,assists,cleanSheet,...} }  ← add gw (3.5)
leagues/{lid}                { …, status (one enum, 3.4), currentGw, leaguePhaseGws[], knockoutStartGw }
  ├─ members/{uid}           { displayName, teamName, draftPosition, waiverPriority, predictions{} }
  ├─ squads/{uid}            { players:[{playerId:int, position, draftedRound}] }   ← int ids only (3.3)
  ├─ lineups/{uid}_{gw}      { starting[], bench[], formation[], captain, viceCaptain, autoSubsMade[] }
  ├─ scores/{gw}             { processed, results:{uid:{points}} }
  ├─ standings/{gw}          { managers:[…] }       ← per-GW snapshots, not just /current (Phase A)
  ├─ schedule/{gw}           { gw, matches:[{home,away}] }
  ├─ knockout/bracket        { seeds[], rounds:{qf?,sf,final} }
  └─ transactions | trades | waivers | transfer_windows | draft/*
```

### P3.1 — Persist gameweeks
The 8-GW calendar lives only in `fpl_predictor/game/wc_gameweeks.py` (`_GW_CONFIG`). Seed a `wc_gameweeks` collection from that config (one doc/GW). Add `GET /api/v1/wc/gameweeks`. `app.jsx` populates `TOURNAMENT.gwDates`/`currentGw` from it (not the `data.jsx` mock). Keep `wc_gameweeks.py` as the single seed source. **Calendar is editable** (manager decision) — store in DB, but the Python config remains the canonical seed input.

### P3.2 — Group standings + team WC status
- Add `wc_teams.status` (`"group"|"advanced"|"eliminated"`) + `roundReached`. **Populate `eliminated` only for now** (design full, populate minimal).
- Add `wc_group_standings/{group}` computed from `wc_fixtures` (P,W,D,L,GF,GA,GD,Pts). Compute in the fixture-processing path (extend `wc_api.py:compute_group_eliminations`).
- Expose `GET /api/v1/wc/teams` and `GET /api/v1/wc/group-standings`.

### P3.3 — Player-ID type consistency (known bug)
`wc_players` is keyed by `str(int)`, but `populate_production_real_squads.py:133` seeds squads with **string slugs** (`p_kane`) — they never join.
- **Integers everywhere** for `playerId`.
- Fix the production populate script to use the same int ids as `wc_players`/`wc_seeded_data.json`.
- Audit `squads`, `lineups`, `playerScores` for remaining slug ids.

### P3.4 — Unify the league `status` enum
Engine lifecycle writes `"group_phase"` (`wc_leagues.py:370`); seed writes `"active"` (`api_wc.py:1068`); `populate_production_real_squads.py:91` writes `"knockout"`/`"pre_draft"`. `_propagate_to_leagues` matches only `("group_phase","knockout")` (`wc_scoring.py:410-411`), so seeded `"active"` leagues **never get live-score propagation**, while the finalize-poller's *inverted* filter (`skip complete/pre_draft/drafting`, `api_wc.py:~1774`) *does* run on them — the two disagree.
- Canonical lifecycle: `pre_draft → drafting → group_phase → knockout → complete`.
- Seed/populate use `group_phase`/`knockout` — never `active`.
- Make the finalize-poller filter **positive**: `if status not in ("group_phase","knockout"): continue` so both paths agree.

### P3.5 — Per-player-per-GW scores + indexes
- Add `gw` to each `playerScores` doc so `(player, gw)` is directly queryable (drives the real player-stats endpoint and kills the modal synthesis from Phase 1).
- Add `GET /api/v1/wc/players/{pid}/scores` → per-GW history.
- Declare Firestore indexes for `.where(...).order_by(...)` queries: `wc_fixtures.where(gw)`, `playerScores.where(gw)`, `leagues.where(status)`, `transfer_windows.where(status).limit()`, `transactions.order_by(timestamp)`. Put them in `firestore.indexes.json`, reference from `firebase.json`.

### ✅ Phase 3 Acceptance
- [ ] `GET /gameweeks`, `/teams`, `/group-standings`, `/players/{pid}/scores` all return real DB data.
- [ ] No string-slug player ids: `grep -rn '"p_' populate_*.py fpl_predictor/` → nothing in squad/lineup/score writes.
- [ ] `grep -rn '"status": "active"' fpl_predictor/api_wc.py populate_*.py` → nothing for league docs.
- [ ] Reviewer confirms `_propagate_to_leagues` and the finalize-poller use the **same** status set.
- [ ] `firestore.indexes.json` exists and lists the queried fields.
- [ ] Player modal shows real per-GW history.
- [ ] Full test suite still passes (add group-standings + status-enum propagation cases).

---

## Phase A — Simulation time-machine (Platform A, `lg_sim`)

### Goal
One league seeded with **all 8 GWs** simulated via the real engine, with **per-GW snapshots** so any past GW is queryable, and a UI selector to move forward/back and view "state as of GW N."

### A.1 — Per-GW snapshots
Building on Phase 2 (seed via real engine) + Phase 3 (`standings/{gw}`):
- Write `standings/{gw}` for every finalized GW (not just `standings/current`).
- Ensure `scores/{gw}` and `lineups/{uid}_{gw}` exist per GW (engine already writes these — verify).
- Snapshot **bracket state per GW** (e.g. `knockout/bracket_gw{gw}` or a `bracketByGw` map) so the bracket can be shown as it was at that GW.

### A.2 — GW selector in the UI
- Add a GW selector (e.g. in `shell.jsx`/Status) that loads "state as of GW N": reads `standings/{gw}`, `scores/{gw}`, per-GW lineups, and the bracket snapshot.
- Forward/back stepping. When viewing a past GW, the `simulated` banner stays on.

### ✅ Phase A Acceptance
- [ ] `lg_sim` seeded with all 8 GWs via the real engine (no direct scorer).
- [ ] `standings/{gw}` exists for each finalized GW; selecting GW N shows that GW's standings/scores/lineups/bracket.
- [ ] Stepping forward/back changes the on-screen state correctly; values match Firestore per GW.
- [ ] Full test suite still passes.

---

## Phase B — Real-draft readiness (Platform B, `lg_real`)

### Goal
One league (`lg_real`): **7 members, no results**, status `pre_draft`/`drafting`, with the **complete 48-team player pool** (nation-filterable) and a **crash-proof draft**.

### B.1 — Complete the player pool (BLOCKER — data gap)
`wc_seeded_data.json` has **48 teams but only 857 players across 30 teams — 18 teams have ZERO players**. Platform B's "draft any of 48 nations, filter by nation" cannot be met.
- Pull confirmed squads for the missing 18 teams from api-sports.io (use `populate_emulator_real_squads.py`, which now imports `API_KEY` correctly).
- Mark squads **`provisional: true`**; plan a refresh when FIFA confirms (~early June).
- Keep **integer player ids** (Phase 3.3). Target ≈ 48×23–26 ≈ 1,100–1,250 players.

### B.2 — Nation filter on the draft board
- Ensure the draft board (`screens-draft.jsx`) filters the pool by nation/`teamIso` across all 48 teams.

### B.3 — Draft stress-test (crash-proof)
- Add a new Simulation in `test_simulation.py`: snake draft for **7 managers** over the **full pool**, exercising watchlist, pick timeout/autopick, and concurrent picks. Must run **end-to-end without error**.

### ✅ Phase B Acceptance
- [ ] All 48 teams have a non-empty squad in `wc_players`; nation filter on the draft board returns players for every nation.
- [ ] `lg_real` exists: 7 members, status `pre_draft`/`drafting`, **no results** (empty scores/standings).
- [ ] New draft-stress Simulation passes end-to-end.
- [ ] Full test suite still passes.

---

## Phase 4 — Hygiene

- [ ] `git rm -r --cached scratch/` + add `scratch/` to `.gitignore`. (Files: `brace_counter.py`, `bracket_stack.py`, `check_syntax.js`, `compile_draft_data.py`, `export_emulator.py`, `map_drafted_players.py`, `mapped_draft.json`, `squad_ids.json`, `test_babel*.js`, `test_points_calculation.py`, `test_seed.py`, `verify_*.py`.)
- [ ] Remove duplicate `squad_ids.json` (rely on `wc_seeded_data.json`).
- [ ] Confirm `__pycache__/*.pyc` untracked: `git ls-files | grep pyc` → empty.
- [ ] Seeding logic lives in `fpl_predictor/seed/` (from Phase 2.2), not inline in `api_wc.py`.

### ✅ Phase 4 Acceptance
- [ ] `git ls-files | grep -E 'scratch/|\.pyc$'` → nothing.
- [ ] `api_wc.py` no longer contains a multi-hundred-line seed function.
- [ ] Full test suite still passes.

---

## Suggested order & final end-to-end acceptance

**Order:** 1 (Truth) → 2 (One scorer) → 3 (Schema) → A (time-machine, needs 2+3) → B (real draft, needs 3.3 ids) → 4 (Hygiene). Phases 1 and B.1 (player-pool pull) are independent and can run in parallel if needed.

**Reviewer runs this last:**
1. Fresh emulator; run the consolidated seed as an **authenticated admin** (no `?secret=`).
2. Start API; open frontend as the seeded admin — spot-check 8 on-screen numbers against Firestore.
3. Stop API → banner shows "down"; restart → shows "simulated"/"live" appropriately.
4. `lg_sim`: step through all 8 GWs forward/back — state matches per-GW snapshots.
5. `lg_real`: full 48-nation pool filterable; draft-stress Simulation passes; no results pre-kickoff.
6. Run Sims 1–5 (+ new ones) → all pass; every phase's `grep` Acceptance checks return clean.

When all six pass, the platform is genuinely data-true end-to-end across both platforms and ready for deploy hardening.
