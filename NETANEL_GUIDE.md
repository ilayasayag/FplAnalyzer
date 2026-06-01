# Hey Netanel 👋

This guide gets you from **"I have never seen this repo"** to **"I can run, test, and ship changes safely"** in about 30 minutes. Read it top to bottom once; come back to specific sections as you need them.

If anything here feels intimidating: **if Frida can do it, so can you.** Seriously. Push through and ask Claude when stuck.

---

## 0. What is this project, in 30 seconds

A private **FIFA World Cup 2026 fantasy snake-draft** app for our 7-friend group. You're one of the 7 (`u_netanel` / `netanel@wc2026.local`).

Two leagues exist:
- **`lg_mock_draft`** — a finished simulated season we click around to see what a complete UI looks like.
- **`lg_pre_draft`** — the real league. The draft happens **2026-06-06 20:00 IDT**.

Tech stack: Python Flask backend, vanilla React (Babel-in-browser) frontend, Firestore (Firebase) for data, deployed as a Cloud Function + Firebase Hosting at `https://fpl-analyzer-792eb.web.app`.

---

## 1. ⛔ THE GOLDEN RULE — never push to `main`

We ship through pull requests, period. Workflow is:

1. Make a branch off `main` (`git checkout -b your-thing`)
2. Commit on your branch
3. Push your branch to origin
4. Open a PR with `gh pr create`
5. Someone reviews, then merges

**Never** `git push origin main`. **Never** `git merge` into your local `main` and push. If you find yourself typing the word `main` after a git command other than `git checkout main` to read code, stop and think.

There are two GitHub accounts available locally:
- `ilay-asayag` — the default. **Cannot push to this repo (read-only).**
- `ilayasayag` — owner. Can push.

To push a branch you'll need `gh auth switch --user ilayasayag` first, then `gh auth switch --user ilay-asayag` to switch back.

---

## 2. One-time setup

```bash
# Clone (skip if you already have it)
git clone https://github.com/ilayasayag/FplAnalyzer.git
cd FplAnalyzer

# Python virtualenv used by the project
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # if requirements.txt exists
# or, if it doesn't, install the obvious deps:
.venv/bin/pip install flask firebase-admin requests google-cloud-firestore

# Firebase CLI (npm)
npm install -g firebase-tools
firebase login                                # opens browser; use ilayasayag@gmail.com

# Java (needed for the Firestore emulator)
brew install openjdk                          # macOS — skip if you already have Java
```

The repo has a service-account key path baked into a few scripts: `/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json`. Ask Ilay for it if you don't have it. **Never commit it.** It lives outside the repo on purpose.

---

## 3. Running the local stack

Four things need to be alive:

| Process | Port | Command (in its own terminal) |
|---|---|---|
| Firestore + Auth emulators | 8080 + 9099 | `firebase emulators:start --only firestore,auth,ui` |
| Flask backend | 5000 | `FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FPL_TESTING=true .venv/bin/python run_server.py` |
| Frontend static server | 8897 | `python3 -m http.server 8897 --directory dist` |
| (Seed once after emulator starts) | — | `FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 .venv/bin/python populate_emulator_real_squads.py` |

Now open `http://localhost:8897`. The frontend on `localhost` automatically talks to the emulators (not prod). You'll see the platform-selector lobby — Platform A (mock) or Platform B (real draft).

> Always use `.venv/bin/python`. The bare `python` doesn't have `firebase_admin` and the error messages are confusing.

---

## 4. Logging in

**Local emulator** has fake auth — you can sign up with any email/password and you're in.

**Production** (`https://fpl-analyzer-792eb.web.app`) — your login is:
- Email: `netanel@wc2026.local`
- Password: ask Ilay (or use the in-app **Change Password** button next to **Sign Out** the first time you sign in).

---

## 5. Playing with it — what to actually try

The mock league is your sandbox. Once signed in on Platform A:

- **Status / Points** — see how a finished season looks.
- **Pick Team** — drag-and-drop your starting XI (the mock has a finished squad).
- **Draft Room** — won't show anything because the mock draft is already done. Switch to Platform B to see it pre-draft.
- **Players** — full player browser, filterable by position and nation.
- **Knockout** — the bracket.
- **Trades / Transfers** — propose, vote, etc.
- **Change Password** (next to Sign Out) — try changing your password, then sign back in with the new one.

For Platform B you'll see `Status: pre_draft` — the draft hasn't been started. Only `u_roy` (admin) can hit "Start Draft."

---

## 6. Running the tests

Two test scripts you should know about:

```bash
# Bot-driven snake draft + 21 validation checks (happy + negative paths).
# Talks to the LOCAL backend, does NOT touch prod.
.venv/bin/python test_draft_bot.py

# Heavier end-to-end simulation that fakes 8 gameweeks of scoring + finalisation.
# ⚠️ WIPES THE EMULATOR — you need to re-run populate_emulator_real_squads.py after.
FIRESTORE_EMULATOR_HOST=localhost:8080 FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 FPL_TESTING=true \
  .venv/bin/python test_simulation.py
```

Green output = good. If `test_draft_bot.py` fails, something you changed broke the draft surface — fix before pushing.

---

## 7. Shipping a change (branch → PR)

```bash
# 1. Branch off main
git checkout main
git pull origin main
git checkout -b netanel/short-description

# 2. Edit code. Make sure tests still pass.
.venv/bin/python test_draft_bot.py

# 3. Commit (specific files, never "git add ." for sensitive stuff)
git add path/to/file1 path/to/file2
git commit -m "Short imperative description"

# 4. Push (switch accounts first!)
gh auth switch --user ilayasayag
git push origin netanel/short-description
gh auth switch --user ilay-asayag

# 5. Open PR
gh pr create --base main --title "Your title" --body "What + why, in 2-3 lines."
```

That's it. Wait for review. **Don't merge your own PRs without a green light.**

If a pre-commit hook fails, the commit didn't happen — fix the issue and commit again. Don't use `--no-verify`.

---

## 8. The lay of the land — where stuff lives

```
fpl_predictor/
  api.py                ← Flask app entry (also the Cloud Function entry)
  api_wc.py             ← All /api/v1/wc/* HTTP routes
  game/
    draft.py            ← Snake draft engine (the brain of the live draft)
    wc_scoring.py       ← Points calculation
    wc_knockout.py      ← Bracket seeding + advancement
    wc_leagues.py       ← League CRUD
    wc_squads.py        ← Squad CRUD
  data/
    wc_api.py           ← WC2026Client: pulls from api-sports.io, caches in Firestore
  seed/
    seed_league.py      ← Canonical seeding logic, used by both prod + emulator
draft_wc_design/        ← Frontend source (.jsx files, in-browser Babel)
dist/                   ← Built frontend — same files as draft_wc_design/ but DEPLOYED
functions/              ← Firebase Functions wrapper (entrypoint for the Cloud Function)
test_draft_bot.py       ← Bot-driven draft test (read this — it's a great example of using the API)
test_simulation.py      ← Full season simulation
populate_emulator_real_squads.py  ← Seeds the LOCAL emulator with both leagues
populate_production_real_squads.py ← The PROD reseed (destructive — only run if you know why)
WC2026_PLAN.md          ← Authoritative product/rules spec
WC2026_GOLIVE_HANDOFF.md ← Latest "what's going on right now" status doc
```

**Gotcha #1 — `dist/` is a separate copy of `draft_wc_design/`.** When you change a `.jsx` file in `draft_wc_design/`, copy it to `dist/` too (`cp draft_wc_design/foo.jsx dist/foo.jsx`) or your local frontend won't see the change.

**Gotcha #2 — Babel-in-browser treats `let`/`const` as block-scoped.** A `const foo` declared inside an `if {}` block is *not* visible in a sibling `else {}` block. We've been bitten by this several times — keep declarations at the right scope.

**Gotcha #3 — `secrets.json` and the service account JSON must NEVER be committed.** They're gitignored, but if you create new scripts that read them, double-check `git status` before committing.

---

## 9. Deploying to prod (you probably don't need to do this)

You won't deploy until you're comfortable. When the day comes:

```bash
# Backend (Cloud Function)
firebase deploy --only functions:api

# Frontend (Hosting)
firebase deploy --only hosting
```

Both require `firebase login` to be `ilayasayag@gmail.com`. **Never deploy without your PR being merged first** — deployed-but-unmerged code is how we lose changes.

---

## 10. When you're stuck

1. **Read the error.** Most errors say what's wrong literally. `KeyError: 'currentDrafter'`? Something's missing that key.
2. **Re-read this guide.** Maybe section 3 (something not running) or section 8 (gotcha you tripped on).
3. **Ask Claude.** Claude has the whole codebase in front of it. Be specific — paste the error, paste what you tried.
4. **Ask Ilay.** Last resort, but no shame in it.

And when you doubt yourself: **if Frida can do it, so can you.**

---

*Welcome to the team. Now go break something (on a branch).* 🎯
