# FPL Draft Analyzer

Live FPL Draft league analysis with fixture difficulty scoring, squad simulation, and replacement recommendations.

**All data is fetched live from the FPL API** - no bookmarklet, no database, no manual imports.

## Features

- **League Dashboard** - Live standings with W/D/L and points
- **Fixture Difficulty Grid** - Color-coded FDR grid for all 20 PL teams across GW1-38
- **Squad Fixture Analysis** - Per-position scoring (GK/DEF/MID/FWD) with easy/medium/hard tiers
- **Player Replacement Simulation** - Click any player to see ranked replacement candidates with impact scores
- **Free Agent Rankings** - Filter and sort available players by position, points, form
- **Transaction History** - View all waivers, free agent picks, and inter-manager trades

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python run_server.py

# Open http://localhost:5000
```

## Architecture

```
Browser (index.html)  →  Flask API (api.py)  →  FPL Draft API (live)
                                               →  FPL Fixtures API (FDR)
```

- **Frontend**: Single HTML file with vanilla JS (~400 lines)
- **Backend**: Stateless Flask API with in-memory cache (5-min TTL)
- **Data**: Fetched live from `draft.premierleague.com` and `fantasy.premierleague.com`
- **Storage**: None required. User preferences stored in localStorage.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Status + current gameweek |
| `GET /api/players` | All PL players with stats |
| `GET /api/teams` | All 20 PL teams |
| `GET /api/fixtures/grid` | Full fixture grid with FDR |
| `GET /api/league` | League info + entries |
| `GET /api/league/standings` | Computed standings |
| `GET /api/league/transactions` | Waivers and free agent picks |
| `GET /api/league/trades` | Inter-manager trades |
| `GET /api/squad/<entry_id>` | Enriched squad for a manager |
| `GET /api/free-agents` | Available players ranked |
| `GET /api/analysis/<entry_id>` | Squad fixture analysis |
| `POST /api/analysis/replacements` | Replacement candidates for a player |
| `POST /api/analysis/simulate` | What-if analysis with replacements |

All endpoints accept `?league_id=XXXXX` (defaults to env var `FPL_LEAGUE_ID`).

## Deploy to Cloud Run

```bash
# One-command deploy
gcloud run deploy fpl-analyzer --source . --region us-central1 --allow-unauthenticated

# Or with Docker
docker build -t fpl-analyzer .
docker run -p 8080:8080 fpl-analyzer
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | Server port |
| `HOST` | `0.0.0.0` | Server host |
| `DEBUG` | `false` | Flask debug mode |
| `FPL_LEAGUE_ID` | `201560` | Default league ID |

## Project Structure

```
fpl_analyzer/
├── index.html                      # Frontend (single file)
├── run_server.py                   # Entry point
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Cloud Run deployment
├── fpl_predictor/
│   ├── api.py                      # Flask REST API
│   ├── data/
│   │   └── fpl_api.py              # FPL API client with caching
│   └── engine/
│       └── analysis.py             # Squad fixture analysis engine
```

## Scoring System

Each player gets a per-gameweek score based on their team's Fixture Difficulty Rating:

| FDR | Tier | Regular | Star Player |
|---|---|---|---|
| ≤ 2.5 | Easy | 1.5 (DEF), 2.0 (FWD) | 2.0 |
| 2.5-3.5 | Medium | 1.0 | 1.5 |
| > 3.5 | Hard | 0.0-1.0 | 0.5-1.0 |

Position aggregate scores are classified into tiers:
- **Easy** (green): Strong position coverage for the gameweek
- **Medium** (yellow): Adequate but not ideal
- **Hard** (red): Weak coverage, consider transfers
