# WC 2026 — Validation Tickets

Validation tickets for the scoring + rendering fixes shipped in PRs #27–#32 (epics EP1–EP6)
plus the code-review follow-up fixes. **Pick up a ticket, run it with Claude Code, check the box,
and note pass/fail in the PR or a comment.**

How to use with Claude Code:
> "Run validation ticket VT-### from `WC2026_VALIDATION_TICKETS.md` and tell me if it passes."

Each ticket says **what** to verify, **how** (exact commands / UI steps), and the **expected** result.
Backend tests use the repo venv (it lives in the MAIN repo, not a worktree):
`PYTHONPATH=. /Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python -m pytest <file> -q`

Status legend: ⬜ not validated · ✅ passed · ❌ failed (file a bug, link it).

---

## Automated (backend) — should be green on every `main`

### VT-001 — Full backend suite green ⬜
- **Verify:** the entire scoring/aggregation/seed/e2e suite passes.
- **How:** `PYTHONPATH=. /Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python -m pytest -q`
- **Expected:** `135 passed` (or higher as tests are added), 0 failures.

### VT-002 — Scoring engine rules (EP1) ⬜
- **Verify:** DefCon (DEF +2 @ ≥10, MID +2 @ ≥12, none for GK/FWD), rating bonus 3/2/1 with ties, 9-scenario regression.
- **How:** `pytest test_wc_scoring.py -q`
- **Expected:** all pass; confirm `test_defcon_thresholds`, `test_rating_bonus_top3`, `test_engine_regression_matrix` present and green.
- **Manual sanity:** in a Python shell, `compute_player_points({"minutes":90,"tackles":{"total":6,"interceptions":4,"blocks":0}}, 2, None)` → base includes +2 DefCon (10 actions, DEF).

### VT-003 — Season totals + idempotency (EP2) ⬜
- **Verify:** `Σ wc_players.totalPoints == Σ playerScores.fantasyPoints`; bonus not double-counted; re-processing a fixture is a no-op.
- **How:** `pytest test_aggregate.py -q`
- **Expected:** all pass incl. `test_totalpoints_matches_playerscores`, `test_totalpoints_no_double_count_of_bonus`, idempotency test.

### VT-004 — Seed data fidelity (EP3) ⬜
- **Verify:** synthetic seed stats carry `tackles{total,interceptions,blocks}` + `games.rating`, varied minutes, NO `bps`; DEF≥10 / MID≥12 anchors fire; 3/2/1 bonus observable.
- **How:** `pytest test_seed_stats.py -q`
- **Expected:** `test_no_injected_bps_has_tackles_rating`, `test_seed_exercises_defcon_and_bonus` pass.

### VT-005 — End-to-end reconciliation invariant (EP6) ⬜
- **Verify:** per-player points = engine output; season totals reconcile; manager snapshot sums back to results; home/away goals-conceded correct.
- **How:** `pytest test_e2e_reconcile.py -q`
- **Expected:** all pass incl. `test_full_invariant` and `test_home_away_goals_conceded_from_score`.
- **Bonus check (non-vacuous):** temporarily break the engine (e.g. double-count bonus) and confirm `test_full_invariant` FAILS, then revert.

### VT-006 — Seeded mock league scores are correct end-to-end ⬜
- **Verify:** after seeding the mock league, home-side GK/DEF clean sheets & goals-conceded are correct (regression for the `homeTeam.id` fix).
- **How:** run the seed against the Firestore emulator (`database_id=gamedb`) or a throwaway project, then inspect `wc_fixtures/{fid}/playerScores/*` for a fixture with a non-draw score: the winning side's GK should have `goalsConceded=0, cleanSheet=true`.
- **Expected:** home and away GKs have DIFFERENT `goalsConceded` matching the scoreline (not both equal to home_goals).

---

## Manual (frontend) — open the app against seeded `lg_mock_draft`

> No JS test runner exists (Babel-in-browser). Validate in the UI. Sign in as a real seeded
> manager. Where two managers are needed, use two browsers / accounts.

### VT-101 — Players tab ownership (#1) ⬜
- **Verify:** drafted players owned by ANY manager (e.g. Haaland) show "Owned by …", not "Free agent / Claim".
- **How:** Players tab → find a player you know another manager drafted.
- **Expected:** shows the owning manager; only genuinely undrafted players show "Claim". Filter "Free agents" excludes owned players.

### VT-102 — Transfers tab ownership (#2) ⬜
- **Verify:** same ownership correctness on the Transfers tab.
- **Expected:** owned players are not offered as free agents.

### VT-103 — Pick Team: position labels (#3b) ⬜
- **Verify:** EVERY pitch slot (starters AND bench) shows a position label (GK/DEF/MID/FWD).
- **Expected:** starters now labelled (previously bench-only); bench role badge still visually distinct.

### VT-104 — Pick Team: next fixture (#3a) — FULL FIX (GAP-301 done) ⬜
- **Verify:** on Pick Team, each player's "v OPP" comes from REAL fixtures for the viewing GW
  (live `window.WC_FIXTURES_BY_TEAM`, built from `GET /fixtures?gw=N`), not the static round.
- **How:** Pick Team tab → confirm opponents match the actual GW fixtures; advance the GW and
  confirm opponents change. Teams not playing that GW (eliminated / bye) show "—" without crashing.
- **Expected:** opponents reflect the live schedule; "—" only for teams with no fixture that GW.
  Falls back to the static `WC_FIXTURES_GW4` round only if the fixtures fetch fails.
- **Backend regression:** `pytest test_wc_fixtures.py -q` (iso resolution from team map).

### VT-105 — Trades appear after proposing (#6) ⬜
- **Verify:** proposing a trade makes it appear without a manual refresh.
- **How:** Trades → propose a trade to another manager → submit.
- **Expected:** the new trade shows in your Sent/outbox (and the target's inbox).

### VT-106 — Player stats modal reconciles (#4) ⬜
- **Verify:** in a player's stats modal, each GW row's PTS equals what its stats imply; nothing is fabricated.
- **How:** open any player → History tab.
- **Expected:** rows come from `/players/{id}/scores` (real); PTS column = backend `fantasyPoints`; B = `bonusPoints`; stats and PTS are from the same row. Empty/finalized-no-data shows a message, not random rows.

### VT-107 — Points tab total reconciles (#4) ⬜
- **Verify:** the Points tab squad total equals the sum of the rostered starters' points (+captain), not a hardcoded number.
- **How:** Points tab for a finalized GW; compare the big total to the per-player points on the pitch/list.
- **Expected:** total == Σ starter points (post-autosub) + captain; GW nav changes the data; the rendered roster is the REAL lineup for that GW (not a demo roster). No "65" fallback.

### VT-108 — Modal owner label ⬜
- **Verify:** the "Owned by" line in the player modal shows the REAL owning manager's team name (and "(you)" when it's yours), for players owned by any manager.
- **Expected:** not the hardcoded "Hapoel Eliyahu"; reflects `window.SQUADS_BY_UID`.

---

## Cross-reference
- Screenshot bugs → tickets: #1→VT-101, #2→VT-102, #3→VT-103/VT-104, #4→VT-106/VT-107, #5→EP7 (GAP-700), #6→VT-105.
- Known gaps from code review → `WC2026_CODE_REVIEW_GAPS.md`.
