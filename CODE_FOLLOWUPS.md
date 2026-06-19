# WC2026 — Code follow-ups (queued from the 2026-06-18 session)

Prioritized. Each is a self-contained change → branch → SSR/test → PR → merge → deploy
(`gh auth switch --user ilayasayag` first; deploy from a clean merged-main worktree).

## P1 — Free-agent / wishlist swap should reconcile the lineup
**Why:** `sign_free_agent` (and any squad-changing swap) updates `squads/{uid}.players`
but NOT `lineups/{uid}_{gw}`, leaving a dropped player dangling and the new one missing
(the Vargas/Leão bug; we fixed Yuval by hand). Recurs for anyone who doesn't re-save.
**Fix:** in the swap path (`fpl_predictor/game/wc_squads.py` `sign_free_agent`, and the
wishlist `_execute_swap`), after updating the squad, update the manager's *unlocked* GW
lineup(s): replace `playerOut → playerIn` in `starting`/`bench` in place (keep slot;
keep `bench[0]`=GK). Skip locked GWs. Add a test.
**Deploy:** functions. **Until shipped:** `/squad-lineup-audit` catches + fixes it.

## P2 — Review/close PR #102
"position-specific stat comparison + compact modal viewport" overlaps the shipped #100
(`PickupCompare`). Diff it against `screens-bracket.jsx@main`; either cherry-pick the
genuinely-new bits or close it. Avoid a third conflicting copy of the swap modal.

## P3 — Auto-fire the wishlist auction when the FA window opens (optional)
**Why:** the auction is manual; at FA-open someone must run it. With no scheduler, a
"lazy" hook could run it on the first read after FA-open.
**Caution:** must reuse the idempotency guard (PR #103) so it can't double-fire, and run
ONLY the real `run_auction` (never the mock fill). Prefer keeping it manual via
`/wishlist-run` + a scheduled reminder unless the league wants true automation.

## P4 — `finalize_gw` should honor the pick blocklist (optional)
**Why:** `pickBlockByGw` blocks STARTING a player at save time, but a manager who saved
a blocked starter BEFORE the block, or a bench auto-sub, could still score them.
**Fix:** at finalize, treat `pickBlockByGw[gw]` players as non-scoring / force-bench in
the effective XI. Low priority (this GW no one started a blocked player).

## P5 — Rename leftover `GW3_*` references / dead `MY_LINEUP_GW3` doc-name
#106 renamed the live globals (`MY_LINEUP`, `GW_POINTS`, `GW_TOTALS`). Grep the whole
repo (incl. backend + `dist/`) for any remaining `GW3_`/`_GW3` identifiers or comments
and clean them so the "GW3" misnomer is fully gone.

## Nice-to-have
- Companion scripts under `scripts/` for the new validation skills (like
  `scripts/gw_end_validate.py`) so they're deterministic + CI-runnable, not just inline.
- A tiny `/me/super-admin`-style surfacing so the frontend can hide Ilay-only controls
  cleanly (already have `isSuperAdmin` from `/me/admin`).
