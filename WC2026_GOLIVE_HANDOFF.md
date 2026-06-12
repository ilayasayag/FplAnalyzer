# WC 2026 Fantasy Draft — Live-Operations Handoff

> **Audience:** the next agent picking this up cold.
> **Written:** 2026-06-12 evening (validation session, post-PR #75). **Repo:** `/Users/ilay/RiderProjects/fpl_analyzer`.
> **Supersedes** the 2026-06-03 session-6 handoff (same filename — that doc predates PRs #10–#75 and the entire live-scoring era; its §§ about "draft readiness" are history now).
> **Every claim below was re-verified against live prod / git / GitHub on 2026-06-12 ~16:00–16:30 UTC** by a pickup-validation pass (Firestore reads via SA key, authed HTTP probes, Chrome UI walk-through, gh API).
>
> **Read first:** §0 (what changed since the old handoff), §2 (the league reality — the names are misleading), §3 (live-scoring architecture), §5 (watch items for tonight), §6 (gotchas).

---

## 0. TL;DR — where the project is NOW

The tournament is **live**. GW1 (Group Stage R1, Jun 11–14) is in progress. The draft happened; 6 friends have squads and locked lineups; two matches have been played and fully scored (player-level, itemized breakdowns, DefCon); the system scores matches automatically via two redundant schedulers + a self-healing catch-up watermark. The job is no longer "build & ship" — it is **operate, watch, and polish** through the final on 2026-07-19.

What changed vs the Jun 3 handoff (66 PRs):
- **PRs #10–#75 all merged.** Highlights: real kickoff times (#69), FWD→MID reclassification (#70), FIFA-aligned pool/squads (#71), draft-room hardening + rehearsal sandbox (#72), final-squad corrections + transactional picks (#73), **mobile retrofit of all 11 screens + remote scheduler** (#74), **self-healing catch-up watermark** (#75).
- **The real league is `lg_mock_draft` now** (yes, really — see §2).
- **A full live-scoring pipeline exists** (WhoScored/FIFA/ESPN ingest, per-player itemized breakdowns, DefCon, league live totals) — see §3.
- Captains remain REMOVED from the game (old handoff §4 still accurate on that).

---

## 1. ⏰ Operational calendar

- GW1 Group-R1 Jun 11–14 · GW2 Jun 18–22 · GW3 Jun 24–26 · GW4 (R32) Jun 28–Jul 4 · GW5 (R16) Jul 4–7 · GW6 (QF) Jul 9–12 · GW7 (SF) Jul 14–15 · GW8 (3rd+Final) Jul 18–19.
- League knockout: `knockoutStartGw=6`, `leaguePhaseGws=[1..5]`, 4 qualifiers → SF → Final ("Bracket seeded after GW5").
- Matches already played: **fixture 101 MEX 2–0 RSA** (Jun 11 19:00 UTC) and **fixture 102 KOR 2–1 CZE** (Jun 12 02:00 UTC) — both FT, `scoredFinal=true`, 31 playerScores each.
- Next up (UTC): **103 CAN–BIH Jun 12 19:00** (= 22:00 Israel), **104 USA–PAR Jun 13 01:00**, 105 QAT–SUI Jun 13 19:00, 106 BRA–MAR Jun 13 22:00.

---

## 2. ⚠️ THE LEAGUE REALITY (names are misleading — do not trust labels)

Verified in prod `gamedb` 2026-06-12:

| League id | Status | simulated | Members | What it actually is |
|---|---|---|---|---|
| **`lg_mock_draft`** | `group_phase`, currentGw=1 | **false** | **6: u_ilay, u_nadav, u_netanel, u_roy, u_shay, u_yuval** | **THE REAL FRIENDS LEAGUE.** Display name is still "WC 2026 Expert Mock Draft" — cosmetic leftover, user chose to keep for now. |
| `lg_pre_draft` | `pre_draft`, currentGw=None | false | 10 mixed (incl. 2 stranger gilbeni accounts) | Stale leftover from the pre-draft era. **User decision 2026-06-12: leave as is.** |
| `lg_draft_test` | `drafting` | true | same 6 friends | Draft rehearsal sandbox (PR #72). Leave as is. |

So: the original "Platform A mock / Platform B real (7 friends incl. Omer/Yonatan/Ido)" model is DEAD. The friend group is **6 managers** and they live in `lg_mock_draft`. Any code/scripts that filter on league id or `simulated` must treat `lg_mock_draft` as production data.

---

## 3. Live-scoring architecture (PRs #74–#75, the heart of operations)

### Data flow
1. **`fpl_predictor/data/wc_live_ingest.py`** — the engine.
   - `ingest_live(db, gw, date)` — FIFA + ESPN pass: writes per-fixture `playerScores` (with **itemized `breakdown` list** — Minutes/Goal/Assist/Shots/FIFA bonus/DefCon lines), updates fixture status/score, then `_recompute_live_scores()` writes `leagues/{lid}/scores/{gw}.results.{uid}.points` = Σ starters from the **locked lineup** (only for leagues in `group_phase`/`knockout`).
   - WhoScored path (full Opta stats incl. **DefCon** — defensive contribution, +2 at threshold) — **only works from residential IPs**. GCP is blocked by Incapsula (`whoscoredOk:false` on every cloud run — expected, not a bug). The FIFA cloud pass **preserves** any DefCon the Mac already wrote (read-merge, no clobbering).
   - `catch_up_scan(db, days_back)` — **the self-healing watermark** (PR #75): walks the last N days (default 3), scores every FINISHED fixture not yet bookmarked `scoredFinal=true`, bookmarks it, never re-touches bookmarked ones. Idempotent (verified: re-runs report `alreadyBookmarked`, score nothing). Every scheduler tick calls this, so downtime/redeploys never lose a match.
2. **Cron endpoint** — `POST/GET /api/v1/wc/cron/ingest-live-scores?key=<secret>` ([api_wc.py:3042](fpl_predictor/api_wc.py)). Secret lives at **`wc_config/cron` doc, field `secret`** in gamedb (read it with the SA key if you need to fire a tick manually). 401 without key (verified). Response shape: `{alreadyBookmarked, datesScanned, gw, liveUpdated, newlyFinalized, whoscoredOk}`.
3. **Finalization** is SEPARATE from live ingest: `finalize_gw` (engine) runs after a GW completes — writes `gw_history` snapshots, `standings/{gw}` + `standings/current`, official auto-subbed scores. Live ingest never finalizes.

### The two schedulers (redundant by design)
- **Cloud — GitHub Actions** `.github/workflows/wc-live-scores.yml` ("WC Live Scores"): cron `*/10 15-23 * * *` + `*/10 0-4 * * *` UTC + manual `workflow_dispatch`. Hits the cron endpoint with `secrets.WC_CRON_KEY`. Repo is public → free unlimited minutes. Delivers FIFA points only (no DefCon from GCP).
- **Mac — launchd** `~/Library/LaunchAgents/com.wc26.livescores.plist` → `scripts/run_ingest_cron.sh` → `scripts/ingest_live_scores.py`, every 600s + RunAtLoad, logs to `/tmp/wc_ingest.log` / `.err`. Adds WhoScored DefCon when the Mac is awake. Verified loaded and ticking (sleeps with the Mac, catches up on wake — by design).

---

## 4. ✅ VCS & DEPLOY REALITY (verified 2026-06-12)

| Question | Answer |
|---|---|
| `main` | `d046fd4` (= merge of PR #75). origin/main in sync. **0 open PRs.** |
| Deployed frontend | Hosting serves **`jsx?v=37`**; `dist/` is byte-identical to `draft_wc_design/` source for every .jsx/.css (verified file-by-file). **No drift.** |
| Deployed backend | The `api` function runs the PR #75 code — proven by firing a cron tick and getting the catch-up response shape. Frontend API calls now go **same-origin through the Hosting rewrite** (deliberate revert — see gotcha 4). |
| Worktrees | Main checkout sits on merged branch `live-catchup-watermark` (should `git checkout main && git pull`). ~20 `.claude/worktrees/*` exist; 12 locked `agent-*` ones are from past mentored-agent sprints — cleanup candidates, not load-bearing. |
| Untracked in main repo | `WC2026_GOLIVE_HANDOFF.md` (the STALE Jun-3 one — delete after this PR merges, or `git pull` will refuse the checkout), `fifa_fantasy_squads/`, `fifa_live_sync.py`, `wc_draft_analysis.html`, `wc_non_squad_players.html`, `"gws-group stage.pages"` — scratch artifacts, never committed. |

---

## 5. 🔭 WATCH ITEMS (the actual open work, in priority order)

1. **GitHub Actions cron has never fired on schedule.** As of 16:22 UTC Jun 12 (82 min into its first-ever window) there were **0 scheduled runs** — only the morning's manual dispatch (success). Workflow state is `active`; likely first-day schedule-registration lag, but UNPROVEN. The schedule fires every 10 min regardless of whether games are on (the endpoint no-ops safely), so **if `gh run list --workflow wc-live-scores.yml` still shows no `schedule` runs after the CAN–BIH window (22:00+ Israel, Jun 12), the cloud leg is broken** → fire `gh workflow run wc-live-scores.yml` manually during match windows and consider Cloud Scheduler (blocked on user running `gcloud auth login` with the owner account). Safety net either way: Mac agent + catch-up watermark guarantee no match is permanently lost.
2. **Intermittent "DEMO DATA — backend not reached" banner on prod.** Reproduced twice during validation, then disappeared. Root cause: the heavy `/players` read through the Hosting rewrite has 2.2–11.4s tail latency (8/8 authed probes succeeded but the worst was a hair under the frontend's 12s timeout); when the first attempt aborts, `loadInitialData` can fall back to the 91-player demo set even though retries exist. A reload fixes it. Watch on match night under real load; options if it worsens: longer `timeoutMs` for the initial load, eager retry-with-banner-refresh, or investigating why warm responses aren't ~0.3s (TTL-cache misses across instances?).
3. **Logged cosmetic UI bugs (user: "log now, talk later"):**
   - Hardcoded gold **"Knockout Phase"** pill on the League screen while the league is in `group_phase` — `draft_wc_design/screens-data.jsx:380`.
   - Sidebar Transfer Window card shows mock **"W— · The Big One / Closes —"** — the "· The Big One" suffix is hardcoded and `activeWindow.number/closesAt` are missing — `draft_wc_design/shell.jsx:313-318` (mock cousin at `data.jsx:327`).
   - **League → Standings table renders completely empty** until the first `finalize_gw` writes `standings/` docs (none exist yet — expected pre-finalize, but 0-pt member rows would look less broken).
   - Knockout screen label inconsistency: header badge says "GW6 · SEMI-FINALS" while the bracket columns say "SEMI-FINALS · GW7 / FINAL · GW8" (league has `knockoutStartGw=6`). Verify which is right before fixing.
4. **First `finalize_gw` for GW1** happens after Jun 14 — that's when `gw_history` snapshots, standings docs, and official (auto-subbed) scores first appear. The Points screen's console error `Failed to fetch gw-history snapshot` (404) is EXPECTED until then — the route exists ([api_wc.py:1533](fpl_predictor/api_wc.py)), the snapshot just isn't written yet. Confirm the GW1 finalize path runs (who triggers it — check before Jun 14!).
5. **Mac agent stderr noise:** `/tmp/wc_ingest.err` contains `gcloud auth print-access-token` failures + a few Firestore 403 tracebacks (last at 15:23 UTC). The agent's scoring ticks succeed regardless (log lines healthy through 15:44+). Transient/auth-fallback noise — investigate only if scoring stops.
6. **Post-tournament (after Jul 19):** revert `min_instances=1` → 0 in `functions/main.py` (~$5–15/mo), disable/delete the GH Actions workflow + launchd agent.

### Verified-good this session (don't re-litigate)
- Both played fixtures scored correctly end to end: Firestore playerScores ↔ UI Standout XI ↔ player popup breakdown all agree (Hwang In-Beom 13 = 2+5+3+1+2, DefCon line "5/12 → 0" rendered).
- `scores/1` all-zeros for the 6 managers is **CORRECT** — replicated the engine's computation: no manager's locked GW1 lineup contains any of the 62 scored players (nobody started MEX/RSA/KOR/CZE).
- Cron endpoint secret-gated (401 bare), hosting 200, API auth-gated (401 unauth), fixtures panel matches DB (scores, local kickoff times), Points pitch view renders the real squad, Knockout bracket placeholder sane, mobile CSS ships (v=5 files load).
- Catch-up watermark idempotency: a live cron tick returned `alreadyBookmarked:2`, scored nothing twice.

---

## 6. ⚠️ GOTCHAS (carried forward + new)

1. **API prefix is `/api/v1/wc`**; leagues live in collection `leagues` (not `wc_leagues`); DB is named **`gamedb`** (`(default)` is divergent/empty — never write there; emulator scripts need `FIRESTORE_DB_ID=gamedb` or explicit `database_id`).
2. **`dist/` is a separate gitignored copy** — edit `draft_wc_design/*.jsx`, `cp` to `dist/`, bump `jsx?v=N` in `dist/index.html` (currently **v=37**), `firebase deploy --only hosting`. Babel-in-browser: one JSX syntax error white-screens everything — compile-check first.
3. **Captains are GONE** (scoring applies no captain bonus; `_recompute_live_scores` still has a vestigial captain-doubling branch that's inert because lineups have `captain=None`). Don't reintroduce; keep frontend/backend deploys in lockstep.
4. **Frontend API calls are same-origin through the Hosting rewrite — DELIBERATELY** ([firebase.jsx:55-64](draft_wc_design/firebase.jsx)). The direct Cloud Run URL was reverted because privacy browsers / tracking prevention silently kill cross-origin fetches ("squads disappear" bug). Don't flip it back without solving that; the cost is the tail-latency issue in §5.2.
5. **Two `gh` accounts:** repo owner **`ilayasayag`** (push rights); default-active `ilay-asayag` is read-only. Push/merge: `gh auth switch --user ilayasayag` → do the thing → switch back.
6. **Never push to `main`** — branch → PR → squash-merge, always (CLAUDE.md). After squash-merges, branch off fresh `main`.
7. **Secrets:** never commit `secrets.json` / any `*service-account*.json`. SA key (full admin): `/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json` (outside repo). Cron secret: `wc_config/cron.secret` in gamedb + GitHub secret `WC_CRON_KEY`. Web API key in `firebase.jsx`. Prod test-token mint: SA custom token for uid `zeOCZ6LdZsa7k18VuGknyhcs3x73` → Identity Toolkit `signInWithCustomToken`.
8. **`test_simulation.py` wipes the emulator**; reseed after. Use `.venv/bin/python` for everything (bare python lacks firebase_admin).
9. **WhoScored from datacenter IPs = blocked** (Incapsula). `whoscoredOk:false` from the cloud is normal. DefCon only flows from the Mac (or a future residential proxy).
10. **Security rules remain loose on `leagues`/`lineups`** (any authed user can write) — user accepted ("just a fun game"). Squads/draft/trades/scores are server-only.
11. The frontend Firestore compat SDK opens a realtime Listen channel against `(default)` — it's unused for data (draft room polls `/draft/state` over HTTP); ignore it in network traces.
12. **Netanel rule** (CLAUDE.md): if the active user is Netanel, preface every substantive answer with the exact line "Netanel, if Frida can do it then so can you." — see CLAUDE.md for the trigger signals.

---

## 7. HOW TO RUN / VALIDATE

```bash
cd /Users/ilay/RiderProjects/fpl_analyzer

# Local stack
firebase emulators:start --only firestore,auth,ui          # :8080 / :9099 / :4000
FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FPL_TESTING=true \
  .venv/bin/python run_server.py                            # Flask :5000
python3 -m http.server 8897 --directory dist                # frontend

# Prod checks (read-only)
gh run list --workflow wc-live-scores.yml --limit 10        # has the schedule fired?
tail -5 /tmp/wc_ingest.log                                  # Mac agent ticking?
curl -s -o /dev/null -w '%{http_code}\n' https://fpl-analyzer-792eb.web.app/   # 200
# Fire one scoring tick manually (idempotent — safe):
#   read secret from wc_config/cron in gamedb (SA key), then
#   curl -X POST "https://fpl-analyzer-792eb.web.app/api/v1/wc/cron/ingest-live-scores?key=$KEY"
# Firestore ground truth (SA key): wc_fixtures status/scoredFinal, leagues/lg_mock_draft scores/standings
```

---

## 8. REFERENCE

- `WC2026_PLAN.md` — rules/schema (note: captains removed since).
- `CLAUDE.md` — repo rules for Claude (PR-only, Netanel preface, gamedb, secrets).
- `NETANEL_GUIDE.md` — contributor onboarding.
- Auto-memory: `~/.claude/projects/-Users-ilay-RiderProjects-fpl-analyzer/memory/project_wc2026.md`.
- Old handoffs (`SPRINT_FIXIT_HANDOFF.md`, `S1_REVIEW_HANDOFF.md`) — historical only.
- Next agent: run the **pickup-handoff** skill against THIS doc before acting; the highest-value first check is §5.1 (did the GH cron ever fire on schedule?).
