# WC 2026 Fantasy Draft — Implementation Sprints

> **Reference docs in order of importance:**
> 1. `WC2026_PLAN.md` — master rules, schema, edge cases
> 2. `draft_wc_design/PRODUCT_SPEC.md` — full API surface + validations
> 3. `draft_wc_design/README.md` — UI prototype notes

---

## ✅ Sprint 0 — Foundations (DONE)

Everything in this sprint is already written and committed.

| Module | File | Status |
|---|---|---|
| api-sports.io client | `fpl_predictor/data/wc_api.py` | ✅ |
| GW calendar | `fpl_predictor/game/wc_gameweeks.py` | ✅ |
| Scoring engine | `fpl_predictor/game/wc_scoring.py` | ✅ |
| League management | `fpl_predictor/game/wc_leagues.py` | ✅ |
| Squad + lineup | `fpl_predictor/game/wc_squads.py` | ✅ |
| Trades | `fpl_predictor/game/wc_trades.py` | ✅ |
| Waivers | `fpl_predictor/game/wc_waivers.py` | ✅ |
| Knockout engine | `fpl_predictor/game/wc_knockout.py` | ✅ |
| REST API (45 endpoints) | `fpl_predictor/api_wc.py` | ✅ |
| UI prototype | `draft_wc_design/` | ✅ |

---

## 🔧 Sprint 1 — Firebase Setup & Data Bootstrap

**Goal:** Running local server with Firestore connected; WC squads + fixtures loaded.

### 1.1 Firebase project

```bash
# Create project at https://console.firebase.google.com
# Enable: Firestore, Authentication (Email/Password + Google), Storage
firebase login
firebase init firestore   # select your project
firebase emulators:start
```

### 1.2 Get your api-sports.io key

1. Sign up free at https://www.api-sports.io/
2. Copy your key → `secrets.json`
3. Free tier: 100 req/day (enough for a single friend-group league)

### 1.3 Sync squads into Firestore

```bash
# Start the server
python run_server.py

# One-time: load all 48 WC 2026 national team squads (~48 API calls)
curl -X POST http://localhost:5000/api/v1/wc/admin/sync-squads \
  -H "Authorization: Bearer <your-firebase-id-token>"
```

Expected result: `{"data": {"teams": 48, "players": ~1248}, "error": null}`

> ⚠️ WC 2026 squads may not be in api-sports until ~June 1–5. Re-run daily until `players > 600`.

### 1.4 Sync fixtures

```bash
curl -X POST http://localhost:5000/api/v1/wc/admin/sync-fixtures \
  -H "Authorization: Bearer <your-firebase-id-token>"
```

Expected result: `{"data": {"fixturesWritten": 104}, "error": null}`

### 1.5 Verify

```bash
# Should return 48 teams
curl http://localhost:5000/api/v1/wc/teams | python3 -m json.tool | head -20

# Should return ~1248 players
curl http://localhost:5000/api/v1/wc/players?limit=5 | python3 -m json.tool
```

---

## 🎮 Sprint 2 — League Flow (Create → Draft → Season)

**Goal:** One complete league from creation to GW1 lineups.

### 2.1 Create a league

```bash
curl -X POST http://localhost:5000/api/v1/wc/leagues \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "El Clásico Friends", "displayName": "Admin", "maxMembers": 8, "pickTimer": 60}'
```

Share the `inviteCode` from the response with your friends.

### 2.2 Friends join

Each friend calls `POST /api/v1/wc/leagues/join` with the invite code.

### 2.3 Lock for draft (admin)

When everyone has joined:

```bash
curl -X POST http://localhost:5000/api/v1/wc/leagues/{lid}/lock \
  -H "Authorization: Bearer <admin-token>"
```

This finalises member count and computes knockout thresholds.

### 2.4 Start draft (admin)

```bash
curl -X POST http://localhost:5000/api/v1/wc/leagues/{lid}/draft/start \
  -H "Authorization: Bearer <admin-token>"
```

The draft engine (from `fpl_predictor/game/draft.py`) takes over. Each manager picks in snake order within `pickTimer` seconds.

### 2.5 Make a pick

```bash
curl -X POST http://localhost:5000/api/v1/wc/leagues/{lid}/draft/pick \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"playerId": 123, "idempotencyKey": "uuid-here"}'
```

### 2.6 Start season (admin, after draft completes)

```bash
curl -X POST http://localhost:5000/api/v1/wc/leagues/{lid}/start-season \
  -H "Authorization: Bearer <admin-token>"
```

This transitions status to `group_phase` and generates the H2H schedule.

### 2.7 Set lineup (each manager, before GW lockAt)

```bash
curl -X PUT http://localhost:5000/api/v1/wc/leagues/{lid}/lineup/1 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "starting": [pid1, pid2, ..., pid11],
    "bench": [gk_pid, out1, out2, out3],
    "captain": pid_captain,
    "viceCaptain": pid_vc
  }'
```

---

## ⚽ Sprint 3 — Live Scoring Pipeline

**Goal:** Fixtures processed automatically; GW scores update in real-time.

### 3.1 Background polling job

You need a job that runs every 5 minutes on match days. Options:

**Option A — Cloud Scheduler (recommended for Firebase)**
```bash
# Deploy as a Cloud Function and schedule with Cloud Scheduler
# Trigger: POST /api/v1/wc/admin/process-live-fixtures
```

**Option B — Simple cron during tournament**
```bash
# crontab -e
*/5 * * * * curl -X POST http://your-server/api/v1/wc/admin/process-live-fixtures \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>> /tmp/wc_poll.log
```

**Option C — Manual (works for a friends group)**
After each match finishes:
```bash
curl -X POST http://localhost:5000/api/v1/wc/admin/process-fixture/12345 \
  -H "Authorization: Bearer <admin-token>"
```

### 3.2 Implement the live polling helper (TODO)

> This method is not yet implemented — it's the only missing piece in the pipeline.

Add to `fpl_predictor/api_wc.py`:

```python
@wc_bp.route("/admin/process-live-fixtures", methods=["POST"])
def admin_process_live_fixtures():
    """
    1. GET /fixtures/live from api-sports
    2. For each fixture that just went FT: call process_fixture()
    3. Returns count of fixtures processed
    """
    uid, err = _require_auth()
    if err:
        return err
    
    live = _wc.get_live_fixtures()
    processed = []
    
    for f in live:
        status = f["fixture"]["status"]["short"]
        fid = f["fixture"]["id"]
        
        if status in ("FT", "AET", "PEN"):
            # Check if already processed
            doc = _db.collection("wc_fixtures").document(str(fid)).get()
            if doc.exists and doc.to_dict().get("processedForFantasy"):
                continue
            try:
                raw_stats = _wc.get_fixture_player_stats(fid, use_cache=False)
                process_fixture(fid, raw_stats, _wc, _db)
                processed.append(fid)
            except Exception as exc:
                pass  # log + continue
    
    return _ok({"processed": processed, "count": len(processed)})
```

### 3.3 GW finalization (admin)

After ALL fixtures in a GW are `processedForFantasy=true`:

```bash
curl -X POST http://localhost:5000/api/v1/wc/admin/leagues/{lid}/finalize-gw/1 \
  -H "Authorization: Bearer <admin-token>"
```

This chain runs automatically:
1. Auto-substitutions for all managers
2. Captain bonus applied
3. H2H results recorded
4. Standings updated
5. Elimination detection (after GW3)
6. Transfer window opened
7. Knockout seeding (if last league GW)

---

## 🏆 Sprint 4 — Knockout Phase

**Goal:** Bracket running, winners advancing, champion crowned.

### 4.1 Bracket seeded automatically

`finalize_gw()` calls `seed_knockout()` when `gw == knockoutStartGw - 1`.

For N ≤ 8 leagues: after GW6 finalizes → bracket seeded → GW7 is SF.
For N > 8 leagues: after GW3 finalizes → bracket seeded → GW4 is QF.

### 4.2 Bracket advancement

Happens automatically inside `finalize_gw()` for knockout GWs.

### 4.3 View bracket

```bash
curl http://localhost:5000/api/v1/wc/leagues/{lid}/knockout \
  -H "Authorization: Bearer <token>"
```

---

## 🌐 Sprint 5 — Deploy to Firebase (Production)

**Goal:** Friends access from their phones, not just localhost.

### 5.1 Deploy backend to Cloud Run

```bash
# Build + push Docker image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/wc-fantasy

# Deploy to Cloud Run
gcloud run deploy wc-fantasy \
  --image gcr.io/YOUR_PROJECT/wc-fantasy \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=YOUR_PROJECT"
```

### 5.2 Set secrets on Cloud Run

```bash
gcloud run services update wc-fantasy \
  --update-secrets="FOOTBALL_API_KEY=football-api-key:latest"
```

### 5.3 (Optional) Frontend

The `draft_wc_design/` prototype is a complete UI. To wire it to live endpoints:
- Replace `data.jsx` mock data with `fetch("/api/v1/wc/...")` calls
- Add Firebase Auth login flow
- Deploy to Firebase Hosting: `firebase deploy --only hosting`

---

## 🔮 Sprint 6 — Nice-to-haves

These are out of scope for a private friends league but easy to add:

| Feature | Where | Effort |
|---|---|---|
| Push notifications | Firebase Cloud Messaging | Medium |
| Auto waiver processing (T+24h) | Cloud Scheduler → `/admin/process-waivers/{window}` | Small |
| Auto trade expiry | Cloud Scheduler → `/admin/leagues/{lid}/expire-trades` | Small |
| Player search / browse in UI | Wire `draft_wc_design/screens-data.jsx` to `/players` API | Medium |
| Admin dashboard | New screen in UI prototype | Large |
| WC bracket live sync | Wire `screens-bracket.jsx` to `/knockout` API | Medium |

---

## 🗺️ Data flow reference

```
api-sports.io
     │
     ├─► sync_all_squads()  ──► wc_players, wc_teams (Firestore, once)
     ├─► sync_fixtures()    ──► wc_fixtures (Firestore, once)
     └─► get_live_fixtures() ──► (every 5 min, match days only)
              │
              ▼
     process_fixture(fid)
              │
              ├─► wc_fixtures/{fid}/playerScores/{pid}
              └─► leagues/{lid}/scores/{gw}  (Increment per starter)
                          │
                          ▼
              finalize_gw(lid, gw)
                          │
                          ├─► auto-subs + captain bonus
                          ├─► H2H results → standings
                          ├─► elimination detection (GW3)
                          ├─► transfer window opened
                          └─► knockout seeded / bracket advanced
```

---

## ⚠️ Known constraints & watch-outs

| # | Issue | Mitigation |
|---|---|---|
| 1 | api-sports WC 2026 squads not available yet | Re-run `sync-squads` daily from May 28; draft after June 3 |
| 2 | api-sports 100 req/day free limit | Only poll live fixtures; permanent cache for FT matches |
| 3 | Draft engine (`draft.py`) still expects FPL player shape | `WC2026Client` passed as `wc_client` — verify `get_player_map()` signature matches |
| 4 | `process-live-fixtures` endpoint is a TODO stub | Add the 15-line implementation from Sprint 3.2 above |
| 5 | No frontend auth flow | Use Firebase Console to get ID tokens for testing |
| 6 | Firestore security rules need WC collections added | Update `firestore.rules` to allow `wc_teams`, `wc_players`, `wc_fixtures` |

---

*Last updated: 2026-05-29 · WC 2026 kicks off June 11*
