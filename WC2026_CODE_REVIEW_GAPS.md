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

### GAP-301 — Real per-team fixtures endpoint (Pick Team "next fixture") ✅
- **Where:** `draft_wc_design/components.jsx` (`getNextFixtureOpponent`); previously static source
  `WC_FIXTURES_GW4` in `draft_wc_design/data.jsx`.
- **Was:** "v OPP" on the Pick Team pitch was derived from a hardcoded single-round static set.
  Players on teams outside that set rendered "—". `window.SCHEDULE` is H2H **manager** matchups,
  not team fixtures, so it couldn't be used.
- **Fix (this PR):**
  - Backend: `GET /api/v1/wc/fixtures[?gw=N]` now resolves each fixture's `homeTeam`/`awayTeam`
    `isoCode` from the team map (`_enrich_fixtures_with_iso` / `_team_display_iso` in
    `fpl_predictor/api_wc.py`) — stored fixtures only carry team ids with empty isoCode.
  - Frontend: `app.jsx` builds `window.WC_FIXTURES_BY_TEAM` from `GET /fixtures?gw={viewingGw}`,
    keyed by the same iso players use; `getNextFixtureOpponent` reads it (static round is now a
    fallback only when the fetch fails).
- **Validates:** VT-104 (now full fix). Backend regression: `test_wc_fixtures.py` (6 tests).

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

## Session-7 live-testing findings (mock-league walkthrough, GW3) — mostly FIXED + deployed (v=30)

Bugs reported while signed into `lg_mock_draft` as a real manager. Each was root-caused in
code (file:line) below. **None were fully fixed by EP1–EP6 + GAP-301** — they were either new,
or the parts those epics didn't reach. **Session-8 update:** GAP-501/502/503/505 are now FIXED
and deployed (PRs #36/#39/#38/#37, hosting v=30 + functions:api). GAP-504 is code-done but its
live data re-seed is pending; GAP-506 still needs a runtime repro. Severity as before.

### GAP-501 — Status panel + squad card read bare `ME` ("u_me"), not `window.ME` 🔴 ✅ FIXED (PR #36, deployed v=30)
- **Symptom:** Status tab GW3 Points / Total Points / League Rank all render "—", and the data
  flickers in then blanks across 2–3 re-renders.
- **Root cause:** `data.jsx:228` declares `let ME = "u_me"`; login sets `window.ME = uid`
  (`app.jsx:244`) but the bare `ME` binding that `screens-status.jsx` / `shell.jsx` close over
  stays `"u_me"`. Live `STANDINGS` / `GW3_TOTALS` are keyed by the real uid, so lookups by
  `"u_me"` miss → fall to the `{rank:"—",fpts:"—",hpts:"—"}` default. Each loader's
  `forceUpdate()` (app.jsx:276,326,359) re-runs the failing lookup → the flicker-to-blank.
  Offending reads: `screens-status.jsx:168,178-183,205,325`; `shell.jsx:195,197,206`;
  also ownership fallback `screens-data.jsx:22`. (`PointsScreen` already uses `window.ME` — copy it.)
- **Fix:** replace every bare `ME` read in those files with `window.ME`. Then grep the whole
  `draft_wc_design/` for other bare-lexical consumers (same class as the EP5 lineup bug).
- **Validates:** new VT-110.

### GAP-507 — Player stats empty + reset orphans playerScores 🔴 ✅ FIXED (PR #42, deployed)
- **Symptom:** after the prod tournament sim, every player's stats modal showed
  "No match data yet" even though 6,000+ real `playerScores` rows existed.
- **Root cause (real one behind GAP-502):** `/players/{id}/scores` runs a
  collection-group query on `playerScores` filtered by `playerId`. That needs a
  **single-field `COLLECTION_GROUP` index on `playerScores.playerId`** — which was
  **never deployed to the `gamedb` database**. The declared `(playerId, gw)`
  composite does NOT satisfy an equality-only query with no ordering. The GAP-502
  try/except then masked the `FAILED_PRECONDITION` as an empty `[]` result.
- **Fix:** added the single-field index via `fieldOverrides` in
  `firestore.indexes.json`; deployed with `firebase deploy --only firestore:gamedb`
  (NB: `--only firestore:indexes` crashes with the multi-DB array config in
  firebase-tools 15.x — use the database name as the target).
- **Second bug found + fixed:** `reset_simulation` deleted fixture docs but not
  their `playerScores` subcollections (Firestore does not cascade), so each re-sim
  left orphaned rows that the now-working query returned as duplicate/stale history
  (a real `gw2=5` plus an orphaned `gw2=0`). Now deletes the subcollection first;
  one-time prod cleanup removed 694 orphans. Regression test added.
- **Validates:** VT-106 (now genuinely testable end-to-end on prod).

### GAP-502 — Player modal: fabricated ICT/“owned in” + history shows an ERROR not empty-state 🟡 ✅ FIXED (PR #39, deployed v=30)
- **Fix shipped:** ICT panel replaced with the REAL fantasy-points rank (by position + overall);
  the "Owned in" card now shows honest Owned/Free-agent status for the current league; the
  `/players/{id}/scores` collection-group query is wrapped in try/except so a missing index /
  not-yet-existing group returns `[]` (benign "No match data yet") instead of a 500. The
  `(playerId, gw)` composite index already exists (playerId is the leading field).
- **Symptom:** modal shows ICT ranks (Influence 127, Creativity 130, Threat 128, ICT 129 /442;
  Overall 387/1386) and "OWNED IN 1/10" while TOTAL is 0 pts and History says
  "Couldn't load this player's match history."
- **Root cause:** EP5 fixed the History tab (real `/scores`) but left the header stats mock —
  `player-stats-modal.jsx:356-360` (`posRankFor`) derives Influence/Creativity/Threat/ICT as
  arithmetic offsets of the points rank (`rank-2`, `rank+1`, `rank-1`), not real ICT; "OWNED IN"
  is the literal `"1/10"` at `:144`. The History message at `:220` renders only when
  `error===true`, set only in the `.catch` (`:61-65`) — i.e. the `/players/{id}/scores` fetch
  actually 500'd, not an empty result. The endpoint (`api_wc.py:280`) runs an unauth
  collection-group query with no try/except; a missing `playerScores` composite index returns 500.
- **Fix:** (a) hide the ICT block (or source real influence/creativity/threat from `/scores`)
  when no scored data; (b) compute "OWNED IN" from real league/squad counts; (c) wrap the
  endpoint in try/except + ensure the collection-group index exists so empty → `[]` (benign
  message) instead of 500.
- **Validates:** extends VT-106 (mark VT-106 partial until done).

### GAP-503 — League standings never ranked / sorted / qualification-flagged 🔴 ✅ FIXED (PR #38, deployed v=30)
- **Fix shipped:** `_update_standings` now sorts by `hpts`→`fpts`, assigns a 1-based `rank`, and
  flags the top `knockoutQualifiers` as `qualified` (rest `knockedOut`); persists the cut count
  on the standings doc. Covered by `test_standings.py` (sort/rank/cut-line/row-count/per-GW snapshot).
- **Symptom:** every row shows rank "#1"; every row shows "QUALIFIED" (even below the top-8 line);
  0-0-0 / 0-pt teams are interleaved with played teams.
- **Root cause:** backend `_update_standings` (`wc_scoring.py:839-910`) writes `managers` with
  records + points but **never computes `rank`, never sorts, never sets `knockedOut`/qualified.**
  Frontend defaults mask it: `rank: m.rank || 1` (`app.jsx:265,291`) → all 1; the
  `.sort((a,b)=>a.rank-b.rank)` (`app.jsx:275`) is a no-op; `knockedOut: m.knockedOut || false`
  (`app.jsx:273`) → `qualified = !knockedOut` always true (`screens-data.jsx:335`).
- **Fix:** in `_update_standings`, sort by `hpts`→`fpts` (tiebreak), assign `rank`, and set
  `qualified`/`knockedOut` by rank vs `knockoutQualifiers` (top-8) and elimination state.
- **Validates:** new VT-111.

### GAP-504 — Mock-league members malformed: duplicate `teamName`, extra rows 🟡 (data) ✅ DONE (data fixed)
- **Code side (PR #38):** `_update_standings` keys rows by member id, so the table now emits
  exactly one row per member (no duplicate/stale rows from the scoring path).
- **Data side (done):** after the clean re-seed + tournament sim, all 8 members have distinct
  team names. The one leftover — `u_netanel` inherited the prior owner's `"FPLFRAN's Squad"` —
  was updated to `"Netanel's Squad"` (members doc + `standings/current` snapshot). The
  `"Opponent XI"` row is the canonical seed name for `u_mk_opp`, not a bug.
- **Symptom:** three managers (Netanel, Roy, Yuval) all show team name "FPLFRAN's Squad";
  repeated "Opponent XI"; more rows than the league's real member count.
- **Root cause:** render is faithful (`screens-data.jsx:351` shows `m.teamName`); the
  `leagues/lg_mock_draft/members` docs in Firestore were seeded by an off-spec/older path with a
  default `teamName` and stale duplicates. The canonical seed (`seed_league.py:281-290`) has 8
  distinct members — live data has drifted from it. Related to the earlier dedup work (task #10).
- **Fix:** re-seed / clean the mock league's `members` collection with distinct `teamName`s and
  no duplicate uids. (Data migration, not code.)
- **Validates:** new VT-111 (same panel).

### GAP-505 — Fixtures SCREEN renders static `WC_FIXTURES_GW4` for every GW 🔴 ✅ FIXED (PR #37, deployed v=30)
- **Fix shipped:** `FixturesScreen` now has a `useEffect` keyed on `gw` that fetches
  `GET /fixtures?gw={gw}`, normalizes the backend shape (`homeTeam/awayTeam/kickoff/status/score`)
  into the renderer's row model, and falls back to the static array only while loading / on fetch
  error. Team names + group labels resolve via `teamById`/`TEAM_MAP`; empty GWs show a benign
  "No fixtures scheduled" message.
- **Symptom:** the dedicated Fixtures tab shows the same 8 matches (ESP v JPN, ARG v ECU, …) for
  every GW; GW nav only changes the header; group labels wrong ("GRP ?", Argentina "GRP H").
- **Root cause:** `FixturesScreen` (`screens-data.jsx:211`) reads the bare lexical
  `const WC_FIXTURES_GW4` (`data.jsx:313`) at `:213` and never fetches; `gw` state only drives
  the header/nav. Wrong groups: `:248` renders `Grp ${teamById(m.home).grp}` and the static
  array uses playoff-slot codes (`POR2`,`MEX2`) absent from `TEAM_MAP` → `grp:"?"`.
- **Scope note:** GAP-301 / PR #34 fixed ONLY the Pick Team pitch `getNextFixtureOpponent`
  (`components.jsx`), NOT this screen. This is the screen-level sibling.
- **Fix:** add a `useEffect` keyed on `gw` that calls `GET /fixtures?gw={gw}` (endpoint already
  exists, returns iso-resolved teams) and renders the result, mapping iso→flag/name/group via
  `window.TEAM_MAP`; keep the static array only as a pre-load fallback.
- **Validates:** new VT-109.

### GAP-506 — Wishlist shows (0) / squad changes hard to confirm in UI 🟡 ⬜ (needs runtime repro)
- **Symptom:** "I made a couple of trades — did it change? I don't see anything. I replaced
  Robinson with Munoz, it worked?" Wishlist tab shows "(0)".
- **Findings so far:** executed swaps/trades DO persist — the submit handlers force a full
  `window.location.reload()` (`screens-data.jsx:532,796`), so the squad reflects after reload
  (the lag the user noticed on the Trades tab is this reload, and it lands on correct data —
  acceptable). The Wishlist "(0)" is consistent with the window being CLOSED ("Rebuild window is
  closed · 0h remaining") — wishlist bids only resolve during the free-agents window, so nothing
  shows. Bare-`ME` (GAP-501) also weakens the "is this mine?" ownership fallback.
- **Confirmed (this session):** the "(0)" is correct — on `lg_mock_draft` there were zero
  wishlist docs and all transfer windows were `closed`, so nothing could show. A free-agents
  window has now been forced open (`windowOverride={phase:"free_agents", gw:9}`) so the wishlist
  panel + auction flow can be exercised. The remaining EP7 work is to also surface saved bids
  while a window is CLOSED (read-only) and add the "run auction" button in the Trades panel.
- **Open question:** is the empty wishlist correct (window closed) or a persistence/visibility bug?
  This overlaps EP7/GAP-700 and needs a focused two-state repro (window open vs closed).
- **Fix (pending repro):** confirm wishlist persistence across reload while a free-agents window
  is open; surface saved bids even when the window is closed (read-only) so the user sees them;
  fold into EP7.

### Working as intended (no ticket)
- **Trades tab "lag then correct":** the brief delay is the post-submit `window.location.reload()`
  followed by a fresh fetch; it lands on correct data. Acceptable; could be smoothed later by
  optimistic update instead of full reload, but not a bug.

---

## Cross-reference
- Validation tickets → `WC2026_VALIDATION_TICKETS.md`.
- VT-104 ↔ GAP-301 (Pick Team pitch only); VT-109 ↔ GAP-505 (Fixtures screen);
  VT-110 ↔ GAP-501 (Status/squad-card); VT-111 ↔ GAP-503/504 (standings); EP7 ↔ GAP-700/506.
- Recurring **bare-lexical vs `window.*`** class: EP5 lineup (fixed), GAP-501 (`ME`, swept all 49
  reads in PR #36), GAP-505 (`WC_FIXTURES_GW4`, PR #37). The bare-`ME` sweep is done; keep this
  class in mind for any new `data.jsx` lexical that an async loader later overwrites on `window`.
