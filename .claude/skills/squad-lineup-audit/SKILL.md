---
name: squad-lineup-audit
description: Read-only integrity check that every WC2026 manager's gameweek lineup is consistent with their squad. Use when the user says "audit the squads", "are the lineups aligned with the gw", "check everyone's lineup", "squad lineup audit", before locking a GW, or after free-agent/wishlist/trade activity. Catches the stale-lineup class (a dropped player dangling in the lineup, a new player missing — e.g. Vargas/Leão), bad formations, missing/extra players, blocked-team starters, and post-lock edits. Reports per manager; proposes a fix and applies it only after explicit confirmation.
---

# Squad ↔ lineup audit (read-only; fixes only on confirm)

Free-agent / wishlist swaps update the **squad** (`players`) but NOT the **lineup**
doc — so a dropped player can dangle in the lineup and the new one go missing (the
Vargas/Leão bug, `memory/lineup-lock-override-and-pickblock.md`). This catches that
class in one pass, for every manager.

## Step 0 — Ground rules
- `.venv/bin/python`; prod `gamedb` via firebase-adminsdk SA token:
  `export WC_TOKEN=$(gcloud auth print-access-token --account=firebase-adminsdk-fbsvc@fpl-analyzer-792eb.iam.gserviceaccount.com)`
- League `lg_mock_draft` (parameterize `lid`). Times in Israel (IDT).

## Step 1 — Run the audit (read-only)
For each member's `lineups/{uid}_{gw}` vs their `squads/{uid}.players`, assert:

| Check | Asserts |
|---|---|
| **lineup ⊆ squad** | every starting+bench player is currently OWNED (no dangling dropped players) |
| **squad ⊆ lineup** | every owned player is in the lineup (no missing new pickups) |
| **counts** | exactly 11 starters + 4 bench = the 15-man squad, no dupes |
| **formation** | 1 GK + ≥3 DEF + ≥2 MID + ≥1 FWD; `bench[0]` is the reserve GK |
| **pick blocklist** | no `leagues/{lid}.pickBlockByGw[gw]` player is in the STARTING XI |
| **carry-forward** | a manager with no `{uid}_{gw}` doc would carry forward their last GW's XI (finalize handles this since PR #105) — flag who has none |

Inline pattern (one Firestore client; print PASS/MISMATCH per manager + the exact diff with player names):
```python
squad = {p["playerId"] for p in squad_doc["players"]}
ln = lineup_doc; lineup = set(ln["starting"]) | set(ln["bench"])
unowned = [p for p in lineup if p not in squad]        # dangling — bug
missing = [p for p in squad if p not in lineup]         # new pickup not placed
blocked_starting = [p for p in ln["starting"] if p in pickBlock]
```

## Step 2 — Post-lock / fairness check (STRICT)
If `gw` is already locked (`is_lineup_locked(db, gw, lid=lid)` — honours `lineupLockOverride`),
flag ANY lineup that changed after the lock. For a proposed fix to a LOCKED lineup,
**verify the swapped-in and swapped-out players have NOT kicked off** (their team's
GW fixture `kickoff > now`, `status == "NS"`) before allowing it.

## Step 3 — Propose + apply fixes (CONFIRM each)
For a stale lineup, the canonical fix is **replace the dangling (unowned) player with
the missing (owned) one in place** (same slot — usually bench; XI unchanged), so the
lineup again equals the 15-man squad. Show the before/after, then on the user's OK:
```python
ref.update({"starting": new_start, "bench": new_bench, "formation": form})
```
Re-run Step 1 to confirm all managers are `OK`. Never change a player's start/bench
status beyond the minimal swap unless asked.

## Output
A one-line-per-manager table (`OK` / `MISMATCH` + diff), a summary count, and — when
anything was fixed — the re-verified all-clear. Pure read-only unless a fix is confirmed.
