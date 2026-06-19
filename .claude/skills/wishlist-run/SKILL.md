---
name: wishlist-run
description: Safe protocol to run the WC2026 wishlist / waiver auction for a gameweek on the managers' REAL bids. Use when the user says "run the wishlist", "run the auction", "resolve the waivers", "free agents window opened — run it", or at FA-open. Snapshots bids, dry-runs a preview (claimed/denied by round), runs the real auction ONCE (idempotent), verifies the result + full history, and can roll back. NEVER uses the mock auto-fill path. Orchestration skill: confirms before the real run and before any rollback.
---

# Wishlist auction — safe run (snapshot → dry-run → run once → verify → rollback-if-needed)

This codifies the GW2 recovery so it never goes sideways again. Root cause then:
the "Run wishlist" button called `run-mock-wishlist`, which **fabricated fake bids**
and ran **twice**. Both are now fixed (PR #103) — this skill is the disciplined path.
See `memory/wishlist-auction-mechanics.md`.

## Step 0 — Ground rules
- `.venv/bin/python`; prod `gamedb` via firebase-adminsdk SA token (`WC_TOKEN`, as in gw-transition).
- League `lg_mock_draft` (parameterize `lid`). Times in Israel (IDT). Run from this Mac.
- The auction = `WCWishlistManager.run_auction(lid, gw)` (waiver round-robin, last-place-first, one claim/round, cycling). Idempotent: refuses if `wishlist_results/{gw}` exists unless `force`. Bids are PRESERVED + marked `done-completed`/`done-denied` (not deleted).

## Step 1 — Snapshot bids (always, correctly timestamped)
Dump `leagues/{lid}/wishlist_bids/*_{gw}` to a JSON tagged with the **real** capture time in BOTH UTC and Israel (do NOT hardcode — read the clock). This is the only fallback if anything goes wrong. (Lesson: a mislabeled snapshot cost real time.)

## Step 2 — Dry-run preview (read-only, no writes)
Mirror `run_auction` in memory against the live bids + squads (real `_ordered_managers` + per-bid validation; do NOT call `_execute_swap`/writes). Print the **full round-by-round log**: every claim and every cancel, in order, with the reason and who-won. Show per-manager `claimed/total`. Confirm with the user this is the intended outcome before running for real.

## Step 3 — Run for real (CONFIRM, once)
```python
result = WCWishlistManager(db).run_auction(lid, gw)   # 409/ValueError if already resolved
```
- If it raises `ALREADY_RESOLVED`: the GW already ran — do NOT force-rerun blindly; roll back first (Step 5) if the prior run was wrong.
- Do this from the SKILL/script, NOT via the live "Run wishlist" UI button, and NEVER via `run-mock-wishlist` (simulated-leagues only now).

## Step 4 — Verify
- Claims match the dry-run; `wishlist_results/{gw}` records ALL bids (claimed AND denied) with reasons; one `wishlist_claim` transaction per claim; squad sizes unchanged (15 each); per-bid status keyed by (uid,playerIn,playerOut) so a cancelled fallback isn't mis-shown as claimed.
- Then run `/squad-lineup-audit` for the GW (the auction changes squads → lineups may need reconcile).

## Step 5 — Rollback (CONFIRM) if the run was wrong
```python
WCWishlistManager(db).rollback_auction(lid, gw)   # all-or-nothing
```
Reverses every claim (squads → pre-auction), reopens the bids (pending), clears the results doc + the GW's `wishlist_claim` transactions. Then fix bids and re-run from Step 1.

## Guardrails
- Confirm before Step 3 (run) and Step 5 (rollback); both are prod mutations.
- After a clean run, set the window to `free_agents` only if that's the intended phase; otherwise leave the window as-is.
- If bids look contaminated (counts don't match a trusted snapshot), reconcile bids to the snapshot BEFORE running — never union in prior winning-claims (that mistake injected phantom bids in GW2).
