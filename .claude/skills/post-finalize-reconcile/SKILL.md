---
name: post-finalize-reconcile
description: Read-only consistency check run AFTER finalize_gw, confirming the WC2026 scoring artifacts agree — scores, gw_history, standings, H2H — that every manager was scored (none skipped), carry-forwards applied, and the scoring invariant holds. Use when the user says "reconcile the finalize", "did finalize work", "check standings after finalizing", "post finalize check", or right after running finalize_gw(n). Proposes a fix (e.g. re-finalize, fill a gap) only on explicit confirm.
---

# Post-finalize reconcile (read-only; fixes only on confirm)

Run immediately after `finalize_gw(n)` to confirm scoring is whole and consistent.
Complements `/gw-end-validations` (which runs BEFORE finalize). See
`memory/gw-finalize-lock-mechanics.md`.

## Step 0 — Ground rules
- `.venv/bin/python`; prod `gamedb` via firebase-adminsdk SA token (`WC_TOKEN`).
- League `lg_mock_draft` (parameterize `lid`). Times in Israel (IDT).

## Step 1 — Artifacts exist + agree (read-only)
For finalized gw `n`, assert:

| Check | Asserts |
|---|---|
| **scores/{n}** | exists; `results` has an entry for EVERY active member (none skipped) |
| **gw_history** | a `{uid}_{n}` snapshot for every member; `locked: True`; starting/bench frozen |
| **carry-forward** | any manager who had no `{uid}_{n}` lineup was scored on the prior GW's XI (`carriedForwardFrom` set), NOT 0 (PR #105) — flag anyone scored 0 with an empty/absent lineup |
| **standings/{n}** | exists; per-manager totals = Σ finalized GW points to date; standings/current matches |
| **H2H (schedule/{n})** | W=3 / D=1 / L=0 from the GW points, **+1 'מצטיין מחזור'** to the top GW scorer; matches stored values |
| **invariant** | per scored player, `fantasyPoints == FIFA total + DefCon − scouting`; squad total == Σ(starters post-autosub) + captain×2 |
| **transactions** | the GW's wishlist/free-agent/trade history is coherent (no dangling claims; bids marked resolved) |

## Step 2 — Cross-check against the pre-finalize preview
If `/gw-end-validations` was run before finalize, confirm the finalized H2H + points match its PREVIEW (no drift between preview and stored).

## Step 3 — Report + propose fix (CONFIRM)
Print PASS/FAIL per check with the offending uid/player. Common fixes (each needs OK):
- A skipped/0-pt manager with a real prior lineup → materialize the carry-forward lineup and re-finalize `n`.
- Standings/H2H drift → re-run `finalize_gw(n)` (idempotent on scores) or correct the specific doc.
- DefCon/invariant breach → guarded resync (see `/gw-end-validations` Step 3) then re-finalize.

Pure read-only unless a fix is explicitly confirmed.
