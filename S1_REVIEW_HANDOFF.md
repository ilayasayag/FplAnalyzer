# S1 Review & Validation Packet — for the review agent

**Scope:** Segment **S1 — Scoring snapshot & Points panel** (tickets #50 / #52 / #47).
**Branch / PR:** `fix/s1-scoring-snapshot` → **PR #54** (base `main`).
**Author:** previous session (Opus). **Status:** code complete, tests green, **NOT deployed, NOT browser-verified.**

> Your job: code-review the diff below, then run the live validation checklist. Nothing here has
> been exercised in a browser yet — the backend change has a unit test, the frontend change is
> reasoned-but-unverified. Treat both as "claimed correct," not "confirmed."

---

## 0. Baseline state you're starting from (verified this session)

- **PR #42 was reviewed + squash-merged to `main`** (`1753aab`). `main` now matches the deployed prod
  build — the prior "deployed-but-unmerged drift" is resolved.
- **No deploy happened this session.** Prod hosting is still `?v=34`; the `api` Cloud Function is
  unchanged. Prod already ran #42's code before the merge.
- Test suite baseline after #42: **160 passing**. After S1: **162 passing** (160 + 2 new).
- Prod mock league `lg_mock_draft` (8 managers; human test acct `netanel@wc2026.local` / uid
  `u_netanel`, admin) drifts as people sim — use the admin Tweaks panel (⚙ bottom-right) "Reset mock
  to GW1" / "Simulate next GW" for a clean state.

---

## 1. What changed (the diff to review)

Run: `git diff main..fix/s1-scoring-snapshot`

| File | Change | Ticket |
|---|---|---|
| `draft_wc_design/components.jsx` | `PlayerSlot` points-mode display: removed the `GW3_POINTS[playerId]` (season-total) fallback → now `points != null ? points : 0`. Updated the `ptsOf` comment in `Pitch`. | #52 |
| `fpl_predictor/api_wc.py` | `get_player_scores`: join each `playerScores` doc to its parent fixture → set `opponent`; drop orphan scores (fixture deleted); collapse to one row per GW. | #47 |
| `test_helpers.py` | Fake DB: added `_Doc.parent` and `_Coll.parent` so `snap.reference.parent.parent` (collection-group → parent-doc) is testable. | (test infra) |
| `test_player_scores_endpoint.py` | **New.** Route-level test: opponent join (home/away both directions), orphan-drop, per-GW dedup, empty case. | #47 |

### #52 — VT-PointsNoStats (rationale to verify)
The points `Pitch` (`screens-status.jsx:465`) is the **only** `mode="points"` caller and it always passes
`pointsById={gwPointsById}` (built from the `gw_history` snapshot). So when a player has no snapshot
entry (didn't feature that GW), the old `GW3_POINTS[playerId]` fallback surfaced their **season total**.
Fix shows **0** instead. **Reviewer check:** confirm there is no other `mode="points"` Pitch that
*relied* on the season-total fallback (grep `<Pitch` — there are 2 usages; the other is `mode="pick"`).

### #47 — VT-106 (rationale to verify)
Opponent = the side of the parent fixture whose team id ≠ the player's `teamId` (read from
`wc_players/{id}`). Orphan `playerScores` (whose `wc_fixtures/{fid}` doc was deleted) are skipped, which
also removes the duplicate-GW1 rows the modal showed. **Reviewer check:** the parent-walk
`d.reference.parent.parent` is `wc_fixtures/{fid}` in real Firestore — confirm against the live client,
and confirm fixtures actually carry `homeTeam.id` / `awayTeam.id` + `isoCode` (they do via
`_write_fixture`, lines ~424-425, and `_enrich_fixtures_with_iso`).

### #50 — VT-PointsLock (no code change)
Claimed **already closed by PR #42**: `_snapshot_gw_history` freezes the locked `starting`/`bench`/
`autoSubs`, and `PointsScreen` renders a finished GW from that snapshot (not the mutable lineup doc).
`starting`/`bench` are disjoint so no per-manager dup. **Reviewer check:** validate behaviorally (below).

---

## 2. Run the tests (must stay green)

```bash
# from the worktree root; venv lives in the MAIN repo
PYTHONPATH=. /Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python -m pytest -q
# expect: 162 passed
```

---

## 3. Live validation checklist (NOT yet done — please do)

Deploy is required to see #52/#47/#50 in the browser. Deploy steps (touches prod hosting):

```bash
# frontend: babel-in-browser, no build — copy changed jsx to dist/, bump ?v=N in dist/index.html
cp draft_wc_design/components.jsx dist/   # (+ any other changed jsx)
# edit dist/index.html: ?v=34 -> ?v=35
firebase deploy --only hosting
# backend (for #47): predeploy copies fpl_predictor/ into functions/
firebase deploy --only functions:api
```

Then, signed in as an admin on https://fpl-analyzer-792eb.web.app/ , with `lg_mock_draft` simmed to at
least GW2 (Tweaks ⚙ → "Simulate next GW"):

- [ ] **#52** — Points tab, step back to a **finished** GW. A player who did **not** feature (0 minutes,
      no snapshot entry) shows **0 PTS**, not a large season-total number. Cross-check the squad total
      (gold box) equals Σ starter points + captain bonus.
- [ ] **#50** — On that finished GW, the pitch shows the squad **as it was locked** for that GW (do a
      free-agent/trade move first, then re-open the past GW — the swapped-in player must **not** appear).
- [ ] **#47** — Open a player's stats modal → History tab. The **OPPONENT** column shows a real nation
      (e.g. `ECU`), not `—`, and there is exactly **one row per GW** (no duplicate GW1).
- [ ] Regression: live (current) GW Points still renders; List View matches Pitch View.

Report any mismatch back on PR #54 with the manager/GW/player you used.

---

## 4. Open follow-ups (out of S1 scope — for later segments)

- `_GOAL_WEIGHTS` (`fpl_predictor/seed/wc_simulator.py:54`) is **dead code** after PR #42's scoreline
  rework — safe to delete in a hygiene pass.
- Next segments per `WC2026_TICKET_SEGMENTS.md`: **S2** (#48/#53 standings), then **S3/S4/S6**, then
  **S5**. S2 should branch off `main` after #54 merges.
