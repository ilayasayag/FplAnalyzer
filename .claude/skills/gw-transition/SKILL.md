---
name: gw-transition
description: Master runbook for moving the WC2026 league from one gameweek to the next — end the current GW (validate, finalize) and start the next (open windows, run wishlist, set the lineup lock, open Pick Team). Use when the user says "transition the gameweek", "end gw and start the next", "move to the next gw", "gw rollover", "what do I do now that gwN ended", or at any GW boundary. Orchestration skill: it PERFORMS actions but confirms before every prod write; it chains the read-only validation skills and the wishlist-run skill in the correct order.
---

# GW transition — the one ordered protocol per gameweek boundary

This is the checklist we wished we had during GW2. It sequences the **three
independent clocks** people conflate — and they are NOT the same moment:

- **Lineup lock** = `T0 − squad_lock_before_hours` (default 1h before the GW's first
  kickoff). Freezes squads/XI. Per-league override: `leagues/{lid}.lineupLockOverride[gw]`.
- **Window phase** (trade / free_agents / next_gw_bid) = the lazy resolver:
  passed `windowSchedule` entry > manual `windowOverride` > fixture clock. **No cron.**
- **Finalize** = scoring. **Manual**, and only AFTER all that GW's matches are FT +
  scored (group GWs span ~6 days). Never happens at the lineup lock.

See `memory/window-scheduling-mechanism.md`, `memory/lineup-lock-override-and-pickblock.md`.

## Step 0 — Ground rules (same as gw-end-validations)
- Python: `/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python`.
- Prod = Firestore `gamedb`. Auth with the firebase-adminsdk SA (gcloud user lacks perms):
  ```bash
  SA=firebase-adminsdk-fbsvc@fpl-analyzer-792eb.iam.gserviceaccount.com
  export WC_TOKEN=$(gcloud auth print-access-token --account="$SA")
  ```
  In Python: `firestore.Client(project="fpl-analyzer-792eb", credentials=Credentials(token=os.environ["WC_TOKEN"]), database="gamedb")`.
- League: `lg_mock_draft` (parameterize `lid` if asked). All human-facing times in **Israel (IDT, UTC+3)**.
- **Push/PR/deploy** (only if code changes): `gh auth switch --user ilayasayag` first (see `memory/git-push-needs-owner-account.md`); deploy from a clean merged-main worktree (`memory/deploy-from-clean-checkout.md`).
- Run from THIS Mac (WhoScored/DefCon needs the residential IP).

## A. END the current GW (gw = n)
1. **Scores fresh?** run `/sync-gw-scores` for `n` — all `n` fixtures FT + scored. If not all matches are played, STOP: you can't finalize yet.
2. **Validate (read-only):** run `/gw-end-validations` for `n` (DefCon, points, lineups, H2H + מצטיין מחזור, wishlist order) AND `/squad-lineup-audit` for `n`. Resolve any FAIL before finalizing.
3. **Finalize (CONFIRM):** `finalize_gw(n)` writes `scores/{n}`, `gw_history`, `standings/{n}`, `schedule/{n}` (H2H), bracket. Missing lineups now carry forward from the prior GW (PR #105). Scoring invariant: `fantasyPoints = FIFA total + DefCon − scouting`.
4. **Reconcile (read-only):** run `/post-finalize-reconcile` for `n`.

## B. START the next GW (gw = n+1)
5. **Advance** `leagues/{lid}.currentGw → n+1` (CONFIRM). Confirm GW n+1's first kickoff (T0) and derive the three clocks.
6. **Open Trade window** (CONFIRM): `windowOverride = {phase:"trade", gw:n+1}`; clear any stale `windowSchedule`.
7. **At FA-open time → run the wishlist auction:** use `/wishlist-run` (snapshot → dry-run → run once → verify → rollback-if-needed). Then set the window to `free_agents` (CONFIRM).
8. **Set the next lineup lock + schedule** (CONFIRM): if you want a custom deadline, set `lineupLockOverride[n+1] = <ISO-UTC>` (e.g. 21:30 IL = 18:30 UTC) and `windowSchedule = [{phase:"next_gw_bid", effectiveAt:<lockISO>, gw:n+1}]` so Free agents → Gameweek at the deadline. Validate with `/window-schedule-check`.
9. **Pick Team** then auto-targets n+1 (the `edit-gw` endpoint walks to the first unlocked GW). Optionally set a per-GW `pickBlockByGw[n+1]` to disable specific teams' players.
10. **At the deadline:** lineups lock automatically (any save after is rejected). Run `/squad-lineup-audit` for n+1 one last time so every lineup ⊆ squad before kickoff.

## Guardrails (STRICT — chosen default)
- Confirm before EVERY prod write; show the exact before/after.
- **Never** edit a lineup after its lock without explicit override AND verifying no swapped-in/out player has already kicked off (see `/squad-lineup-audit`).
- Never run the wishlist via the mock auto-fill path — only `/wishlist-run` (real bids). See `memory/wishlist-auction-mechanics.md`.
- Back up before any destructive step (squads/lineups → timestamped JSON).

## Scheduled reminders
There is no built-in scheduler. After Step 5, set Israel-time reminders (via `/schedule`) for: FA-open (run `/wishlist-run`), the lineup-lock deadline (run `/squad-lineup-audit`), and ~the day after the last match (run `/sync-gw-scores` then End-of-GW A1–A4). The reminders only PING; you run the skill.
