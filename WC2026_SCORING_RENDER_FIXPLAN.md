# WC 2026 — Scoring & Rendering Fix Plan (end-to-end implementation handoff)

**Author:** investigation agent (research/planning only — no code changed yet)
**Date:** 2026-06-06
**Scope:** Everything found across the multi-phase audit of the scoring pipeline, the
score/stat rendering, the mock/seed data, and the six screenshot bugs — consolidated
into epics → work items → targets → validations.

> **Read first:** §0 (how to run this with Claude as manager), §1 (mission), §2 (architecture map),
> then pick an epic from §4. Every work item has a `tags:` line, a concrete change, a **TARGET**,
> and a **VALIDATION** test that must go green before the item is "done."

---

## 0. How to execute this (Claude = guide & manager)

This plan is designed to be driven by an implementing agent **with Claude as the managing guide**.
Protocol:

1. **Pick one work item** (not a whole epic) at a time. Smallest shippable unit.
2. **Tell Claude the item ID** (e.g. `EP2-W3`). Claude restates the target, the files, and the
   validation gate before you write code.
3. **Implement → run the item's VALIDATION test → paste the result back to Claude.** Claude confirms
   green or diagnoses red. Do not move on while red.
4. **One PR per epic** (or per work item if large). PR-only workflow — never push to `main`.
   Squash-merge. Verify merge with `gh pr view <n> --json state,mergedAt`.
5. **Dependency order matters** — see §3. Backend scoring/persistence (EP1–EP3) must land before the
   frontend reconciliation work (EP5) can be validated against real data.
6. Use `/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python` (the venv is in the **main** repo, not
   the worktree). Run backend tests from the worktree with `PYTHONPATH=.`.
7. Firestore emulator / prod use `database_id=gamedb`. Never write the `(default)` store.

**Definition of done for the whole plan:** a finalized GW produces, for every manager, a squad total
that equals the sum of its players' per-GW points, every per-player point equals
`compute_player_points(stats)` for that player's real stats, and all six screenshot bugs are closed
with passing validations.

---

## 1. Mission & the one invariant

Build a World-Cup fantasy scoring pipeline whose **numbers reconcile**. The north-star invariant,
stated by the user:

> "A score of a player in a game week should be validated with the sum of all his points, and saved
> for the manager to sum up his squad."

Concretely, for every player `p`, gameweek `gw`, manager `m`:

```
player_gw_points(p, gw)        == compute_player_points(real_stats(p, gw), p.position, rules)
manager_gw_total(m, gw)        == Σ player_gw_points(p, gw) for p in starting_after_autosub(m, gw)
                                  + captain bonus
season_total(p)                == Σ player_gw_points(p, gw) over all finalized gw
```

Today **none** of these three hold end-to-end: the engine is missing two scoring rules, season totals
are never aggregated, and the frontend invents per-player stats client-side.

---

## 2. Architecture map (where everything lives)

**Backend (Flask + Firestore, project `fpl-analyzer-792eb`, db `gamedb`, prefix `/api/v1/wc`):**

| File | Role |
|------|------|
| `fpl_predictor/game/wc_scoring.py` | `compute_player_points` (engine), `process_fixture` (per-fixture write), `finalize_gw` (GW close), `_propagate_to_leagues`, `_snapshot_gw_history`, dead `compute_bps_bonus` |
| `fpl_predictor/api_wc.py` | All HTTP endpoints + `DEFAULT_RULES["scoring"]` (132-146) + `_require_auth` |
| `fpl_predictor/seed/seed_league.py` | Seeds tournament + runs the real engine per GW; `get_team_raw_stats` builds synthetic match stats |
| `fpl_predictor/data/wc_seeded_data.json` | 1383 players, **0 have `totalPoints`** |

**Frontend (vanilla React via in-browser Babel, no build; synced `draft_wc_design/` → `dist/`):**

| File | Role |
|------|------|
| `draft_wc_design/data.jsx` | Static demo data incl. hardcoded `WC_FIXTURES_GW4` (313) |
| `draft_wc_design/app.jsx` | Loaders: `window.PLAYERS`, `GW3_POINTS`, `GW3_TOTALS`, trades, scores |
| `draft_wc_design/screens-data.jsx` | Players/Transfers/Trades screens + ownership map (14-18) + ProposeTradeModal (786) |
| `draft_wc_design/screens-status.jsx` | PointsScreen (hardcoded `MY_LINEUP_GW3`/`GW3_POINTS`) |
| `draft_wc_design/screens-draft.jsx` | Draft room + per-user watchlist |
| `draft_wc_design/components.jsx` | `PlayerSlot` (pitch), `getNextFixtureOpponent` (186) |
| `draft_wc_design/player-stats-modal.jsx` | `synthHistory`/`synthFixtures`/`synthICT` — fully synthetic |

**Firestore collections touched:** `wc_players/{id}`, `wc_fixtures/{fid}/playerScores/{pid}`,
`leagues/{lid}/squads/{uid}`, `leagues/{lid}/scores/{gw}`, `leagues/{lid}/gw_history/{uid}_{gw}`,
`leagues/{lid}/standings/{current|gw}`, `leagues/{lid}/draft/watchlists/{uid}/list`,
`leagues/{lid}/trades/*`.

---

## 3. Epic dependency / sequencing

```
EP1 (engine rules) ──┐
                     ├──> EP2 (aggregate + persist) ──┬──> EP5 (frontend reconcile #4)
EP3 (seed fidelity) ─┘                                │
                                                      └──> EP6 (validation harness, cross-cutting)
EP4 (frontend render #1/#2/#3/#6)  — independent, can run in parallel
EP7 (wishlist #5)  — blocked on runtime repro
```

Recommended order: **EP1 → EP3 → EP2 → EP6 (scoring tests) → EP5**, with **EP4** in parallel by a
second agent, **EP7** last.

---

## 4. Epics & work items

Tag legend: `[tab:…]` UI tab · `[collection:…]` Firestore · `[window/gw]` time logic ·
`[points]` scoring math · `[seed]` mock data · `[render]` frontend display.

---

### EPIC 1 — Scoring engine completeness `[points]`

**Why:** The engine is missing two locked-in rules and still keys bonus off a dead field. Until the
engine is complete, every downstream total is wrong.

**Locked decisions (from this session's AskUserQuestion):**
- **DefCon:** `defCon = tackles.total + tackles.interceptions + tackles.blocks`. Award **+2** when
  DEF reaches **≥10**, MID reaches **≥12**. No GK, no FWD.
- **Bonus:** ONE award per fixture — top-3 by api-sports `games.rating` → **3 / 2 / 1** (ties share the
  rank, mirror existing tie logic). Replaces `bps`/`compute_bps_bonus` entirely.

**EP1-W1 — Add DefCon to the engine** `[points]`
- File: `fpl_predictor/game/wc_scoring.py` `compute_player_points`.
- Add rule constants to `DEFAULT_RULES["scoring"]` in `api_wc.py:132-146`: `defConPoints:2`,
  `defConThresholdDef:10`, `defConThresholdMid:12`.
- Compute `defCon` from `stats.tackles{total,interceptions,blocks}`; add points by position+threshold.
- **TARGET:** DEF with 10 combined actions = +2; MID with 11 = +0, 12 = +2; GK/FWD always +0.
- **VALIDATION:** `test_wc_scoring.py::test_defcon_thresholds` — table of (pos, actions, expected).

**EP1-W2 — Replace bps bonus with rating-rank bonus** `[points]`
- File: `wc_scoring.py` — delete/retire `compute_bps_bonus` (136-) and the `bps` plumbing in
  `process_fixture` (306, 322, 330-331, 341); add `compute_rating_bonus(rating_list)` → {pid: 3|2|1}.
- Add `bonusByRatingRank:[3,2,1]` to `DEFAULT_RULES["scoring"]`.
- **TARGET:** within a fixture, the three highest `games.rating` get 3/2/1; ties share rank.
- **VALIDATION:** `test_wc_scoring.py::test_rating_bonus_top3` incl. a tie case.

**EP1-W3 — Engine regression lock** `[points]`
- Re-run the 9 previously-validated scenarios (goals by position, assists, CS, GC, cards, pens, saves,
  appearance, minutes==0 ⇒ (0,0)) and assert unchanged after W1/W2.
- **VALIDATION:** `test_wc_scoring.py::test_engine_regression_matrix`.

---

### EPIC 2 — Score aggregation & persistence `[points][collection:wc_players][collection:gw_history]`

**Why:** `process_fixture` writes per-fixture `playerScores` but **never** updates
`wc_players.totalPoints`, and `_propagate_to_leagues` only increments a scalar. The frontend reads
`totalPoints` (always 0) and has no per-player-per-GW source it actually calls.

**EP2-W1 — Aggregate season `totalPoints` onto `wc_players`** `[collection:wc_players]`
- File: `wc_scoring.py` `process_fixture`/`finalize_gw`. After computing per-player base+bonus, write
  `wc_players/{pid}.totalPoints` via `Increment(delta)` (idempotent per fixture via the existing
  `processedForFantasy` guard).
- **TARGET:** after GW1-3 seed, `Σ wc_players.totalPoints` equals `Σ` of all `playerScores.fantasyPoints+bonusPoints`.
- **VALIDATION:** `test_aggregate.py::test_totalpoints_matches_playerscores`.

**EP2-W2 — Persist a per-player breakdown the frontend can fetch** `[collection:gw_history]`
- Confirm/extend `_snapshot_gw_history` (652-) so `gw_history/{uid}_{gw}.players` carries, per player,
  `{id, points, stats}` (stats needed for the modal reconciliation in EP5).
- Ensure `/players/<id>/scores` (collection_group `playerScores`) returns per-GW rows for the modal.
- **TARGET:** for any (uid, gw), `Σ players[].points == results.{uid}.points` (post-autosub + captain).
- **VALIDATION:** `test_aggregate.py::test_gw_history_sums_to_results`.

**EP2-W3 — Propagation integrity** `[points][window/gw]`
- Audit `_propagate_to_leagues` `if delta:` guard (429) — net-zero deltas must not silently drop a
  legitimate 0 that should overwrite a stale value. Decide set-vs-increment and document.
- **TARGET:** re-finalizing a GW is idempotent (no double counting, no stale leftovers).
- **VALIDATION:** `test_aggregate.py::test_finalize_idempotent` (finalize twice, totals identical).

---

### EPIC 3 — Mock / seed data fidelity `[seed]`

**Why:** `get_team_raw_stats` (`seed_league.py:449-477`) **injects** `bps = total_base*3` (473),
hardcodes `minutes:90`, and emits **no tackles and no rating** — so mock bonus is fake and DefCon can
never trigger. Prod (real api-sports) won't reproduce the mock numbers. Mock data must be *calculated*,
not *injected*.

**EP3-W1 — Emit real stat shape in synthetic fixtures** `[seed]`
- File: `seed_league.py` `get_team_raw_stats`. Remove the `bps` injection; add
  `tackles{total,interceptions,blocks}` and `games.rating` so DefCon (EP1-W1) and the rating bonus
  (EP1-W2) compute from data instead of being short-circuited. Vary `minutes` (not always 90) so the
  60' appearance threshold is exercised.
- **TARGET:** seeded fixtures contain only fields api-sports actually returns; no `bps`.
- **VALIDATION:** `test_seed_stats.py::test_no_injected_bps_has_tackles_rating`.

**EP3-W2 — Seed a reconciling dataset for GW1-3** `[seed][points]`
- Re-run `seed_everything` against the emulator; assert the EP2 invariants hold on seeded data
  (this is the dataset the frontend validations in EP5 will run against).
- **TARGET:** at least one DEF crosses DefCon≥10 and one MID crosses ≥12 in the seed, so the new rule is
  observable in the UI.
- **VALIDATION:** `test_seed_stats.py::test_seed_exercises_defcon_and_bonus`.

---

### EPIC 4 — Frontend rendering correctness `[render]` (bugs #1, #2, #3, #6)

**Why:** Independent of the scoring backend; pure display/ownership/refetch defects from the
screenshots.

**EP4-W1 — Ownership map across all managers** `[tab:players][tab:transfers][render]` (bugs #1 & #2)
- File: `screens-data.jsx:14-18`. Today `owners` is built only from `ME`'s squad, so every other
  manager's players (e.g. Haaland) render as "Free agent / Claim" (166).
- Fix: build `owners` from **all** `MANAGERS`' squads.
- **TARGET:** every drafted player shows its real owner on both Players and Transfers tabs; only truly
  unowned players show "Claim."
- **VALIDATION:** `test_ownership_all_managers` (JS/dom or logic test): 2+ seeded squads ⇒ no owned
  player renders as free.

**EP4-W2 — Pitch next-fixture from real schedule** `[tab:pickteam][window/gw][render]` (bug #3a)
- Files: `data.jsx:313` (static `WC_FIXTURES_GW4`, only 16 team ISOs) + `components.jsx:186-189`
  (`getNextFixtureOpponent` returns "—" for any team not in the static list).
- Fix: populate next-GW fixtures from the backend schedule keyed by team ISO; remove the hardcoded array.
- **TARGET:** every player in a full 15-man squad resolves an opponent (no "—" for active teams).
- **VALIDATION:** `test_pitch_fixture` — mixed-team squad ⇒ 0 unresolved fixtures.

**EP4-W3 — Show position on starters, not just bench** `[tab:pickteam][render]` (bug #3b)
- File: `components.jsx:224-227`. `POS_NAMES[p.pos]` is rendered only inside `{onBench && …}`.
- Fix: render the position label for starters too (keep bench role styling distinct).
- **TARGET:** every pitch slot (starter + bench) shows GK/DEF/MID/FWD.
- **VALIDATION:** `test_pitch_position` — all 15 slots have a non-empty position label.

**EP4-W4 — Refetch trades after proposing** `[tab:trades][collection:trades][render]` (bug #6)
- File: `screens-data.jsx` ProposeTradeModal `handleSubmit` (786) — currently only calls `onClose()`.
- Fix: after the POST resolves, refetch `/leagues/{lid}/trades` (or reload like `TradeCard.act:526`) so
  the new trade appears in outbox (proposer) and inbox (target).
- **TARGET:** a freshly-created trade is visible without a manual refresh.
- **VALIDATION:** `test_trade_appears_after_create` — POST then re-list ⇒ present in both boxes.

---

### EPIC 5 — Per-player points reconciliation in the UI `[points][render]` (bug #4)

**Why:** `player-stats-modal.jsx:238-279` `synthHistory` invents per-GW rows: `pts` is derived from a
random offset while MIN/GS/A/CS/GC/YC/S come from *independent* `r()` calls, so points never reconcile
with the stats shown. `synthFixtures`/`synthICT` are synthetic too. `/players/{id}/scores` is never
called. PointsScreen (`screens-status.jsx`) sums `GW3_POINTS` (all zeros) and falls back to a hardcoded
65. **Depends on EP2 landing real data.**

**EP5-W1 — Modal reads real per-GW breakdown** `[render][collection:gw_history]`
- Replace `synthHistory` with a fetch of `/players/{id}/scores` (and/or `gw_history`); render real
  MIN/GS/A/CS/GC/YC/S/Bonus/PTS.
- **TARGET:** the modal's per-GW `PTS` equals `compute_player_points(stats_shown)` for that row.
- **VALIDATION:** `test_modal_reconcile` — for every rendered GW row, recompute from the shown stats and
  assert equality (the self-verifying reconciliation).

**EP5-W2 — PointsScreen uses aggregated totals, not zeros/fallback** `[tab:points][points][window/gw]`
- File: `screens-status.jsx` PointsScreen — drop hardcoded `MY_LINEUP_GW3`/`GW3_POINTS`/`65`; read the
  finalized lineup + `gw_history` for the viewed GW.
- **TARGET:** squad total on Points tab == Σ of the lineup's per-player points for that GW (+captain).
- **VALIDATION:** `test_pointsscreen_total` — rendered total matches backend `results.{uid}.points`.

**EP5-W3 — Remove remaining synthetic generators** `[render]`
- Retire `synthFixtures`/`synthICT` or back them with real data; ensure no screen path silently
  fabricates stats.
- **TARGET:** grep shows no live render path calling a `synth*` generator.
- **VALIDATION:** `test_no_synth_in_render` (grep/AST guard).

---

### EPIC 6 — Validation harness (cross-cutting) `[points][seed]`

**Why:** The invariant in §1 must be enforced by an automated, self-verifying suite so regressions are
caught. This epic owns the shared fixtures and the top-level reconciliation test.

**EP6-W1 — Shared seeded-DB fixture** — in-memory/path-keyed fake Firestore (pattern already used in
`test_dedup_squads.py`) seeded via EP3 data. **VALIDATION:** fixture imports and streams collections.

**EP6-W2 — End-to-end reconciliation test** `[points]`
- After a seeded finalize, assert all three §1 equalities for every (player, gw, manager).
- **TARGET:** one test that fails if any layer (engine, aggregation, snapshot) drifts.
- **VALIDATION:** `test_e2e_reconcile.py::test_full_invariant`.

**EP6-W3 — CI wiring** — ensure `pytest -q` runs EP1/EP2/EP3/EP6 backend suites; document the command in
the PR template. **VALIDATION:** green run from the worktree with `PYTHONPATH=.`.

---

### EPIC 7 — Wishlist isolation `[tab:draftroom][collection:watchlists]` (bug #5) — BLOCKED

**Why blocked:** Static code is already per-uid correct — backend stores at
`draft/watchlists/{uid}/list` (`api_wc.py:635-658`), `_require_auth` resolves uid per token (66-78),
frontend keeps watchlist in per-user `useState` and loads via the authed endpoint
(`screens-draft.jsx:15,33-62`). No shared static fallback exists.

**EP7-W1 — Runtime reproduction** — sign in as two distinct Firebase accounts in two browsers; confirm
whether both resolve to the **same uid** (env/token issue) or genuinely leak.
- **TARGET:** a definitive yes/no on whether a leak exists at runtime.
- **VALIDATION (only if a real leak is found):** `test_watchlist_per_uid` — write as A, read as B ⇒ empty.

---

## 5. Bug-#→work-item traceability

| Screenshot bug | Work item(s) | Category tag |
|----------------|--------------|--------------|
| #1 Players free-agent | EP4-W1 | `[tab:players][render]` |
| #2 Transfers free-agent | EP4-W1 | `[tab:transfers][render]` |
| #3 Pitch fixture+position | EP4-W2, EP4-W3 | `[tab:pickteam][window/gw][render]` |
| #4 Points ≠ stats | EP1-*, EP2-*, EP5-W1, EP5-W2 | `[points][render]` |
| #5 Shared wishlist | EP7-W1 | `[tab:draftroom][collection:watchlists]` |
| #6 Trades not shown | EP4-W4 | `[tab:trades][collection:trades][render]` |

## 6. Open decisions for the user / next agent

1. **EP2-W3:** set vs increment for league propagation — pick one and document (idempotency depends on it).
2. **EP4-W2:** which backend endpoint feeds next-GW fixtures (schedule collection vs derived) — confirm source.
3. **EP7:** needs the user to attempt the two-account runtime repro before any code is written.
