# FPL Score Predictor

A statistical analysis tool for predicting Fantasy Premier League (FPL) player scores based on team batch rankings, historical performance data, and opponent analysis.

## Features

- **Team Batch Analysis**: Groups teams by league position (Top 4, Mid-table, Relegation) to analyze performance patterns
- **Per-Player Statistics**: Calculates detailed stats including goals/90, assists/90, clean sheet rates
- **Weighted Predictions**: Combines batch-specific stats, overall performance, and recent form
- **Outlier Handling**: Filters injury games, dampens extreme performances, weights by sample size
- **Optimal 11 Selection**: Picks best lineup respecting FPL formation rules (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD)
- **Multiple Output Formats**: CLI, JSON export, REST API

## Installation

```bash
cd fpl_predictor
pip install -r requirements.txt
```

## Quick Start

### 1. Export Data from HTML Analyzer

Use the FPL Analyzer HTML tool to fetch and export league data:
1. Open the analyzer and run the bookmarklet on FPL Draft
2. Copy the exported JSON data
3. Save to a file (e.g., `data.json`)

### 2. CLI Usage

```bash
# Predict a single player
python main.py predict data.json -p "Salah" -o "Bournemouth"

# Predict entire squad
python main.py squad data.json -e 822133 -g 22

# Show batch summary
python main.py batches data.json

# Analyze all players
python main.py analyze data.json -o output.json
```

### 3. API Usage

Start the API server:
```bash
python api.py --port 5000 --data data.json
```

Then make requests:
```bash
# Health check
curl http://localhost:5000/api/health

# Get player prediction
curl "http://localhost:5000/api/predict/player/308?opponent_id=3&gameweek=22"

# Get squad prediction
curl "http://localhost:5000/api/predict/squad/822133"

# List all teams
curl http://localhost:5000/api/teams
```

## Architecture

```
fpl_predictor/
├── config.py              # FPL scoring rules, batch definitions
├── main.py                # CLI entry point
├── api.py                 # Flask REST API
├── export.py              # JSON export utilities
│
├── data/
│   ├── loader.py          # Load JSON exports from analyzer
│   └── standings.py       # Fetch live PL standings
│
├── models/
│   ├── player.py          # Player data model
│   ├── team.py            # Team & batch models
│   └── prediction.py      # Prediction result models
│
├── engine/
│   ├── batch_analyzer.py  # Team batch statistics
│   ├── player_stats.py    # Per-player performance analysis
│   ├── event_probability.py # Goal/assist/CS probability
│   └── points_calculator.py # Convert to expected points
│
└── utils/
    ├── outlier_filter.py  # Edge case handling
    └── weighted_average.py # Bayesian-style calculations
```

## FPL Scoring Rules

| Action | GK | DEF | MID | FWD |
|--------|-----|-----|-----|-----|
| Playing 1-59 min | 1 | 1 | 1 | 1 |
| Playing 60+ min | 2 | 2 | 2 | 2 |
| Goal scored | 6 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet (60+ min) | 4 | 4 | 1 | 0 |
| 3 saves (GK) | 1 | - | - | - |
| Penalty save | 5 | 5 | 5 | 5 |
| Penalty miss | -2 | -2 | -2 | -2 |
| 2 goals conceded | -1 | -1 | 0 | 0 |
| Yellow card | -1 | -1 | -1 | -1 |
| Red card | -3 | -3 | -3 | -3 |
| Own goal | -2 | -2 | -2 | -2 |
| Bonus (BPS top 3) | 1-3 | 1-3 | 1-3 | 1-3 |

## Batch System

Teams are grouped into batches based on league position:

| Batch | Positions | Typical Teams |
|-------|-----------|---------------|
| Top 4 | 1-4 | Liverpool, Man City, Arsenal, Chelsea |
| Upper Mid | 5-8 | Newcastle, Brighton, Bournemouth |
| Mid Table | 9-12 | Fulham, Brentford, Spurs |
| Lower Mid | 13-16 | Man Utd, West Ham, Everton |
| Relegation | 17-20 | Wolves, Leicester, Southampton |

## Prediction Algorithm

1. **Load Data**: Parse exported JSON from analyzer
2. **Fetch Standings**: Get current PL table positions
3. **Assign Batches**: Group teams by position
4. **Analyze Players**: Calculate per-batch statistics
5. **Calculate Probabilities**: 
   - Playing time (based on minutes history)
   - Goals (based on xG, batch-adjusted)
   - Assists (based on xA, batch-adjusted)
   - Clean sheets (based on opponent attack strength)
   - Bonus (based on BPS history)
6. **Convert to Points**: Apply FPL scoring rules
7. **Output**: CLI tables, JSON, or API response

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/load` | POST | Load data file |
| `/api/predict/player/<id>` | GET | Predict single player |
| `/api/predict/squad/<entry_id>` | GET | Predict squad |
| `/api/players` | GET | List players |
| `/api/players/<id>` | GET | Get player details |
| `/api/teams` | GET | List teams |
| `/api/teams/<id>` | GET | Get team details |
| `/api/batches` | GET | Get batch summary |
| `/api/league` | GET | Get league info |
| `/api/export/predictions` | POST | Export all predictions |

## Configuration

Key settings in `config.py`:

```python
# Batch definitions
DEFAULT_BATCHES = [
    (1, 4),    # Top 4
    (5, 8),    # Upper mid
    (9, 12),   # Mid table
    (13, 16),  # Lower mid
    (17, 20),  # Relegation
]

# Statistical parameters
STATS_CONFIG = StatsConfig(
    MIN_MINUTES_PLAYED=10,      # Ignore games with < 10 min
    OUTLIER_SIGMA=2.0,          # Std devs for outlier detection
    MIN_BATCH_GAMES=2,          # Min games for reliable batch stats
    BATCH_WEIGHT_FACTOR=0.6,    # Weight for batch vs overall
    FORM_WEIGHT=0.4,            # Weight for recent form
)
```

## Future Improvements

- [ ] Integrate real fixture data for accurate opponent matching
- [ ] Add xG/xA data from external sources (FBref, Understat)
- [ ] Machine learning model for comparison
- [ ] Historical season data for training
- [ ] Automated data fetching pipeline

## License

MIT

