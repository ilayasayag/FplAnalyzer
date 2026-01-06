# FPL Draft Analyzer

A comprehensive Fantasy Premier League (FPL) Draft analysis tool with **batch-based prediction system**, squad optimization, fixture analysis, and head-to-head comparisons.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Core Prediction Algorithm](#core-prediction-algorithm-batch-based-system)
4. [FPL Scoring Rules](#fpl-scoring-rules-implemented)
5. [Data Structures](#key-data-structures)
6. [Key Functions Reference](#key-functions-reference)
7. [External APIs](#external-apis)
8. [How to Use](#how-to-use)
9. [Files](#files)
10. [AI Agent Guidance](#ai-agent-guidance)

---

## Project Overview

### Purpose
This tool analyzes FPL Draft leagues by:
- Fetching real league data via bookmarklet from `draft.premierleague.com`
- Predicting player scores using a **batch-based statistical model**
- Optimizing lineups respecting FPL formation rules
- Calculating realistic H2H win probabilities with uncertainty modeling

### Key Capabilities
| Feature | Description |
|---------|-------------|
| **GW Predictions** | Predict points for each player based on opponent batch |
| **Optimal 11 Selection** | Auto-select best lineup with valid formation |
| **H2H Win Probability** | Statistical win % with uncertainty (not just "90% always") |
| **Match Score Predictor** | Predict PL match scores between any two teams |
| **DC Bonus Prediction** | Estimate Defensive Contribution bonus points |
| **Trade Suggestions** | Smart trade recommendations |

### Tech Stack
- **Pure HTML/CSS/JavaScript** - Single file, no build process
- **No external dependencies** - Runs entirely in browser
- **LocalStorage persistence** - Data saved automatically
- **~13,000 lines** in one self-contained HTML file

---

## Architecture

```
fpl_fixture_analyzer.html (~12,900 lines)
│
├── HTML Structure (lines 1-3000)
│   ├── CSS Styles & Variables
│   │   └── Dark theme with accent colors (emerald, violet, cyan, rose, amber)
│   ├── Tab-based UI
│   │   ├── League Dashboard
│   │   ├── Squad Analysis
│   │   ├── Fixtures Grid
│   │   ├── H2H Comparison
│   │   ├── Trade System
│   │   ├── GW Simulation (predictions)
│   │   └── PL Stats (standings, match predictor)
│   └── Modal Components (player details, trade builder)
│
├── JavaScript - Data Layer (lines 7000-7500)
│   ├── Global Variables (importedLeagueData, importedBootstrap, etc.)
│   ├── LocalStorage Functions (saveLeagueData, loadSavedData)
│   ├── Bookmarklet Generator
│   └── Data Import/Export
│
├── JavaScript - Batch Analysis System (lines 10700-11400)
│   ├── BATCH_CONFIG (batches, scoring rules, thresholds)
│   ├── initBatchAnalysis() - Main initialization
│   ├── buildBatchMap() - Assigns teams to batches by rank
│   ├── calculateTeamBatchStats() - Team goals for/against per batch
│   ├── calculatePlayerBatchStats() - Player stats per batch
│   └── calculateLeagueAverages() - League-wide baselines
│
├── JavaScript - Prediction Engine (lines 11200-11800)
│   ├── predictPlayerPointsBatch() - Core prediction function
│   ├── applyBayesianBlend() - Blends batch/overall stats
│   ├── crossReferenceWithOpponent() - Adjusts for opponent strength
│   ├── calculateGWPredictions() - Team-level predictions
│   ├── selectOptimalLineup() - Formation-valid lineup
│   └── calculateH2HWinProbability() - Statistical win probability
│
└── JavaScript - UI Rendering (lines 11800-12900)
    ├── renderTeamRankings()
    ├── renderH2HMatchupPredictions()
    ├── renderPlayerBreakdown()
    ├── renderPLStandings()
    ├── renderPLTeamCards()
    └── calculateMatchupPrediction() (PL match predictor)
```

---

## Core Prediction Algorithm: Batch-Based System

### Concept
Instead of treating all opponents equally, we group teams into **batches** by their league position and analyze how players perform against each batch.

### Batch Configuration
```javascript
BATCH_CONFIG.batches = [
    { id: 1, name: 'Top (1-4)', min: 1, max: 4 },
    { id: 2, name: 'Upper Mid (5-8)', min: 5, max: 8 },
    { id: 3, name: 'Mid Table (9-12)', min: 9, max: 12 },
    { id: 4, name: 'Lower Mid (13-16)', min: 13, max: 16 },
    { id: 5, name: 'Bottom (17-20)', min: 17, max: 20 }
]
```

### Prediction Formula

For each player vs opponent:

```
1. Get opponent's batch (based on PL standings)

2. Get player's batch-specific stats:
   - goalsPerGame vs this batch
   - assistsPerGame vs this batch
   - dcPerGame vs this batch (45+ min games only)
   - csPerGame vs this batch
   - bonusPerGame vs this batch

3. Apply Bayesian Blending (for small sample sizes):
   blendedStat = (batchStat × batchGames + overallStat × priorWeight) / (batchGames + priorWeight)
   
   Where priorWeight = 3 (gives overall stats weight when batch games < 3)

4. Cross-reference with opponent:
   offensiveMultiplier = opponentGoalsConceded / leagueAvgConceded
   defensiveMultiplier = leagueAvgScored / opponentGoalsScored

5. Apply home/away adjustment:
   homeMultiplier = 1.1 (home) or 0.95 (away)

6. Calculate FPL points:
   goals × goalPoints[position]
   + assists × 3
   + cleanSheet × csPoints[position]
   + saves / 3
   + dcBonus (if expectedDC >= threshold)
   + bonus
   - cards
   + minutes
```

### DC Bonus Calculation
```javascript
// Defensive Contribution bonus (2 pts)
const dcThreshold = (pos === 'DEF' || pos === 'GK') ? 10 : 12;

if (expectedDC >= dcThreshold) {
    dcBonusProb = 0.5 + (expectedDC - dcThreshold) * 0.1;
} else if (expectedDC >= dcThreshold - 3) {
    dcBonusProb = dcBonusRate * (expectedDC / dcThreshold);
}

dcBonus = dcBonusProb × 2;
```

### H2H Win Probability (Statistical)
```javascript
// Calculate uncertainty for each team based on prediction confidence
σ = baseUncertainty(12) + lowConfPlayers×2 + medConfPlayers×1 + highConfPlayers×0.5

// Combined standard deviation
σ_diff = √(σ1² + σ2²)

// Win probability using normal distribution
P(Team1 wins) = Φ((μ1 - μ2) / σ_diff)
```

---

## FPL Scoring Rules Implemented

```javascript
BATCH_CONFIG.fplScoringRules = {
    // Minutes
    minutes60plus: 2,
    minutes1to59: 1,
    
    // Goals
    goalGK: 6,    // GK/DEF
    goalMID: 5,
    goalFWD: 4,
    
    // Other
    assist: 3,
    cleanSheetGK: 4,   // GK/DEF
    cleanSheetMID: 1,
    savesPerPoint: 3,  // 1 pt per 3 saves
    
    // DC Bonus (FPL Draft specific)
    dcBonusDEF: 2,     // if DC >= 10
    dcBonusMID: 2,     // if DC >= 12
    
    // Penalties
    goalsConcededPenalty: -1,  // per 2 goals conceded (GK/DEF)
    yellowCard: -1,
    redCard: -3,
    ownGoal: -2,
    penaltyMiss: -2
}
```

---

## Key Data Structures

### `importedLeagueData`
```javascript
{
    league: { id, name, ... },
    league_entries: [
        { entry_id, entry_name, player_first_name, ... }
    ],
    squads: {
        "entry_id": {
            picks: [{ element: playerId, position: 1-15 }, ...]
        }
    },
    transactions: [...],
    matches: { h2h_matches: [...] }
}
```

### `importedBootstrap`
```javascript
{
    elements: [
        {
            id, web_name, first_name, second_name,
            team, element_type, // 1=GK, 2=DEF, 3=MID, 4=FWD
            form, points_per_game, total_points,
            status, chance_of_playing_next_round,
            goals_scored, assists, clean_sheets,
            defensive_contribution, // season total
            ...
        }
    ],
    teams: [
        { id, name, short_name, strength, ... }
    ],
    fixtures: {
        "gameweek": [
            { team_h, team_a, team_h_difficulty, team_a_difficulty, ... }
        ]
    }
}
```

### `importedPlayerDetails`
```javascript
{
    "playerId": {
        history: [
            {
                round, // gameweek
                opponent_team,
                was_home,
                minutes,
                goals_scored,
                assists,
                clean_sheets,
                goals_conceded,
                saves,
                bonus,
                bps,
                yellow_cards,
                red_cards,
                defensive_contribution, // DC per game
                total_points
            }
        ]
    }
}
```

### `batchAnalysisCache`
```javascript
{
    teamBatchMap: { teamId: batchId },
    teamStats: {
        teamId: {
            overall: { goalsFor, goalsAgainst, cleanSheets, games },
            vsBatch: {
                1: { goalsFor, goalsAgainst, cleanSheets, games },
                2: { ... },
                ...
            }
        }
    },
    playerStats: {
        playerId: {
            name, position, teamId,
            overall: {
                goals, assists, cleanSheets, goalsConceded,
                saves, bonus, bps, yellowCards, redCards,
                dc, dcBonusHits, minutes, games, games45plus,
                // Per-game averages:
                goalsPerGame, assistsPerGame, dcPerGame, csPerGame, ...
            },
            vsBatch: {
                1: { /* same structure */ },
                2: { ... },
                ...
            }
        }
    },
    leagueAverages: {
        goalsPerGame, // league-wide
        goalsConcededPerGame,
        csPerGame,
        ...
    },
    plStandings: [...],  // Real PL standings
    standingsSource: 'football-data.org' | 'calculated',
    lastComputed: timestamp
}
```

---

## Key Functions Reference

### Prediction Functions

| Function | Purpose | Location |
|----------|---------|----------|
| `predictPlayerPointsBatch(playerId, opponentTeamId, isHome, gameweek)` | Core prediction for single player | ~line 11206 |
| `calculateGWPredictions(gameweek)` | Predictions for all teams in a GW | ~line 11496 |
| `applyBayesianBlend(batchStat, overallStat, batchGames, priorWeight)` | Blends stats for small samples | ~line 11192 |
| `crossReferenceWithOpponent(...)` | Adjusts for opponent strength | ~line 11170 |

### Lineup Selection

| Function | Purpose | Location |
|----------|---------|----------|
| `selectOptimalLineup(playerPredictions)` | Selects best 11 with valid formation | ~line 11730 |

Formation constraints: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD

### H2H Probability

| Function | Purpose | Location |
|----------|---------|----------|
| `calculateTeamUncertainty(teamPred)` | Calculates σ based on confidence | ~line 11784 |
| `normalCDF(x)` | Standard normal CDF approximation | ~line 11810 |
| `calculateH2HWinProbability(pts1, pts2, pred1, pred2)` | Statistical win probability | ~line 11830 |

### Batch Analysis

| Function | Purpose | Location |
|----------|---------|----------|
| `initBatchAnalysis()` | Main init, orchestrates all batch calculations | ~line 10870 |
| `buildBatchMap()` | Maps teams to batches by rank | ~line 10920 |
| `calculateTeamBatchStats()` | Team-level goals/CS per batch | ~line 10970 |
| `calculatePlayerBatchStats()` | Player-level stats per batch | ~line 11052 |
| `getBestAvailableStandings()` | Fetches real PL standings | ~line 10730 |

### PL Match Predictor

| Function | Purpose | Location |
|----------|---------|----------|
| `predictMatchScore(homeTeam, awayTeam)` | Predicts PL match xG | ~line 12350 |
| `calculateMatchupPrediction()` | UI handler for match predictor | ~line 12300 |

---

## External APIs

### 1. FPL Draft API (`draft.premierleague.com`)
Fetched via bookmarklet (to bypass CORS):
```
/api/league/{leagueId}/details
/api/league/{leagueId}/element-status
/api/bootstrap-static
/api/entry/{entryId}/public
/api/element-summary/{elementId}
/api/draft/league/{leagueId}/transactions
```

### 2. Football-Data.org API (for real PL standings)
```
https://api.football-data.org/v4/competitions/PL/standings
```
- Requires free API key (sign up at football-data.org)
- User enters key in analyzer settings
- Uses CORS proxies as fallback (`corsproxy.io`, `allorigins.win`)

---

## How to Use

### Step 1: Generate the Bookmarklet
1. Open `fpl_fixture_analyzer.html` in your browser
2. Enter your FPL Draft League ID
3. Click "Generate Bookmarklet"
4. Drag the bookmarklet to your bookmarks bar

### Step 2: Fetch Your League Data
1. Navigate to [FPL Draft](https://draft.premierleague.com)
2. Log in to your account
3. Click the bookmarklet
4. Wait for data collection (~30 seconds)
5. Download or copy the JSON data

### Step 3: Import Data
1. Return to the analyzer
2. Upload the JSON file or paste data
3. Click "Import Combined Data"

### Step 4: (Optional) Add PL Standings API Key
1. Sign up at [football-data.org](https://www.football-data.org/client/register)
2. Copy your free API key
3. Paste in the "PL Standings API Key" section
4. Click "Test & Fetch Standings"

### Step 5: Analyze!
- **GW Simulation**: View predictions, H2H matchups, player breakdowns
- **PL Stats**: Real standings, match predictor
- **Fixtures**: Interactive fixture difficulty grid
- **Trade System**: Get smart trade suggestions

---

## Files

| File | Description |
|------|-------------|
| `fpl_fixture_analyzer.html` | Main application (single-file, self-contained) |
| `README.md` | This documentation |
| `unified_wishlist.json` | Combined player wishlist data |
| `gk_wishlist.json` | Goalkeeper rankings |
| `def_wishlist.json` | Defender rankings |
| `mid_wishlist.json` | Midfielder rankings |
| `fwd_wishlist.json` | Forward rankings |
| `fpl_predictor/` | Python prediction scripts (optional) |

---

## AI Agent Guidance

### Understanding the Codebase

1. **Single-file architecture**: Everything is in `fpl_fixture_analyzer.html`
2. **No build process**: Edit HTML directly, refresh browser to test
3. **Global state**: Main data in `importedLeagueData`, `importedBootstrap`, `importedPlayerDetails`
4. **Computed cache**: Batch analysis results in `batchAnalysisCache`

### Adding New Features

1. **New prediction factors**: Modify `predictPlayerPointsBatch()` (~line 11206)
2. **New stats to track**: Add to `calculatePlayerBatchStats()` (~line 11052)
3. **New UI tab**: Add HTML in tab structure, JS render function
4. **New scoring rules**: Update `BATCH_CONFIG.fplScoringRules`

### Important Constraints

1. **Formation rules**: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD (enforced in `selectOptimalLineup`)
2. **DC thresholds**: DEF/GK need 10+, MID/FWD need 12+ for 2pt bonus
3. **Defensive stats**: Only count for games with 45+ minutes (`minMinutesForDefensiveStats`)
4. **Bayesian blending**: Use `applyBayesianBlend()` for batch stats with small samples

### Testing Recommendations

1. **Console logging**: Check browser console for `[Standings]`, `[Batch]`, `[Predictions]` logs
2. **Data validation**: Verify `batchAnalysisCache` has expected structure
3. **Edge cases**: Test with players who have few games vs a batch
4. **Formation validation**: Ensure optimal 11 always has valid formation

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| All predictions 0 | Batch analysis not initialized | Ensure `initBatchAnalysis()` called |
| Undefined players | Trade-ins not in bootstrap | Filtered out in `calculateGWPredictions` |
| Invalid formation | Not enough players at position | Check `selectOptimalLineup` constraints |
| CORS errors | API blocked | Use CORS proxy or bookmarklet approach |
| Wrong standings | Using calculated fallback | Add football-data.org API key |

### Code Style

- Use `const`/`let`, not `var`
- Use template literals for HTML strings
- Use `?.` optional chaining for nullable objects
- Round display values to 1 decimal: `Math.round(x * 10) / 10`
- Log important operations: `console.log('[Module] Message')`

---

## Privacy

All data is processed locally in your browser. No data is sent to any external servers except:
- Football-data.org API (only if you add an API key)
- CORS proxies (only for API fallback)

---

## License

MIT License - Feel free to use and modify for your FPL Draft leagues!

---

## Contributing

Issues and PRs welcome at [github.com/ilayasayag/FplAnalyzer](https://github.com/ilayasayag/FplAnalyzer)
