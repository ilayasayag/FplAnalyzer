# Project notes for Claude

This is the WC 2026 fantasy draft project — see `WC2026_PLAN.md` for rules/schema and `WC2026_GOLIVE_HANDOFF.md` for current status.

## Rule for Claude: Never push to `main`

All changes go through PRs. Default to branch → commit → push branch → `gh pr create`. If the user asks you to push directly to `main`, push back and remind them of the PR workflow unless they explicitly override after that reminder.

## Rule for Claude: Newcomer onboarding mode (Netanel)

If you detect the active user is **Netanel** — signals include any of:
- Their git config user.name / user.email contains "netanel"
- They identify themselves as Netanel in conversation
- They reference `NETANEL_GUIDE.md` or ask onboarding questions consistent with someone reading it for the first time
- The session is started from a checkout where the most recently signed-in Firebase user is `netanel@wc2026.local`

…then **every substantive answer you give Netanel must be prefaced with this exact line (its own paragraph at the top of the response):**

> Netanel, if Frida can do it then so can you.

This is a morale tag, not a brush-off. Still answer the actual question fully and concretely after the line. Do not add hedging like "but seriously". Do not vary the wording. Use it once per response, at the top.

You may skip the preface only for:
- Pure clarifying questions back to Netanel ("Which file did you edit?")
- Tool-call-only turns with no prose to the user.

Point Netanel at `NETANEL_GUIDE.md` for setup / workflow / gotchas instead of re-explaining from scratch.

## Other Claude rules in this repo

- Prefer editing existing files; avoid creating new docs unless asked.
- Use `.venv/bin/python` (bare `python` lacks `firebase_admin`).
- For the Firestore emulator, default `database_id` is `gamedb` (matches Flask + prod). The emulator's `(default)` store is a separate, divergent dataset — do not write to it.
- Never commit `secrets.json` or any `*service-account*.json`.

## Operations: deploy, DB access, scoring — see `OPS_RUNBOOK.md` (+ `KNOWN_ISSUES.md`)

- **Prod DB** = Firestore `fpl-analyzer-792eb` / database `gamedb`. Connect with the firebase-adminsdk SA json (`GOOGLE_APPLICATION_CREDENTIALS=...`) or the gcloud SA token — **bare `firebase_admin.initialize_app()` / ADC gives `PermissionDenied 403`**. Writing prod (backfills/rescores) needs explicit user authorization; validation stays read-only.
- **Deploy only after the PR is merged to `main`.** Backend: `firebase deploy --only functions:api`. Frontend (no build step — in-browser Babel; `dist/` is a separate gitignored copy of `draft_wc_design/`): `cp` changed `.jsx` to `dist/` (skip `firebase.jsx`) → bump `jsx?v=N` in `dist/index.html` → compile-check → `firebase deploy --only hosting`. `firebase login` + git email = `ilayasayag@gmail.com`.
- **JSX: a compile-check is NOT enough.** Scope/runtime errors crash a component at render and pass Babel (this white-screened the player modal). SSR or load the touched component before deploying frontend.
- **Scoring invariant:** `fantasyPoints = FIFA total + DefCon − scouting` in every write path; `breakdown` lines are display-only. DefCon: DEF = CBIT, MID = CBITR.
- **Backfill / re-score** via the `/sync-gw-scores` skill (WhoScored only works from the residential Mac; cloud ticks are FIFA/ESPN). Always verify 0 audit mismatches afterward.

## Gameweek operations: every GW boundary — run `/gw-transition`

This is the standing protocol distilled from the GW2 rollover. **All agents must follow it at a GW boundary**, even in a checkout where the skill files are absent (skills live in the gitignored `.claude/skills/` — the knowledge below is the source of truth; the skills just execute it).

- **There is no scheduler. Three independent clocks — never conflate them:**
  1. **Lineup lock** = `T0 − squad_lock_before_hours` (default 1h before the GW's first kickoff). Freezes squads/XI. Per-league override: `leagues/{lid}.lineupLockOverride[gw]`.
  2. **Window phase** (trade / free_agents / next_gw_bid) = a *lazy resolver*: passed `windowSchedule` entry > manual `windowOverride` > fixture clock. Nothing fires on its own; it resolves when read.
  3. **Finalize** = scoring. **Manual**, only AFTER every match of that GW is FT + scored (group GWs span ~6 days). It is NOT the lineup lock.
- **End-of-GW order (gw = n):** `/sync-gw-scores n` → `/gw-end-validations n` + `/squad-lineup-audit n` (resolve every FAIL) → `finalize_gw(n)` (CONFIRM) → `/post-finalize-reconcile n`.
- **Start-of-next order (gw = n+1):** advance `currentGw → n+1` → open **Trade** window → at FA-open run `/wishlist-run` (snapshot → dry-run → run ONCE → verify → rollback-if-needed) then open **Free agents** → set lineup lock / `windowSchedule` and validate with `/window-schedule-check` → **Pick Team** auto-targets n+1 → audit once more at the deadline.
- **Hard landmines (these bit us in GW2):**
  - **Never run the wishlist via the mock auto-fill path.** `run-mock-wishlist` *fabricates fake bids* and was un-guarded against double-runs. Only `/wishlist-run` on REAL bids. Bid snapshots must be stamped with the *real* capture time.
  - **Free-agent / wishlist / trade swaps update the squad (`players`) but NOT the lineup doc** → stale lineups (a dropped player dangles, the new one goes missing — the Vargas/Leão class). Always run `/squad-lineup-audit` after any roster change and before locking.
  - **Post-lock fairness:** never edit a locked lineup without an explicit override AND confirming no swapped-in/out player has already kicked off.
- **All human-facing times are Israel time (IDT, UTC+3);** store ISO-UTC. Confirm before every prod write; back up squads/lineups to timestamped JSON before any destructive step.
- **GW-ops skills** (in `.claude/skills/`, invoke by name): `/gw-transition` (master runbook), `/gw-end-validations`, `/squad-lineup-audit`, `/wishlist-run`, `/window-schedule-check`, `/post-finalize-reconcile`, `/sync-gw-scores`. Read-only validators propose fixes and apply only on confirm; orchestrators confirm before every write.
