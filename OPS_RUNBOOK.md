# WC2026 Ops Runbook

How we **deploy, update, and access the DB** for the live World Cup fantasy game.
This is the canonical operational reference; `WC2026_GOLIVE_HANDOFF.md` is the
session log and `NETANEL_GUIDE.md` is the newcomer guide. Bugs: `KNOWN_ISSUES.md`.

---

## 1. Identity & access

- **GitHub:** `gh` is logged in as `ilayasayag`. Git commit email should be
  `ilayasayag@gmail.com` (this is a personal project), **not** a work email — set
  `git config user.email ilayasayag@gmail.com`.
- **Firebase deploy:** `firebase login` must be `ilayasayag@gmail.com`
  (`firebase login:list` to check).
- **Prod data:** Firestore project `fpl-analyzer-792eb`, database **`gamedb`**
  (region `nam5`). The `(default)` database is a divergent, empty store —
  **never** read or write it.
- **Backend:** Flask app served as Cloud Function `api` (us-central1, python313,
  `min_instances=1`) at `https://api-4anrfyrdxa-uc.a.run.app`. **Frontend:**
  Firebase Hosting at `https://fpl-analyzer-792eb.web.app`.

### Collaborators & merge control

- **Roles:** `ilayasayag` (owner/admin) is the **only** account that merges to
  `main` and deploys to **prod**. Contributors (e.g. Chen, Netanel) get **Write**
  access so they can push branches and open PRs — they **cannot** merge.
- **Enforcement:** `main` is protected (require PR + 1 approving review +
  **review from Code Owners**). `.github/CODEOWNERS` makes `@ilayasayag` the sole
  code owner, so no PR merges without his review and contributors can't
  self-approve. (This is a personal/public repo — GitHub's per-user "who can
  merge" lock is org-only, so this review gate is the enforcement mechanism.)
- **Prod deploy** is gated by Firebase/GCP credentials, not GitHub: only the
  owner's `firebase login` can `firebase deploy`. Don't hand out prod IAM.

### Staging environment (Hosting preview channel)

Contributors test on a **staging Hosting channel** that shares the prod backend
(`api` Cloud Function + `gamedb`) — frontend-only isolation, no separate DB.

```bash
# Deploy current dist/ to the staging channel (from a checkout with a real dist/)
firebase hosting:channel:deploy staging --project fpl-analyzer-792eb --expires 30d
```

- Channel URL: `https://fpl-analyzer-792eb--staging-<hash>.web.app`
  (run `firebase hosting:channel:list` for the current URL — the hash is stable
  per channel; re-deploying refreshes content, not the URL).
- Preview channels expire (30-day max). Re-run the command to extend/refresh.
- To let Chen/Netanel deploy to staging themselves they'd need Firebase Hosting
  IAM on the prod project — **not granted by default** (it would also expose prod
  data). Default flow: they open a PR, owner deploys their branch to staging.

## 2. Accessing the prod DB (read or write)

Use `.venv/bin/python` (bare `python` lacks `firebase_admin`). Two working auth
paths, in order of preference:

```python
# Preferred: the firebase-adminsdk service-account JSON
from google.cloud import firestore
from google.oauth2 import service_account
SA = "/Users/ilay/Downloads/fpl-analyzer-792eb-firebase-adminsdk-fbsvc-b9d60c3c01.json"
creds = service_account.Credentials.from_service_account_file(SA)
db = firestore.Client(project="fpl-analyzer-792eb", credentials=creds, database="gamedb")
```
```python
# Fallback: the gcloud SA access token (active account = firebase-adminsdk SA)
import subprocess; from google.oauth2.credentials import Credentials
tok = subprocess.check_output(["gcloud","auth","print-access-token"], text=True).strip()
db = firestore.Client(project="fpl-analyzer-792eb", credentials=Credentials(token=tok), database="gamedb")
```

- **PITFALL:** plain `firebase_admin.initialize_app()` / bare Application Default
  Credentials resolve to a **no-permission user identity → `PermissionDenied
  403`**. Always pass the SA json or the gcloud SA token explicitly.
- **Never commit** the SA json or `secrets.json` (it's API keys, not an SA cert).
- **Mutating prod is read-only by default** — only write (backfills, rescores)
  with **explicit user authorization**. Validation/debugging stays read-only.

## 3. Deploy (only after the PR is merged to `main`)

> Never deploy unmerged code — deployed-but-unmerged is how changes get lost.

**Backend** (Cloud Function): backward-compatible changes only; if frontend and
backend are coupled, deploy both together.
```bash
firebase deploy --only functions:api --project fpl-analyzer-792eb
# predeploy copies fpl_predictor/ + secrets.json into functions/ automatically
```

**Frontend** — there is **NO build step**: raw `.jsx` is served and transpiled by
**in-browser Babel**. `dist/` is a **separate, gitignored copy** of
`draft_wc_design/`.
```bash
# 1. sync changed jsx (NOT firebase.jsx — dist/ has the real prod config)
cp draft_wc_design/<changed>.jsx dist/<changed>.jsx
# 2. bump the cache-bust version in dist/index.html (find live version first)
curl -s https://fpl-analyzer-792eb.web.app/index.html | grep -o 'jsx?v=[0-9]*' | head -1
perl -pi -e 's/\?v=OLD/?v=NEW/g' dist/index.html
# 3. COMPILE-CHECK every changed jsx (a syntax error white-screens the WHOLE app)
#    npm i @babel/core @babel/preset-react in a temp dir; transformSync each file.
# 4. deploy + verify
firebase deploy --only hosting --project fpl-analyzer-792eb
curl -s https://fpl-analyzer-792eb.web.app/index.html | grep -o 'jsx?v=[0-9]*' | head -1
```

- **Compile-check is necessary but NOT sufficient.** Scope/runtime errors
  (undefined var, out-of-scope prop) crash a component at render and pass Babel
  (this caused the `HistoryTab` white-screen — see `KNOWN_ISSUES.md`).
  **SSR-smoke-test or load the touched component before deploying frontend:**
  `renderToStaticMarkup(React.createElement(Comp, sampleProps))`.

## 4. Stacked-PR merge workflow

Never push to `main`. Branch → commit → push → `gh pr create`. For a stack
(`#a→#b→#c`), re-target each PR's base to `main` (`gh pr edit N --base main`) and
merge **bottom-up**; each branch is a superset of its parent, so the merges are
clean and only that PR's own commits land.

## 5. Backfill / re-score the live scores

- **Cloud ticks (scheduled jobs + the user "Sync data" button)** deliver FIFA
  points + ESPN stats only — **WhoScored 403s from datacenter IPs**, so DefCon
  requires a tick from the **residential Mac**.
- `recompute_all_scores` is the self-heal: it re-derives totals, scouting,
  FIFA-position itemization, and DefCon-by-position from **already-stored stats**
  (so a Sync fixes those without a re-parse).
- **New stat keys** (penalties, per-player clean sheet) need a **force re-parse
  from WhoScored**: clear `scoredFinal` on the fixture, then re-run
  `ingest_whoscored_fixture` (residential). Use the **`/sync-gw-scores` skill** —
  it encodes the diagnose → clear-bookmark → tick → verify procedure.
- **Always verify after:** per-player `expected = FIFA − scouting + DefCon ==
  stored` (0 mismatches), and `leagues/lg_mock_draft/scores/{gw}` `updatedAt` is
  fresh.

## 6. Scoring model invariant (don't break it)

```
fantasyPoints = FIFA_round_total + DefCon_bonus − scouting_bonus
```
in **every** write path (`ingest_whoscored_fixture`, `ingest_live`,
`recompute_all_scores`). The itemized `breakdown` lines are **display-only** — a
balancing "FIFA match points" / "FIFA adjustment" line absorbs whatever we can't
itemize, so the lines always sum to the total. Scouting (0 or 2) comes from the
FIFA total + FIFA %owned only. **DefCon: DEF = CBIT, MID = CBITR** (ball
recoveries count for MID only). The breakdown reconstructs FIFA's published rules
using **FIFA's position** (goal value etc.), while DefCon thresholds + roster use
our **pool** position — the two notions are intentionally separate.
