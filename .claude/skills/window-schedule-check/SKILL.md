---
name: window-schedule-check
description: Read-only validator that the WC2026 window phase, lineup lock, and currentGw are correctly set for the upcoming gameweek, with a clear "what fires when" timeline in Israel time. Use when the user says "check the window schedule", "is the window set right", "when does the window flip", "validate the lock time", or before/after configuring a GW's windows. Confirms the lazy resolver will produce the intended phase + lock at the intended minutes; proposes a fix only on explicit confirm. Prevents the "closed at 18:00 not 18:30" confusion.
---

# Window / lock / schedule check (read-only; fixes only on confirm)

The three clocks are independent and people conflate them. This proves what the
lazy resolver will ACTUALLY do, in Israel time. See `memory/window-scheduling-mechanism.md`.

## Step 0 — Ground rules
- `.venv/bin/python`; prod `gamedb` via firebase-adminsdk SA token (`WC_TOKEN`).
- League `lg_mock_draft` (parameterize `lid`). All times shown in **Israel (IDT, UTC+3)**.
- **No scheduler exists** — phases/locks apply LAZILY on the next read. State that in the output (a flip "happens" when someone loads the page at/after the time).

## Step 1 — Read the config (read-only)
- `leagues/{lid}`: `currentGw`, `windowOverride`, `windowSchedule` (list of `{phase, effectiveAt, gw}`), `lineupLockOverride` (`{gw: ISO-UTC}`), `pickBlockByGw`.
- `wc_config/tournament`: `fa_open_before_hours`, `squad_lock_before_hours`, `match_duration_minutes`.
- Upcoming GW first kickoff (T0) from `wc_fixtures` where `gw == currentGw`.

## Step 2 — Resolve + build the timeline (use the real code)
```python
from fpl_predictor.game.wc_windows import current_window_from_db, is_lineup_locked, lineup_lock_time
```
Compute and PRINT, each in UTC **and** Israel time:
- **Now:** the resolved window phase (`current_window_from_db(lid, db, now)`), and whether the GW lineup is locked (`is_lineup_locked(db, gw, lid=lid)`).
- **Lineup lock instant:** `lineup_lock_time(db, gw, lid=lid)` — flag whether it's the `lineupLockOverride` or the fixture-clock `T0 − squad_lock_before_hours`.
- **Each `windowSchedule` entry:** phase + when it flips, and the resolved phase just before/after that minute.
- **A "what fires when" timeline:** ordered rows (time IL · time UTC · what changes) through to T0.

## Step 3 — Assert the intent
Ask/confirm the intended setup (e.g. "Free agents now → Gameweek at 21:30 IL; lineup locks 21:30 IL") and assert the resolved timeline matches. FLAG mismatches, e.g.:
- lineup lock ≠ the intended deadline (override missing or wrong) — the GW2 "18:00 vs 18:30" trap (the fixture lock is T0−1h, separate from `windowSchedule`).
- `windowSchedule` entry in the past / wrong phase / wrong gw.
- `currentGw` not the upcoming GW.
- `windowOverride` fighting the schedule (passed schedule entry wins).

## Step 4 — Propose + apply fix (CONFIRM)
Show the exact field change (e.g. set `lineupLockOverride["3"] = "2026-06-24T18:30:00Z"`, or `windowSchedule = [...]`) and apply on the user's OK. Israel-time inputs convert to UTC (IDT = +3). Re-run Step 2 to confirm the timeline now matches intent.
