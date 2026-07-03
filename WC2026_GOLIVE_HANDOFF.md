# WC 2026 Fantasy Draft — Go-Live Handoff

> **Audience:** the next agent picking this up cold.
> **Written:** 2026-06-03 (session 6). **Repo:** `/Users/ilay/RiderProjects/fpl_analyzer`. **Branch:** `main` (clean).
> **Author note:** written by an agent at the end of session 6 (PR #9 review-fixes + deploy). **Supersedes** the 2026-06-02 session-5 handoff (same filename — session-5 content rolled into §3). `WC2026_PLAN.md` remains authoritative for *rules & schema*.
>
> **Read first:** §0 (mission), §1 (deadline), §2 (VCS/deploy reality — CLEAN this session, no drift), §4 (what session 6 did — captains removed + DB-sync tool + deploy), §5 (gotchas).

---

## 0. TL;DR — what this project is

A private **FIFA World Cup 2026 fantasy snake-draft** app for a 7-person friend group, built on an existing FPL-draft codebase (Flask + Firestore + vanilla-React/Babel-in-browser frontend) adapted to WC data from api-sports.io.

Two leagues live side by side in the same Firestore (`leagues` collection in the `gamedb` database):

- **Platform A — `lg_mock_draft`**: finished, fully-simulated showcase season (8 managers, knockout). `simulated: true`, status `knockout`, admin `u_mk_golden`. Exists to click around a "complete" season.
- **Platform B — `lg_pre_draft`**: **the real product** — 7 friends, status `pre_draft`, **draft NOT yet run.** `simulated: false`, admin `u_netanel`.

**The whole job: run Platform B's draft on 2026-06-06 20:00 IDT, get all 7 squads locked before GW1 locks 2026-06-11 17:00 UTC.** Sessions 5–6 were UX/polish + contributor-PR integration (still pre-draft) — not on the deadline critical path, but user-facing and now live.

---

## 1. ⏰ THE DEADLINE

- **GW1 locks `2026-06-11 17:00 UTC`.** The 7-friend draft must be complete and squads locked before then.
- **Real draft scheduled: `2026-06-06 20:00 Israel time` (= 17:00 UTC).** ~3 days of buffer from today (2026-06-03).
- **Mock auto-run** slot passed; mock is `knockout`. User said "fine for now." Not on the critical path.

Tournament calendar (live from `GET /api/v1/wc/gameweeks`): GW1 Group-R1 06-11 · GW2 Group-R2 06-16 · GW3 Group-R3 06-22 · GW4 R32 06-27 · GW5 R16 07-05 · GW6 QF 07-10 · GW7 SF 07-14 · GW8 Final 07-18 (all lock 17:00 UTC).

---

## 2. ✅ VCS & DEPLOY REALITY — CLEAN (no drift this session)

Unlike session 5 (which ended with 3 deployed-but-unmerged commits on an open PR), session 6 ends **fully reconciled**: everything that is deployed is also merged to `main`.

| Question | Answer |
|---|---|
| **Committed?** | ✅ Yes. `main` = `b834c1e`. Working tree clean except `?? WC2026_GOLIVE_HANDOFF.md` (this file). |
| **Pushed to origin?** | ✅ Yes. `main` is in sync with `origin/main` (0 ahead / 0 behind). |
| **Merged to `main`?** | ✅ Yes. PRs #8 and #9 both squash-merged. No open feature PRs. |
| **Deployed to prod?** | ✅ Yes — **hosting AND functions this session.** Hosting at `jsx?v=21`; `api` function (v2) redeployed. Both verified by `curl`. |

> ✅ **No outstanding drift.** `main` (`b834c1e`) is the single source of truth and matches prod. The session-5 drift (PR #8) was resolved by merging it at the start of this session.

### Commit timeline (default branch `main`)

| SHA | Message |
|---|---|
| `b834c1e` | Netanel PR #4 rebased onto main + review fixes (dev-gate Tweaks, complete DB export/import) (#9) |
| `950cae1` | UX fixes: DR→Pos, player stats popup, manager squad view, propose trade modal (#8) |
| `e1dfb04` | Fix mock league orphaning real users on reseed (#7) |
| `8a69b79` | Draft Room watchlist persist + drag-reorder (#6) |
| `83d574c` | Draft Tab watchlist/auto-pick UI (#5) |
| `62043e7` `5d68356` `7eb2905` | Auto-pick on timer (#3); admin→u_netanel (#2); go-live (#1) |

---

## 3. What happened BEFORE this session (sessions 1–5 recap)

- **Sessions 1–3 (prod-fix phase):** built lobby/platform-selector, Nation filter, backend team metadata; fixed dead prod (api repointed off `gamedb` to empty `(default)`) via env-driven `database_id`; reseeded gamedb (1386 players, 48 teams, 48 fixtures, 2 leagues); fixed `/players` timeout (TTL cache + retry + `min_instances=1` + direct Cloud Run URL).
- **Session 4 (go-live + draft readiness):** VCS-backed prod-fix drift (PR #1). Change Password modal. 7 prod friend accounts. `test_draft_bot.py` (24 checks). Fixed 2 P0 prod bugs. `lg_pre_draft` admin `u_roy`→`u_netanel` (PR #2). Auto-pick on timer (PR #3). Wrote `NETANEL_GUIDE.md` + `CLAUDE.md`. PR #7 merged.
- **Session 5 (UX-polish sprint):** 4 UX features — DR→Position everywhere (incl. pitch), player stats popup (History/Fixtures tabs), manager squad modal, working Propose Trade. Shipped as PR #8, **deployed to prod (v=20) but left UNMERGED** — the drift that session 6 opened by resolving.

---

## 4. What THIS session (6) did — merge reconciliation + contributor PR + deploy

### 4a. Resolved session-5 drift
Merged **PR #8** (the session-5 UX work) into `main` → `950cae1`. Prod had been serving v=20 from an unmerged branch; this realigned `main` with prod.

### 4b. Integrated Netanel's contributor PR (#4 → reworked as #9)
Netanel's PR #4 (branch `NetanelVinter:Netanel`) was branched off **pre-#8 main** and never rebased, so merging it directly would have caused drift. Instead: created `fix/pr4-review-fixes` off current `main`, **merged his branch in** (conflict-free — verified the one `components.jsx` overlap with #8 merges correctly, keeping the DR→Position display), code-reviewed it, **added review fixes**, and shipped as **PR #9** (`b834c1e`). **Closed PR #4** as superseded.

What #9 contains (Netanel's work + fixes):
1. **Captains/vice-captains REMOVED from the game** (end-to-end, his change): `wc_scoring.resolve_captain_bonus` returns `(None, 0)`; `wc_squads.set_lineup` makes captain/vice optional + drops all captain validation; `_default_lineup`/`_get_previous_lineup`/`seed_league` set them `None`; frontend stops sending/displaying captain. Verified no broken references.
2. **Dev-only DB export/import tool** (his feature + my fixes) — "Database Sync" section in the Tweaks panel: a "Connect to Prod DB" toggle (localStorage `firebase_use_prod`), "Export Prod DB to File", and import-JSON-into-emulator. See §5 gotcha 18.
3. **Tweaks panel triggers** (his feature + my fix): auto-open, Ctrl+M, floating ⚙️ button — now **gated to localhost only** (my fix; see 4c).
4. CORS broadened (`r"/api/.*"`); `leagueDetails?.` null-safety.

### 4c. Review fixes I added on top of Netanel's work
- 🔴 **Dev-gated the Tweaks debug panel** (`tweaks-panel.jsx`). His version made it auto-open in prod for ALL users (incl. the "Export Prod DB" button) because the open default was `window === window.top`. Now auto-open, Ctrl+M, and the ⚙️ trigger are gated to `localhost`/`127.0.0.1`; the panel is fully hidden in prod. The design-tool host path (`__activate_edit_mode` postMessage) is unaffected.
- 🟠 **Completed the export** (`firebase.jsx`). Rewrote with a recursive subcollection spec so the `leagues/<id>/draft/<gw>/picks` nesting (silently dropped before) round-trips. Works for BOTH leagues (iterates every `leagues` doc).
- 🟡 **Batched the import** — flatten + commit in batches of 500 instead of one awaited write per doc; handles nesting.

### 4d. Deployed BOTH hosting and functions
- **Why functions too (not hosting-only):** captain removal couples frontend↔backend. The new frontend stops sending `captain` on lineup save; the *old* prod backend's `set_lineup` still *required* it → a hosting-only deploy would have broken lineup saving. Deploying `functions:api` shipped the matching backend (captain now optional).
- Synced all source `.jsx` → `dist/`, bumped `jsx?v=20` → **`v=21`**, ran `firebase deploy --only hosting,functions:api`. Verified: hosting serves `v=21` (200), `api` v2 redeployed, `/teams` → 401 (auth-gated, alive).

### 4e. Left as-is per user decision
- **Security rules gap** (pre-existing, NOT introduced this session): `leagues/{id}` `allow update` and `lineups` `allow write` are `if request.auth != null` with no owner/member scoping → any authed user could overwrite another's lineup or the league doc via the raw client SDK. User said "it's just a fun game" — **deliberately not tightened.** Logged here for visibility.

---

## 5. ⚠️ GOTCHAS (carried forward + new)

1. **API prefix is `/api/v1/wc`**, not `/api/wc` (`api.py`).
2. **Leagues live in collection `leagues`**, not `wc_leagues`. Members are a subcollection.
3. **Red "DEMO DATA — backend not reached" banner** = `__DATA_SOURCE__ === "down"` → silent fallback to the 91-player demo set. Causes: backend unreachable, or a JS error in `loadInitialData`.
4. **Babel-in-browser is unforgiving:** a JSX syntax error white-screens the WHOLE app (no build step). Compile-check before deploy (`@babel/standalone` + `preset-react` transform in `/tmp` — done this session, all OK). `let`/`const` stay block-scoped.
5. **`dist/` is a SEPARATE, gitignored copy.** Editing `draft_wc_design/*.jsx` does nothing in prod until you `cp` to `dist/`. Cache-bust `jsx?v=N` in `dist/index.html` (currently **v=21**, 12 scripts). To find live version: `curl -s https://fpl-analyzer-792eb.web.app/index.html | grep -o 'jsx?v=[0-9]*'`.
6. **JS object keys coerce to strings** — `PLAYER_MAP[42] === PLAYER_MAP["42"]`. The `/squads` API returns player **objects**, not IDs — always `.map(p => String(p.playerId))`.
7. **Hosting `/api/**` rewrite is unreliable for large reads** — frontend calls the **direct Cloud Run URL** `https://api-4anrfyrdxa-uc.a.run.app`. Don't revert to relative paths.
8. **`min_instances=1` on the `api` function** — ~$5-15/mo while live. Revert to `0` post-tournament (after 2026-07-18) in `functions/main.py`.
9. **Emulator multi-DB IS divergent.** `firestore.client()` (`(default)`) and `firestore.client(database_id="gamedb")` are separate stores. Always pass `database_id="gamedb"` (or `FIRESTORE_DB_ID=gamedb`) for local scripts.
10. **`test_simulation.py` wipes the emulator** — re-seed with `populate_emulator_real_squads.py` afterward.
11. **Two `gh` accounts:** repo owned by **`ilayasayag`** (push rights); default-active is **`ilay-asayag`** (read-only → 403 on push). To push/merge: `gh auth switch --user ilayasayag`, do the thing, **switch back** to `ilay-asayag`. (Followed this session for the #9 merge, #4 close, and push.)
12. **Never push directly to `main`** (CLAUDE.md rule) — always branch → PR.
13. **Squash-merge creates divergent history.** After a squash-merge, start the next branch off fresh `git checkout main && git pull origin main`. **This is exactly what bit Netanel's PR #4** — he branched off old main and never rebased; we had to rebase-via-merge into #9.
14. **Stale worktrees** at `/private/tmp/wc_branch` (@0979427) and `/private/tmp/wc_design` (@7f82653) — old detached-HEAD builds, safe-to-remove. There is also a Claude worktree at `.claude/worktrees/jolly-mclean-84f928` (@e1dfb04, branch `claude/jolly-mclean-84f928`) used this session.
15. **SA key** (full Firebase admin) at `/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json` — outside the repo; never commit. Never commit `secrets.json` or any `*service-account*.json`.
16. **Engine randomises draft order at `/draft/start`** (`draft.py` `random.shuffle`). Seeded `draftPosition` is cosmetic until the draft starts. User confirmed random-is-fair.
17. **The `DR` text is legit in two places — leave them:** the draft-room column (`screens-draft.jsx`, sorted by draft rank) and the "FDR" fixture-difficulty acronym. Only the player-row/pitch DR was the confusing one (removed in #8).
18. **🆕 Captains are GONE from the game.** Scoring applies no captain bonus; `set_lineup` no longer requires/validates captain; seed + default lineups use `None`. **Do not re-introduce captain doubling** — it's an intentional rules decision (user confirmed "we don't have captains"). The frontend↔backend versions must stay in lockstep: never deploy a captain-related frontend change to hosting without the matching `functions:api` deploy.
19. **🆕 DB-sync tool is DEV-ONLY (localhost).** The Tweaks panel (and its "Export Prod DB" button) is gated to `localhost`/`127.0.0.1` and hidden in prod. Export reads only client-readable collections (`wc_config/teams/players/fixtures+playerScores`, `leagues` + subcols incl. `draft/picks`). It **cannot** export `users` (per-owner read), `wc_gameweeks`, or `wc_group_standings` (no client read rule). **It is NOT a backup** — for real backups use `gcloud firestore export` / `firebase emulators:export`.
20. **🆕 Browser IMPORT is blocked by rules for server-only collections.** The import writes via the client SDK, so a rules-enforcing emulator rejects `squads`/`draft`/`trades`/`scores`/`waivers`/`standings`/`wc_*` (all `write:false`), and because writes are batched (atomic per 500), one denied doc fails the whole batch. To actually seed an emulator: run it with open rules, OR use `populate_emulator_real_squads.py` (writes as admin, bypasses rules). **Decision still open — see §10.**
21. **🆕 Security rules let any authed user write `leagues`/`lineups`** (no owner check). Left as-is per user ("just a fun game"). Squads/draft/trades/scores ARE server-only and protected.

---

## 6. ARCHITECTURE MAP

```
fpl_predictor/
  api.py                ← Flask entry (also Cloud Function entry). db = firestore.client(
                          database_id=os.environ.get("FIRESTORE_DB_ID","gamedb"))
                          CORS now r"/api/.*" + r"/api/*".
  api_wc.py             ← All /api/v1/wc/* routes
                          - /leagues/<lid>/squads/<target_uid> GET → squad.players is array of
                            OBJECTS {playerId,position,...}, not IDs
                          - /leagues/<lid>/lineup/<gw> PUT → set_lineup(..., captain=body.get("captain"),
                            vice_captain=...) — both now Optional/None (captains removed)
                          - /leagues/<lid>/trades POST; /draft/{state,start,pick,auto-pick,watchlist}
  game/
    draft.py            ← Snake draft engine (idempotency_key; shuffles order at start)
    wc_scoring.py       ← Points calc. resolve_captain_bonus() now returns (None,0) — DISABLED.
    wc_knockout.py      ← Bracket seeding + advancement
    wc_leagues.py       ← League CRUD
    wc_squads.py        ← Squad CRUD; set_lineup captain/vice Optional, no captain validation
  data/wc_api.py        ← WC2026Client: api-sports.io + Firestore cache (300s TTL + retry)
  seed/seed_league.py   ← Canonical seeding (admin default u_netanel; lineups captain=None)

functions/main.py       ← Firebase Function wrapper, @https_fn.on_request(min_instances=1)

draft_wc_design/        ← Frontend SOURCE (.jsx, in-browser Babel). MUST cp to dist/ to take effect.
  app.jsx               ← Top-level App. window.* globals (PLAYER_MAP string-keyed, etc.).
                          Mounts <PlayerStatsModal/> + <TweaksPanel/> (~899, with the Database Sync section).
  firebase.jsx          ← Firebase init + apiCall(). _useProd toggle (localStorage firebase_use_prod).
                          exportFirestore()/importFirestore() (dev-only DB sync; recursive + batched).
  shell.jsx             ← TopBar, SubNav, ChangePasswordModal.
  screens-draft.jsx     ← Draft Room. Countdown + auto-pick watchdog. DR column is LEGIT.
  screens-data.jsx      ← Player Browser, Schedule/Results, Trades + ManagerSquadModal + ProposeTradeModal.
  screens-bracket.jsx   ← Free Agents / Waivers / My Squad / Draft tabs (DR→pos, clickable names).
  screens-status.jsx    ← Points + Pick Team screens. Captain UI/state removed.
  player-stats-modal.jsx← Overview/History/Fixtures tabs.
  components.jsx        ← PlayerSlot (pitch): mode==="pick" shows POS_NAMES[p.pos]; captain props removed.
  tweaks-panel.jsx     ← TweaksPanel — DEV-ONLY (gated to localhost). Auto-open/Ctrl+M/⚙️ trigger.

dist/                   ← Built frontend, gitignored. firebase deploy --only hosting serves this.
                          Currently jsx?v=21. Keep in sync with draft_wc_design/ (cp foo.jsx).

test_draft_bot.py       ← 24-check live-HTTP draft test (LOCAL emulator only)
test_simulation.py      ← Full 8-GW sim. WIPES emulator. gamedb-targeted.
populate_emulator_real_squads.py / populate_production_real_squads.py ← seed (local / prod-destructive)
firestore.rules         ← Security rules (see gotchas 19–21). NEnforced by emulator + prod.
NETANEL_GUIDE.md · CLAUDE.md · WC2026_PLAN.md · WC2026_GOLIVE_HANDOFF.md (this file)
```

**Prod wiring:** Firestore project `fpl-analyzer-792eb`, named DB `gamedb` (region `nam5`; `(default)` is a divergent empty store — don't use). Cloud Function `api` (v2, us-central1, python313, `min_instances=1`) at `https://api-4anrfyrdxa-uc.a.run.app` (direct — what frontend uses). Hosting `https://fpl-analyzer-792eb.web.app` serves `dist/`.

---

## 7. HOW TO RUN / VALIDATE LOCALLY

```bash
cd /Users/ilay/RiderProjects/fpl_analyzer

# 1. Emulators (separate terminal)
firebase emulators:start --only firestore,auth,ui

# 2. Backend against emulators (separate terminal)
FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FPL_TESTING=true \
  .venv/bin/python run_server.py        # Flask :5000

# 3. Frontend static (separate terminal) — serves dist/
python3 -m http.server 8897 --directory dist   # http://localhost:8897

# 4. Seed emulator (after emulator starts; targets gamedb)
FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
  .venv/bin/python populate_emulator_real_squads.py

# 5. Bot test (24 checks; HTTP against local Flask)
.venv/bin/python test_draft_bot.py

# Frontend edit loop: edit draft_wc_design/X.jsx → cp to dist/ → bump jsx?v=N in dist/index.html
# Compile-check JSX before deploy:
#   cd /tmp && npm i @babel/standalone, then Babel.transform(file, {presets:["react"]})
# Deploy: firebase deploy --only hosting              (frontend only)
#         firebase deploy --only hosting,functions:api (when backend changed — e.g. captain coupling)
# Push:   gh auth switch --user ilayasayag && git push && gh auth switch --user ilay-asayag
```

**Use `.venv/bin/python`** (bare `python` lacks `firebase_admin`). SA key via `GOOGLE_APPLICATION_CREDENTIALS=/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json`. Web API key is in `firebase.jsx`.

---

## 8. STATUS BY AREA

### Missions / Sprints
- **Sprint 0 (Go-live foundation)** — ✅ DONE (session 4).
- **Sprint 1 (Draft dry-run + readiness)** — ✅ DONE (session 4). `test_draft_bot.py` 24/24.
- **Sprint 5 (UX polish)** — ✅ DONE + DEPLOYED + **MERGED** (PR #8, session 5; merged session 6).
- **Sprint 6 (Contributor PR + review fixes)** — ✅ DONE + DEPLOYED + MERGED (PR #9). Captains removed, dev-gated Tweaks panel, DB-sync tool. This session.
- **Sprint 2 (Real draft 2026-06-06 20:00 IDT)** — ⬜ scheduled event, not actionable code-wise.
- **Sprint 3 (in-tournament polish)** — ⬜ post-kickoff (Germany default flag, manager-flag display, US/Curaçao naming, delete `lobbytest_*` emulator accounts).

### PRs
- **#9 `b834c1e` MERGED** — Netanel #4 rebased + review fixes (this session).
- **#8 `950cae1` MERGED** — session-5 UX fixes (merged this session).
- **#4 CLOSED** — Netanel's original; superseded by #9.
- #7 `e1dfb04`, #6 `8a69b79`, #5 `83d574c`, #3 `62043e7`, #2 `5d68356`, #1 `7eb2905` — MERGED (sessions 1–5). No open PRs.

### Merges / Branches / Worktrees
- `main` at **`b834c1e`** — contains everything; matches prod. `origin/main` in sync.
- Local feature branches (`fix/pr4-review-fixes`, `feature/ux-fixes-*`, etc.) are merged/superseded — cleanup candidates.
- Worktrees: main repo `@b834c1e [main]`; `.claude/worktrees/jolly-mclean-84f928 @e1dfb04`; stale `/private/tmp/wc_branch`, `/private/tmp/wc_design`.

### Deployments — live
- **Hosting:** `https://fpl-analyzer-792eb.web.app` — **redeployed this session to `jsx?v=21`.** Verified 200.
- **`api` Cloud Function:** gen2, us-central1, python313, `min_instances=1`. **Redeployed this session** (captain-removal backend). `/teams` → 401 (auth-gated, alive — verified).

### Validations
- **Babel compile-check** of all touched `.jsx` — OK this session.
- **dist sync:** all 12 frontend `.jsx` `cp`'d to `dist/`; the 5 changed files `diff`-clean vs source (verified).
- **Merge correctness:** the `components.jsx` overlap between #8 and #9 verified to keep both the DR→Position display and the captain-prop removal.
- **Prod browser end-to-end:** ⚠️ **PENDING user manual pass.** Recommended (signed in, hard-refresh): (a) NO Tweaks/gear panel visible to a normal user; (b) Pick Team has no captain UI and a lineup saves without error; (c) the §9.1 session-5 checklist (stats popup, manager squad, propose trade). Not agent-verifiable without a user login.

---

## 9. THE PLAN — next steps

In priority order:

1. **User browser spot-check on prod** (v=21) — confirm Tweaks panel hidden for normal users + lineup save works without captain (the deploy-coupling path). See §8 Validations.
2. **Decide the import-vs-emulator-rules question** (§10 Q1) — leave as best-effort / run emulator with open rules / drop browser import in favor of `populate_emulator_real_squads.py`.
3. **Live draft dry-run** with the 7 friends before 06-06 (optional but recommended — only way to test auto-pick under real network).
4. **Draft-day runbook** (`DRAFT_DAY_RUNBOOK.md`) — pre-flight, mid-draft incident recipes, manual-pick path, rollback.
5. **Sprint 3 polish (post-kickoff):** Germany default flag, manager flag nits, US/Curaçao naming, delete `lobbytest_*` emulator accounts.
6. **Cost cleanup (post 2026-07-18):** revert `min_instances=1` → `0` in `functions/main.py`, redeploy.

### 9.1 Session-5 UX validation checklist (still worth a prod pass)
Sign in at `https://fpl-analyzer-792eb.web.app` (hard-refresh Cmd+Shift+R):
- [ ] **No "DR"** next to players (pitch, Player Browser, Free Agents, Waivers, My Squad). Draft-room DR column + "FDR" stay.
- [ ] Click a **player name** → stats popup; History tab = per-GW table; Fixtures tab = FDR table.
- [ ] **League → Schedule/Results**, click a manager's **team name** → their squad opens, grouped by position, non-empty.
- [ ] **Propose Trade:** pick a manager → both squads render → unequal positions block submit; equal positions enable + submit succeeds.
- [ ] **No Tweaks/gear panel** anywhere (new — should be hidden in prod). No console errors; no red "DEMO DATA" banner.

---

## 10. OPEN QUESTIONS

1. **Browser DB import** — pick one: (a) leave as best-effort (rules block server-only collections in a rules-enforcing emulator), (b) document running the emulator with open rules so import works fully, or (c) drop the browser import entirely and rely on `populate_emulator_real_squads.py`. (Decision pending with user.)
2. **Prod sign-in spot-check** — has the user confirmed in-browser that the Tweaks panel is hidden and lineup save works post-v=21? (Not agent-verifiable.)
3. Carried: real 7-friend dry-run before 06-06? Mock auto-run reschedule? Knockout config sanity for `lg_pre_draft` before GW7? `min_instances=1` revert (~2026-07-19)?

---

## 11. REFERENCE DOCS & MEMORY

- `WC2026_PLAN.md` — authoritative rules/schema/knockout edge cases (note: captains now removed from the implementation — confirm PLAN reflects this).
- `NETANEL_GUIDE.md` — onboarding for new contributors (referenced by `CLAUDE.md`).
- `CLAUDE.md` — repo rules for Claude: PR-only (never push main), the Netanel "if Frida can do it then so can you" preface rule, `.venv/bin/python`, `database_id=gamedb`, never commit secrets.
- `draft_wc_design/PRODUCT_SPEC.md` — API surface + validations.
- `firestore.rules` — security rules; see gotchas 19–21.
- Auto-memory: `~/.claude/projects/-Users-ilay-RiderProjects-fpl-analyzer/memory/project_wc2026.md`.
- Skills: `.claude/skills/handoff/` (this generator) and `pickup-handoff` (validate-and-align on resume).
- PR links: #9 https://github.com/ilayasayag/FplAnalyzer/pull/9 · #8 https://github.com/ilayasayag/FplAnalyzer/pull/8 · #4 (closed) https://github.com/ilayasayag/FplAnalyzer/pull/4
- The next agent should run this skill in **Pickup mode** to validate this handoff before resuming.
</content>
</invoke>
