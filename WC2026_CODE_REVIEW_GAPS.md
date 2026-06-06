# WC 2026 — Code-Review Gaps & Open Tickets

Findings from the post-implementation code review of PRs #27–#32 (epics EP1–EP6) plus the
follow-up fixes. Each gap is a **ticket**: pick it up with Claude Code, implement, validate
against the linked VT, and close it.

Severity legend: 🔴 correctness/data bug · 🟡 latent/risky (works today, fragile) · 🟢 cleanup/coverage.
Status legend: ⬜ open · 🔵 in progress · ✅ done · ⏸️ deferred.

> Two 🔴/🟡 issues found during review were **already fixed** in `b4a0250`
> (seed `homeTeam.id`, modal stale-demo owner) — see "Already fixed" at the bottom.

---

## Feature follow-ups

### GAP-301 — Real per-team fixtures endpoint (Pick Team "next fixture") ⬜ 🟡
- **Where:** `draft_wc_design/components.jsx:186-189` (`getNextFixtureOpponent`); static source
  `WC_FIXTURES_GW4` in `draft_wc_design/data.jsx`.
- **Problem:** "v OPP" on the Pick Team pitch is derived from a hardcoded static fixtures set.
  Players on teams outside that set render "—". `window.SCHEDULE` is H2H **manager** matchups,
  not team fixtures, so it can't be used here.
- **Fix:** add a backend per-team fixtures endpoint (e.g. `GET /api/v1/wc/fixtures?team={id}&gw={gw}`
  or a preloaded `window.WC_FIXTURES_BY_TEAM` map), and wire `getNextFixtureOpponent` to it.
- **Validates:** VT-104 (currently KNOWN PARTIAL → should become full pass).
- **Note:** this is the explicit "real per-team fixtures" follow-up. In progress next.

### GAP-700 — EP7: wishlist / watchlist isolation per manager ⏸️ 🟡 (DEFERRED per user)
- **Where:** wishlist add/remove flow (screenshot bug #5).
- **Problem:** suspected cross-manager leakage / shared wishlist state; needs confirming whether
  a wishlist is correctly scoped to the signed-in manager.
- **Blocked on:** two-account runtime repro (need two seeded managers signed in concurrently to
  confirm isolation). EP7 was explicitly deferred by the product owner.
- **Validates:** new VT to be authored once repro is set up.

---

## Scoring / aggregation correctness & hygiene

### GAP-101 — `bonusByRatingRank` rule key is dead ⬜ 🟡
- **Where:** `fpl_predictor/api_wc.py` `DEFAULT_RULES["scoring"]["bonusByRatingRank"]=[3,2,1]`;
  consumer `compute_rating_bonus` in `fpl_predictor/game/wc_scoring.py` hardcodes
  `award_map = {0:3,1:2,2:1}`.
- **Problem:** the configurable rule is never read — changing it in rules has no effect. Misleading.
- **Fix:** either (a) read `award_map` from the rule, or (b) delete the rule key and document the
  3/2/1 award as fixed. Pick one; don't leave both.

### GAP-102 — No re-score / decrement path on fixture re-processing ⬜ 🟡
- **Where:** `process_fixture` idempotency early-return + `Increment(total_pts)` accrual.
- **Problem:** correct for first-time processing and safe against double-count (early-return), but
  there is **no path to correct a fixture** if stats are restated after processing — totals can't
  be decremented/replaced. Acceptable for go-live (stats are final), but a real hazard if upstream
  data is ever corrected.
- **Fix:** add a re-process path that diffs old vs new playerScores and adjusts `totalPoints`
  (or recompute totals from playerScores rather than Increment).

### GAP-103 — `_propagate_to_leagues` uses `currentGw`, not the fixture's gw ⬜ 🟡
- **Where:** `_propagate_to_leagues` in `fpl_predictor/game/wc_scoring.py`.
- **Problem:** league accrual is attributed to `league.currentGw` rather than the processed
  fixture's gw. If a fixture is processed while `currentGw` has advanced, points land in the wrong
  gw bucket. Documented as a deliberate set-vs-increment decision at implementation time, but
  flagged for revisit.
- **Fix:** attribute to the fixture's gw, or assert fixtures are only processed for `currentGw`.

### GAP-104 — Dead branch in `wc_scoring.py` ⬜ 🟢
- **Where:** `fpl_predictor/game/wc_scoring.py:501-505` (approx — re-confirm line numbers).
- **Problem:** unreachable/dead branch left from the bps→rating refactor.
- **Fix:** remove dead code.

---

## Rendering hygiene

### GAP-201 — `Pitch` falls back to demo `GW3_POINTS` when snapshot missing a player ⬜ 🟢
- **Where:** `draft_wc_design/components.jsx:221` (approx).
- **Problem:** if a per-GW snapshot is missing a player, the pitch falls back to demo `GW3_POINTS`
  instead of showing 0 / "no data". Could surface stale demo numbers in an edge case.
- **Fix:** fall back to 0 or an explicit "no data" marker, never to demo constants.

### GAP-202 — `wc_api` events-fallback path yields no tackles/rating ⬜ 🟢
- **Where:** events-fallback in the WC api stats path.
- **Problem:** when only the events feed is available (no full player stats), the synthesized stats
  carry no `tackles`/`games.rating`, so DefCon and rating-bonus silently can't fire. Fine if the
  fallback never runs in prod, but it's a silent degradation.
- **Fix:** document that the fallback disables DefCon/bonus, or backfill those fields where possible.

---

## Test coverage gaps ⬜ 🟢

### GAP-401 — Missing/weak coverage to add
- `finalize_gw` full flow (snapshot + propagation) end-to-end.
- `apply_auto_subs` (autosub logic on the points total).
- `_propagate_to_leagues` for an **active** league (not just the no-op path).
- Rating-bonus tie overflow (4+ players tied at rank 1 — ensure award list doesn't over-award).
- DefCon when `minutes < 60` (confirm intended behavior at the minutes boundary).

---

## Already fixed (in `b4a0250`, this branch) ✅

### GAP-001 — Mock seed wrote fixtures without `homeTeam.id` 🔴 → ✅
- **Was:** `seed_league.py` wrote `homeTeam:{isoCode,name}` with **no `id`**, while
  `build_team_raw_stats` uses team ids 1/2. So `is_home = (None == 1) == False` for both sides →
  home-side goals-conceded/clean-sheet computed against the wrong team.
- **Fix:** seed now writes `homeTeam:{id:1,...}`, `awayTeam:{id:2,...}`.
- **Regression:** `test_e2e_reconcile.py::test_home_away_goals_conceded_from_score` (non-vacuous —
  fails if the bug is reintroduced). Validates VT-006.

### GAP-002 — Player-stats modal hardcoded owner "Hapoel Eliyahu (you)" 🟡 → ✅
- **Was:** `const owner = MY_SQUAD_IDS.includes(p.id) ? "Hapoel Eliyahu (you)" : null;` (bare
  lexical + hardcoded team name).
- **Fix:** resolves the real owner from `window.SQUADS_BY_UID` + `window.MANAGERS`, appends
  "(you)" only when it's the signed-in manager. Validates VT-108.

---

## Cross-reference
- Validation tickets → `WC2026_VALIDATION_TICKETS.md`.
- VT-104 ↔ GAP-301 (per-team fixtures); EP7 ↔ GAP-700.
