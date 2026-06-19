# WC2026 — Session handoff (2026-06-18, GW1-end → GW2-live)

Pick up cold from here. Verify every claim against live repo/prod before acting
(use `/pickup-handoff`). Times are **Israel (IDT, UTC+3)** unless marked UTC.

## Where things stand
- **main:** `ba7a97c`. **Hosting live:** `v=60`. Backend `functions:api` deployed off main.
- **League:** `lg_mock_draft` (the active "real" league; despite the name). 6 managers:
  `u_ilay, u_nadav, u_netanel, u_roy, u_shay, u_yuval` (Chen-David).
- **GW state:** `currentGw = 2`. GW2 is **live** (first kickoff 2026-06-18 16:00 UTC; group GW2 fixtures run through ~2026-06-24). **GW2 is NOT finalized** (no `scores/2`/`gw_history_2`/`standings/2` at handoff time — confirm before finalizing).
- **GW2 lineup lock:** `lineupLockOverride = {"2": "2026-06-18T18:30:00Z"}` (21:30 IL) — **passed**. Lineups are locked.
- **Window:** `windowSchedule = [{phase:"next_gw_bid", effectiveAt:"2026-06-18T18:30:00Z", gw:2}]` → resolved phase is **Gameweek** (next_gw_bid) now. `windowOverride` may still read `free_agents` but the passed schedule entry wins.
- **GW2 pick blocklist:** `pickBlockByGw = {"2": [52 CZE+RSA ids]}` — CZE/RSA can't be STARTED in GW2 (managers' agreement). Clear it for GW3.

## What shipped this session (PRs, all merged + deployed unless noted)
- **#97** wishlist last-place-first order + gw-end tooling.
- **#96** gameweek bids + per-player Trade button (resolved vs #98's modal).
- **#100** swap-modal stat+fixture comparison (`PickupCompare`).
- **#101** lazy scheduled window overrides + **Ilay-only** window control + schedule editor UI.
- **#103** secure wishlist: `run-mock-wishlist`→simulated-only; button→real auction; `run_auction` idempotent + bids preserved/marked + `rollback_auction`.
- **#104** per-league `lineupLockOverride` + per-GW `pickBlockByGw`.
- **#105** `finalize_gw` carries forward a missing lineup (no 0-pt skips).
- **#106** Points pitch reflects saved lineup (retry + save-sync); renamed `MY_LINEUP_GW3→MY_LINEUP`, `GW3_POINTS→GW_POINTS`, `GW3_TOTALS→GW_TOTALS`.
- **#99 CLOSED** (Netanel CR cleanup). **#102 OPEN** — "position-specific stat comparison + compact modal", overlaps #100; review/close or merge.

## The GW2 incident (so it's not repeated)
1. The "Run wishlist" button called `run-mock-wishlist`, which **fabricated fake bids** for everyone and ran **twice** → 22 bogus claims, Ilay's real bids dropped.
2. **Recovered:** reversed all 24 GW2 transactions → squads back to GW1-end; the bid snapshot was actually the **16:30 IL deadline** capture (initially mislabeled 12:57).
3. Re-ran the REAL auction on the deadline bids → **10 claims** (Roy 3, Chen-David 2, Nadav 2, Ilay 1, Netanel 2, Shay 0), full claimed/denied history saved, trade window opened.
4. Set GW2 lock 21:30 IL, blocked CZE+RSA, deleted premature GW3 lineups, carried Shay's GW2=GW1.
5. Fixed Yuval's stale lineup (free-agent swap left Vargas dangling / Leão missing). Set Chen's 4-4-2 via **post-lock override** (fair — swapped players hadn't kicked off; `adminOverrideAt` tagged on `lineups/u_yuval_2`).

## Known gotchas (all in `memory/`)
- **No scheduler.** 3 independent clocks: lineup lock (T0−`squad_lock_before_hours`, override-able), window phase (lazy resolver), finalize (manual). [[window-scheduling-mechanism]] [[gw-finalize-lock-mechanics]]
- **Free-agent/wishlist swaps update the squad but NOT the lineup** → stale lineups. Not yet code-guarded. [[lineup-lock-override-and-pickblock]]
- `run-mock-wishlist` fabricates bids — sim-only now. [[wishlist-auction-mechanics]]
- Push needs `gh auth switch --user ilayasayag`. [[git-push-needs-owner-account]]
- Deploy from a clean merged-main worktree (+venv +secrets). [[deploy-from-clean-checkout]]
- JSX needs an SSR runtime check, not just Babel. [[jsx-compile-not-runtime]]

## New tooling added (this PR)
Skills: `gw-transition` (master runbook), `squad-lineup-audit`, `wishlist-run`,
`window-schedule-check`, `post-finalize-reconcile`. See `CODE_FOLLOWUPS.md` for queued
code fixes.

## Immediate next actions
1. When GW2 matches finish (~Jun 24): run `/gw-transition` (it chains sync → validate → finalize → reconcile, then opens GW3).
2. Set Israel-time scheduled reminders for GW3 boundaries (FA-open / lock / finalize).
3. Review/close PR #102. Queue the free-agent→lineup reconcile guard (CODE_FOLLOWUPS.md).
