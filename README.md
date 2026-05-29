# ⚽ WC 2026 Fantasy Draft

A **full-stack Fantasy Draft platform for FIFA World Cup 2026** — private leagues for groups of friends, snake draft, head-to-head competition, live scoring via api-sports.io, and a knockout bracket.

Built on **Firebase + Python (Flask)** with a fully interactive UI prototype included.

---

## ✨ What this is

A self-hosted fantasy football platform you deploy to Firebase for your friend group. Think FPL Draft — but for the World Cup, with:

- 🐍 **Snake draft** — 15 rounds, position quotas (2GK/5DEF/5MID/3FWD)
- 🏆 **H2H league → knockout bracket** — round-robin group phase, then QF/SF/Final
- ⚡ **Live scoring** — fixtures polled from api-sports.io every 5 min during matches
- 🔄 **Transfer windows** — 2 free transfers per window, waiver priority system
- 🤝 **Trades** — like-for-like, veto voting at `ceil(N/3)` threshold
- 📊 **Captain + bonus points** — double your captain's score; BPS 3/2/1 bonus
- 🗺️ **48 teams** — all WC 2026 nations, elimination tracking after Group Stage

---

## 📦 Repository layout

```
├── WC2026_PLAN.md              ← Master product plan (single source of truth)
├── SPRINTS.md                  ← Ordered implementation guide (start here)
├── secrets.json.example        ← API key template — copy to secrets.json
│
├── fpl_predictor/
│   ├── api.py                  ← Main Flask app entry point
│   ├── api_wc.py               ← WC2026 Blueprint — 45 REST endpoints
│   │
│   ├── data/
│   │   └── wc_api.py           ← WC2026Client (api-sports.io wrapper + Firestore sync)
│   │
│   └── game/
│       ├── wc_gameweeks.py     ← GW calendar (Jun 11 – Jul 19 2026)
│       ├── wc_scoring.py       ← Scoring engine + GW finalization
│       ├── wc_leagues.py       ← League create/join/manage
│       ├── wc_squads.py        ← Squad + lineup + captain/VC
│       ├── wc_trades.py        ← Trades with ceil(N/3) veto
│       ├── wc_waivers.py       ← Two-phase waiver system
│       ├── wc_knockout.py      ← Bracket seeding + advancement
│       ├── draft.py            ← Snake draft engine (reused from FPL)
│       └── schedule.py         ← Round-robin H2H schedule generator
│
├── draft_wc_design/            ← ✨ Full hi-fi UI prototype (open in browser)
│   ├── WC26 Fantasy Draft.html ← Entry point — open this
│   ├── PRODUCT_SPEC.md         ← Full API surface + validations
│   ├── README.md               ← UI prototype docs
│   └── *.jsx / styles.css      ← React components (vanilla, no build step)
│
├── firestore.rules             ← Firestore security rules
├── firebase.json               ← Firebase hosting + functions config
└── requirements.txt            ← Python dependencies
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Firebase CLI | `npm install -g firebase-tools` |
| api-sports.io account | Free tier (100 req/day) — [sign up](https://www.api-sports.io/) |

### 1 — Clone + configure secrets

```bash
git clone https://github.com/ilayasayag/FplAnalyzer.git
cd FplAnalyzer

cp secrets.json.example secrets.json
# Edit secrets.json and fill in your api-sports key
```

`secrets.json` (never commit this):
```json
{
  "FOOTBALL_API_KEY": "your_api_sports_key_here",
  "FOOTBALL_API_HOST": "v3.football.api-sports.io",
  "FOOTBALL_API_BASE": "https://v3.football.api-sports.io"
}
```

### 2 — Python backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_server.py          # starts on http://localhost:5000
```

### 3 — Firebase

```bash
firebase login
firebase use --add            # select your project
firebase emulators:start      # Firestore + Auth emulators
```

### 4 — Preview the UI prototype

No build step needed:

```bash
cd draft_wc_design
python3 -m http.server 8000
# Open http://localhost:8000/WC26%20Fantasy%20Draft.html
```

---

## 🏗️ Implementation sprints

See **[SPRINTS.md](SPRINTS.md)** for the full ordered execution plan.

**TL;DR order:**

1. `POST /api/v1/wc/admin/sync-squads` — load all 48 WC squads into Firestore
2. `POST /api/v1/wc/admin/sync-fixtures` — load GW fixture schedule
3. League create → join → `lock` → draft → `start-season`
4. Managers set lineups before each GW lockAt
5. Background job polls live fixtures; `process-fixture` for each FT match
6. `finalize-gw` after all fixtures in a GW complete
7. Knockout seeds automatically after last league GW

---

## 🗓️ Tournament calendar

| GW | WC Round | Dates | N > 8 | N ≤ 8 |
|---|---|---|---|---|
| 1 | Group Stage R1 | Jun 11–15 | H2H League | H2H League |
| 2 | Group Stage R2 | Jun 16–21 | H2H League | H2H League |
| 3 | Group Stage R3 | Jun 22–26 | H2H League | H2H League |
| 4 | Round of 32 | Jun 27–Jul 4 | **Knockout QF** | H2H League |
| 5 | Round of 16 | Jul 5–9 | Knockout SF | H2H League |
| 6 | Quarter-finals | Jul 10–12 | Knockout Final | H2H League |
| 7 | Semi-finals | Jul 14–15 | — | **Knockout SF** |
| 8 | Final + 3rd Place | Jul 18–19 | — | Knockout Final |

---

## 🔑 Key API endpoints

```
POST   /api/v1/wc/leagues                      Create league
POST   /api/v1/wc/leagues/join                 Join by invite code
GET    /api/v1/wc/leagues/{lid}                League details
POST   /api/v1/wc/leagues/{lid}/lock           Lock for draft
POST   /api/v1/wc/leagues/{lid}/draft/start    Start snake draft
POST   /api/v1/wc/leagues/{lid}/draft/pick     Make a pick
PUT    /api/v1/wc/leagues/{lid}/lineup/{gw}    Set lineup + captain
GET    /api/v1/wc/leagues/{lid}/scores/{gw}    GW scores
GET    /api/v1/wc/leagues/{lid}/standings      H2H table
GET    /api/v1/wc/leagues/{lid}/knockout       Bracket
POST   /api/v1/wc/leagues/{lid}/waivers        Submit waiver claim
POST   /api/v1/wc/leagues/{lid}/free-agent     FCFS pickup
POST   /api/v1/wc/leagues/{lid}/trades         Propose trade
```

Full spec: [`draft_wc_design/PRODUCT_SPEC.md`](draft_wc_design/PRODUCT_SPEC.md)

---

## ⚙️ Scoring rules

| Stat | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Played < 60 min | 1 | 1 | 1 | 1 |
| Played ≥ 60 min | 2 | 2 | 2 | 2 |
| Goal scored | 10 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet (≥60 min) | 4 | 4 | 1 | 0 |
| Goals conceded (per 2) | -1 | -1 | 0 | 0 |
| Yellow card | -1 | -1 | -1 | -1 |
| Red card | -3 | -3 | -3 | -3 |
| Save (per 3, in-play) | 1 | — | — | — |
| Penalty save (in-play) | 5 | — | — | — |
| Own goal | -2 | -2 | -2 | -2 |
| Penalty miss | -2 | -2 | -2 | -2 |
| BPS bonus (top 3) | 3/2/1 | 3/2/1 | 3/2/1 | 3/2/1 |

**Captain** doubles points. If captain played 0 min, vice-captain becomes effective captain.
Penalty shootout saves/misses **not** counted.

---

## 🏛️ Architecture

```
Firebase Auth ──► Flask API (Cloud Run / local)
                       │
                       ├── WC2026Client (api-sports.io)
                       │       └── TTL cache + Firestore sync
                       │
                       └── Firestore (gamedb)
                               ├── wc_teams / wc_players / wc_fixtures
                               └── leagues/{lid}/
                                       ├── members, squads, lineups
                                       ├── draft/state + picks
                                       ├── scores/{gw}, standings
                                       ├── transfer_windows, waivers
                                       ├── trades, transactions
                                       └── knockout/bracket
```

Realtime updates via Firestore `onSnapshot` — no polling needed on the frontend.

---

## 🤝 Contributing

This is designed to be self-hosted by any group. To extend it:

1. Read [`WC2026_PLAN.md`](WC2026_PLAN.md) — master spec with all rules
2. Read [`SPRINTS.md`](SPRINTS.md) — what's built, what's next
3. Read [`draft_wc_design/PRODUCT_SPEC.md`](draft_wc_design/PRODUCT_SPEC.md) — full API contract
4. Open the UI prototype to understand expected UX

PRs welcome — especially:
- Frontend (React app wired to live endpoints)
- Push notifications (Firebase Cloud Messaging)
- Admin dashboard for GW management
- Auto-processing background job (Cloud Scheduler)

---

## 📝 License

MIT — use it for your friends group, modify freely.

---

> Built with Claude Code · WC 2026 starts **June 11, 2026**
