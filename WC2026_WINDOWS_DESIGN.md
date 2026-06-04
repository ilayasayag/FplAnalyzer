# WC 2026 — Transfer Windows Design & Implementation Handoff

> **Status:** design locked, ready to implement. Written by the mentor/manager agent (session 6).
> **Read first:** §0 (decisions), §3 (data model), §8 (PR sequence + acceptance criteria).
> **Audience:** the implementing agent. You will build this in a series of small PRs, one per §8 item.
> I (the managing agent) will review each PR and merge. Do **not** batch multiple PRs together.

---

## 0. Locked decisions (do not relitigate — these were decided with the user)

| Decision | Choice |
|---|---|
| Window timing anchor | **Kickoff-relative**, all windows run **before** the upcoming GW's first kickoff (`T0` = lineup lock) |
| Window durations | **Configurable** via `wc_config/tournament`: `trade_window_hours` (default 5), `free_agent_window_hours` (default 5) |
| Wishlist ordering | **Reuse `waiverPriority`** (reversed → last-pick-first), no snake |
| Deferred next-gw trades | **Reuse existing `trades` collection** with a `deferred_pending` status |
| Bid storage | **One new subcollection** `wishlist_bids` only; trades reuse `trades`; free-agent signings store nothing (immediate) |
| `gw-fixture-draft-gw` | **DROPPED** — redundant with `scores/{gw}.h2hResults` + `schedule/{gw}.matches[]` |
| `gw_history` snapshot timing | **At `finalize_gw`**, once player points are final |
| State representation | **Enums** (`str, Enum`) replacing bare-string statuses, introduced incrementally |

---

## 1. The problem we're fixing

Today there is **no real window orchestration**. Three contradictory "is the window open?" checks coexist:

1. `wc_gameweeks.py:190 is_transfer_window_open(gw, now)` — time-based, **off-by-one** (passes `gw-1`/0 so GW1's window never opens).
2. `wc_scoring.py:744 _open_transfer_window(lid, gw, db)` (called from `finalize_gw` at line 632) — writes a `transfer_windows/{auto-id}` doc with `status:"open"` that is **never set to "closed."**
3. `wc_waivers.py:440 _validate_in_submission_phase` — a **stub** (`pass`); waiver gating leans on `league.status` only.

These collapse into **one** deterministic function (§2). The user's spec needs exactly one of {trade, free_agents, next_gw_bid} open at a time, cycling per GW.

---

## 2. Window state machine + timeline

### 2.1 Enum

```python
# new: fpl_predictor/game/wc_windows.py
from enum import Enum

class TransferWindow(str, Enum):
    NONE        = "none"          # mid-GW; nothing open
    TRADE       = "trade"         # wishlist bids + manager<->manager trades
    FREE_AGENTS = "free_agents"   # immediate same-position signings only
    NEXT_GW_BID = "next_gw_bid"   # propose trades + auto-approve-for-next only
```

### 2.2 Timeline (all before `T0`)

Let `T0` = first kickoff of the upcoming GW(n) (= lineup lock), and `Tprev_end` = final whistle of GW(n−1)'s last match. Both are derivable from `wc_fixtures` kickoff times + match duration; **no dependency on when finalize actually runs.**

```
Tprev_end ───TRADE──► +trade_window_hours ───FREE_AGENTS──► +free_agent_window_hours ───NEXT_GW_BID──► T0 (lock)
```

| Window | Opens | Closes |
|---|---|---|
| `TRADE` | `Tprev_end` | `Tprev_end + trade_window_hours` |
| `FREE_AGENTS` | trade close | `+ free_agent_window_hours` |
| `NEXT_GW_BID` | free-agent close | `T0` |

**Short-turnaround guard (must implement):** if `Tprev_end + trade_window_hours + free_agent_window_hours > T0`, compress proportionally so windows never overrun `T0`. Concretely: `gap = T0 - Tprev_end`; if `gap < (trade_h + fa_h)` hours, scale both by `gap / (trade_h + fa_h)` and give `NEXT_GW_BID` whatever (possibly zero) remains. Never let a window close after `T0`.

### 2.3 The single source of truth

```python
def current_window(league_doc, fixtures_for_gw, config, now) -> tuple[TransferWindow, int]:
    """Pure function. Returns (window, gw) for the upcoming GW.
    Computes Tprev_end and T0 from fixtures; applies config durations + guard.
    No Firestore writes. Everything else gates on this."""
```

- `is_transfer_window_open` (gameweeks) becomes a thin wrapper: `current_window(...)[0] != NONE`. Fixes the off-by-one by construction.
- `_open_transfer_window` / the `transfer_windows` doc: keep writing an **audit** doc if you like, but it must **not** be a gate. The gate is `current_window`. If you keep the doc, set `closedAt` when the window transitions — but prefer deleting the stored-flag logic entirely to avoid a 4th source of truth.

---

## 3. Data model

### 3.1 New: `wishlist_bids` (only genuinely new collection)

Path: `leagues/{lid}/wishlist_bids/{uid}_{gw}` — **one doc per manager per GW**.

```jsonc
{
  "uid": "u_abc",
  "gw": 4,
  "bids": [                       // ORDERED; index 0 tried first
    { "playerIn": 12, "playerOut": 88, "position": "MID" },
    { "playerIn": 47, "playerOut": 88, "position": "MID" }
  ],
  "createdAt": <server ts>,
  "updatedAt": <server ts>
}
```

- Deleted (batch) after the wishlist auction resolves at trade-window close.
- `position` must match for both players (same-position swap). Validate on write.

### 3.2 Reused: `trades` (`leagues/{lid}/trades/{id}`)

Add enum + the `deferred_pending` status. Proposed enum (supersedes bare strings currently at `wc_trades.py:180-310`):

```python
class TradeStatus(str, Enum):
    PENDING          = "pending"
    DECLINED         = "declined"
    ACCEPTED         = "accepted"
    AWAITING_ADMIN   = "awaiting_admin"
    AWAITING_VOTE    = "awaiting_vote"
    VETOED           = "vetoed"
    CANCELLED        = "cancelled"
    EXPIRED          = "expired"
    DEFERRED_PENDING = "deferred_pending"   # NEW: auto-approved in next_gw_bid, executes at next trade-window open
```

### 3.3 New: `gw_history` (snapshot at finalize)

Path: `leagues/{lid}/gw_history/{uid}_{gw}`.

```jsonc
{
  "uid": "u_abc",
  "gw": 4,
  "players": [ { "id": 12, "points": 6 }, { "id": 88, "points": 2 }, ... ],  // the 15 FIELDED (lineup) IDs joined to playerScores
  "totalPoints": 54,
  "opponent": "u_xyz",
  "opponentPoints": 41,
  "result": "W"                  // "W" | "L" | "D"
}
```

This performs the **lineup-IDs → playerScores join that currently happens nowhere** — the genuinely missing per-manager per-player breakdown. Source data:
- Lineup IDs: `lineups/{uid}_{gw}` (starting/bench/captain).
- Per-player points: `wc_fixtures/{fid}/playerScores/{pid}.fantasyPoints`.
- Opponent + result + points: `scores/{gw}.h2hResults.{uid}` = `{opponent, result, pointsFor, pointsAgainst}`.

### 3.4 Config additions (`wc_config/tournament`)

```jsonc
{ "trade_window_hours": 5, "free_agent_window_hours": 5 }
```

---

## 4. Wishlist auction algorithm (PR 4)

Runs **once** at trade-window close, inside a transaction (or a tight batch with re-reads). Reuses `waiverPriority`.

```
order = managers sorted by waiverPriority DESC        # last pick first; reverse of normal waiver order
claimed_in  = set()    # playerIns already taken this auction
replaced_out = set()   # (uid, playerOut) already used this auction
progressing = True
while progressing:
    progressing = False
    for uid in order:
        wl = wishlist_bids[uid_gw].bids        # ordered
        for bid in wl (in order, skipping ones already consumed for this uid):
            valid = (bid.playerIn is still a free agent)
                and (bid.playerIn not in claimed_in)
                and (bid.playerOut still on uid's squad)
                and ((uid, bid.playerOut) not in replaced_out)
                and (squad quota stays legal after swap)   # 2 GK / 5 DEF / 5 MID / 3 FWD
            if valid:
                execute swap atomically (remove playerOut, add playerIn)
                mark playerIn unavailable (claimed_in.add; persist on player/squad as needed)
                replaced_out.add((uid, bid.playerOut))
                mark this uid as "claimed this round"; progressing = True
                break        # one successful claim per manager per round
            else:
                continue     # auto-skip to next bid in this manager's list
# after loop: batch-delete all wishlist_bids/*_{gw}
```

**Notes for implementer:**
- "One successful claim per manager per round" then round-robin again — this matches the user's "moves to the next manager" then keeps cycling until no one can claim. Confirm with mentor if a single pass (one claim per manager total) is wanted instead; spec reads as multi-round but **default to multi-round** and flag it in the PR description.
- Explicit unavailable-marking is the piece the current code lacks — without it two managers could claim the same free agent in one batch.
- Quota check uses the same position-count logic already in `wc_squads.sign_free_agent`.

---

## 5. Atomic trades (PR 3)

`wc_trades.py:316 _execute_trade` currently does two separate `.update()` (lines 337-338) → crash between them corrupts both squads.

**Rewrite** as a single `@firestore.transactional` function that:
1. Re-reads both squads inside the txn.
2. Re-validates ownership (each side still owns the players it's giving) + position-count match + quota legality.
3. Applies both `players` arrays in one commit.

Template: `wc_squads.py:236 _claim` (the working `@transactional` used by `sign_free_agent`).

**Also delete** the orphan non-atomic `wc_waivers.py:256 sign_free_agent` (the wired/atomic one is `wc_squads.py:175`). Grep for callers first; expect none.

---

## 6. Deferred next-gw trades (PR 5)

In `NEXT_GW_BID`: managers may propose trades and mark "auto-approve when next trade window opens." Store as a normal `trades/{id}` doc with `status = deferred_pending`. The function that **opens the next trade window** (or the auction resolver) scans `trades where status == deferred_pending` and executes them **atomically first** (via the PR 3 transactional `_execute_trade`), before the wishlist auction. Re-validate at execution time (squads may have changed); if invalid, mark `cancelled` with a reason.

---

## 7. Frontend squad-flash fix (PR 1 — independent, low risk)

**Cause:** `draft_wc_design/data.jsx` exposes demo consts `MY_SQUAD_IDS` (lines ~254-263) and `MY_LINEUP_GW3` (~266-276) on `window`. Pick Team renders these **first**, then the real `/squads/me` fetch overwrites the window globals → visible flash from a wrong squad to the real one.

**Fix:** gate the Pick Team render on a `squadLoaded` boolean (state in `app.jsx`, set true only after the real fetch resolves). Show a skeleton/spinner until then. Do **not** seed visible UI from the demo arrays for real users. Keep the demo arrays only as a fallback for the static/no-auth demo mode if needed.

Bump `jsx?v=N` cache-bust (currently `v=23` per index) when shipping any `.jsx` change.

---

## 8. PR sequence + acceptance criteria

Each PR: branch off **fresh `origin/main`** (currently `164aa6f`), worktree-isolated, squash-merge, `Co-Authored-By: Claude` trailer, push via `ilayasayag` then **switch back to `ilay-asayag`**. Never push `main` directly.

| PR | Scope | Acceptance criteria |
|---|---|---|
| **1** | Squad-flash fix | No flash on Pick Team for a real user; skeleton shows until squad loads; demo mode still renders; `jsx?v` bumped |
| **2** | `wc_windows.py` enum + `current_window` + config keys; rewire `is_transfer_window_open` | Unit tests for timeline incl. short-turnaround guard; GW1 window opens (off-by-one gone); only one window open at any `now`; no behavior change to scoring |
| **3** | Atomic `_execute_trade`; delete orphan free-agent | Trade swap is single-commit transactional; re-validates inside txn; orphan deleted with no remaining callers; existing trade tests pass |
| **4** | Wishlist auction module + `wishlist_bids` writes/validation | Auction resolves last-pick-first, auto-skips invalid bids, marks playerIn unavailable, respects quota, wipes `wishlist_bids` after; tests cover contested player + already-replaced-out |
| **5** | Deferred next-gw trades | `deferred_pending` created in `NEXT_GW_BID`; executed atomically at next trade-window open, before auction; re-validated, invalids cancelled with reason |
| **6** | `gw_history` snapshot in `finalize_gw` | Doc written per manager per GW with correct per-player points (lineup→playerScores join), totalPoints, opponent, opponentPoints, result; `gw-fixture-draft-gw` NOT created |
| **7** | Open trade window in `lg_mock_draft` | Full flow demoable end-to-end in the mock league |

**Dependencies:** 2 is foundation for 4/5/6/7. 4 and 5 depend on 3 (transactional template / executor). 7 depends on 3+5+6. 1 is independent.

---

## 9. Gotchas / landmines

- **Named DB:** all Firestore work uses database `gamedb` (matches Flask + prod). The emulator `(default)` store is a separate divergent dataset — never write to it.
- **Python:** use `.venv/bin/python` (bare `python` lacks `firebase_admin`).
- **Two FPL engines:** WC engine is `wc_*.py` / blueprint `wc_bp` at `/api/v1/wc`. There's a LEGACY non-WC engine (`scoring.py`, `squads.py`, `schedule.py`) — do **not** conflate or edit it.
- **`request.get_json`:** always `get_json(silent=True) or {}` (raises 400 otherwise on empty body). Already fixed across `api_wc.py`; keep the pattern in any new routes.
- **Deploy:** `firebase.json` predeploy copies `fpl_predictor` → `functions/fpl_predictor`. New modules under `fpl_predictor/game/` ship automatically. Bundled data files live in `fpl_predictor/data/`.
- **Atomicity reference:** the only existing correct transactional write is `wc_squads.py:236`. `finalize_gw` is NOT atomic (sequence of writes); `process_fixture` uses `db.batch()` (atomic).
- **Security rules:** there's a pre-existing open-write gap on `leagues`/`lineups` rules (left as-is per user; security is explicitly out of scope — "just a fun game"). New collections (`wishlist_bids`, `gw_history`) should follow existing rule conventions; don't block PRs on hardening them.
- **`waiverPriority`** is written at `wc_leagues.py:102` (first member), `:161` (subsequent), surfaced at `:210`. Reuse it; don't invent a parallel ordering field.

---

## 10. How to run / validate locally

```bash
# Firestore emulator (database_id = gamedb), Flask on :5000, hosting on emulator
firebase emulators:start            # firestore :8080, auth :9099
.venv/bin/python -m fpl_predictor.app    # or however Flask is launched (see app entrypoint)
# Frontend: localhost uses Flask :5000 + emulators (firebase.jsx auto-detects)
```

Tests: backend unit tests under the repo's test dir; run with `.venv/bin/python -m pytest`. Each PR must add/extend tests per §8 acceptance criteria.

---

## 11. Open items to confirm with mentor/user during implementation

- **Auction rounds:** multi-round (default) vs single-pass — flag in PR 4 description for explicit sign-off.
- **`transfer_windows` audit doc:** keep as audit-only or delete entirely — implementer to recommend in PR 2.
- **Match duration constant** for computing `Tprev_end` (when is a match "ended"? kickoff + 120min to be safe for ET?) — pick a config value (`match_duration_minutes`, default ~150) and note it.
