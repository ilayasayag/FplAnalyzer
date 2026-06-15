# Known issues / bug log

Scoring + player-modal bugs surfaced during the 2026-06-15 scoring deploy
(PRs #87–#91). Newest incidents first. See `OPS_RUNBOOK.md` for how we deploy /
access the DB.

---

## RESOLVED — player popup white-screened (`HistoryTab` referenced out-of-scope `p.pos`)

- **Symptom:** opening *any* player card threw `Cannot read properties of
  undefined (reading 'pos')` in `<HistoryTab>`; React unmounted the modal (live
  on prod).
- **Root cause:** the P5 DefCon-by-position change rendered the DEF column as
  `p.pos === 2 ? h.cbit : h.cbit + h.rec`, but `p` is **not in scope** inside
  `HistoryTab` — that component only receives `history`/`error`. A runtime
  ReferenceError that **passed the Babel compile-check** (valid syntax).
- **Fix:** pass the player position in as a `pos` prop (`PlayerStatsModal` →
  `<HistoryTab … pos={p.pos} />`), key off `pos`. PR #91, deployed `jsx?v=50`.
- **Lesson:** for JSX, a compile-check is necessary but **not sufficient** —
  scope/runtime errors crash a component at render and slip past Babel.
  SSR-smoke-test or load the touched component before deploying frontend.
  (`react-dom/server.renderToStaticMarkup(React.createElement(Comp, props))`.)

## OPEN — WhoScored scoring aborts on a null substitution minute

- **Location:** `parse_whoscored_match`, `fpl_predictor/data/wc_live_ingest.py`
  (`sub_off[pid] = e.get("minute")` / `sub_on[pid] = e.get("minute")`, stored
  **without a None guard** — note the goal-minute handler right above it *does*
  guard `if gmin is not None`).
- **Trigger:** a `SubstitutionOff`/`On` event with `minute: null` (WhoScored
  intermittently omits it) → `minutes_for` returns `None` → `min(mins, 90)` and
  the per-player clean-sheet window (`win_start <= gm < win_end`, where
  `win_end = sub_off[pid] = None`) raise `TypeError`.
- **Impact:** that fixture's WhoScored parse throws → the scan's per-fixture
  `try/except` drops it to the **ESPN fallback (no DefCon, no penalties/CS
  reasons)**. Contained (won't kill the whole scan) but an affected match
  *persistently* loses DefCon until the feed supplies the minute.
- **Status:** not fixed; latent (no GW1 match hit it). Suggested fix: default
  `sub_off`/`sub_on` minutes (e.g. to `max_min`/`0`) like the goal handler.

## OPEN (cosmetic) — DEF column over-reports recoveries for GK/FWD

- **Location:** `draft_wc_design/player-stats-modal.jsx` History "DEF" cell:
  `pos === 2 ? h.cbit : h.cbit + h.rec`.
- **Issue:** the `else` branch also catches GK (pos 1) and FWD (pos 4), so their
  DEF column shows CBITR (includes ball recoveries) instead of CBIT — contra the
  "recoveries count for MID only" rule. No crash, no DB/scoring effect (GK/FWD
  get no DefCon bonus). Fix: `pos === 3 ? h.cbit + h.rec : h.cbit`.

## OPEN (latent) — `recompute_all_scores` stale per-player `gwPoints` for multi-GW

- **Location:** `recompute_all_scores`, `wc_live_ingest.py` — `gw_points` is keyed
  by `pid` only, so when a recompute touches a player across ≥2 GWs only the
  **last-iterated GW's** `wc_players/{pid}.gwPoints.{gw}` cache is written; the
  others go stale.
- **Impact:** **zero today** — only GW1 exists, and `wc_players.gwPoints` (this
  per-*player* cache) is not read per-GW anywhere (the modal reads
  `playerScores`; the standings `gwPoints` is a separate manager-level map). Will
  silently drift that cache from GW2 onward. Fix: key `gw_points` by `(pid, gw)`.

---

### Verified solid (so future readers don't re-chase these)

- Hard invariant `fantasyPoints == fifaPoints + defConBonus − fifaBonus` holds in
  all three write paths; live audit = **0 mismatches across 302 GW1 scores**.
- DEF never counts recoveries toward the *bonus* (only the display cell above is
  wrong); clean-sheet vs goals-conceded are mutually exclusive; penalty
  won/conceded are distinct + non-double-counted; ESPN minutes are
  None/negative-guarded; season aggregation is idempotent; wishlist-delete is
  auth-safe + idempotent.
