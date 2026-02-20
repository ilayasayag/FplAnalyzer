# FPL Analyzer Database Schema

This document describes the DuckDB database schema used by the FPL Draft Analyzer.

## Overview

The database serves as the single source of truth for all FPL data, including:
- Premier League teams and players
- Player historical performance (gameweek-by-gameweek)
- FPL Draft league data (entries, squads, matches)
- Transactions (waivers and trades)
- Predicted lineups (from web scraping)

## Core Tables

### Premier League Data

#### `pl_teams`
Stores Premier League team information and strength ratings.

**Purpose**: Reference data for all Premier League teams with their strength metrics.

**Updated When**: Bootstrap import from FPL API data.

**Depends On**: None (root table).

**Columns**:
- `id` (INTEGER, PK): FPL team ID
- `name` (VARCHAR): Full team name (e.g., "Arsenal")
- `short_name` (VARCHAR(3)): 3-letter code (e.g., "ARS")
- `code` (INTEGER): FPL team code
- Strength ratings: `strength_overall_home/away`, `strength_attack_home/away`, `strength_defence_home/away`
- Standings: `position`, `played`, `won`, `drawn`, `lost`, `goals_for`, `goals_against`, `points`, `clean_sheets`
- `batch_id` (INTEGER): Team tier (1-5) for fixture difficulty grouping
- `updated_at` (TIMESTAMP): Last update time

**Relationships**:
- Referenced by: `pl_players.team_id`, `pl_fixtures.home_team_id`, `pl_fixtures.away_team_id`

---

#### `pl_players`
Stores all Premier League player data and season totals.

**Purpose**: Master list of all FPL-eligible players with their stats.

**Updated When**: Bootstrap import from FPL API data.

**Depends On**: `pl_teams`

**Columns**:
- `id` (INTEGER, PK): FPL player ID
- `web_name` (VARCHAR): Display name (e.g., "Salah")
- `first_name`, `second_name` (VARCHAR): Full name components
- `team_id` (INTEGER, FK → pl_teams): Current team
- `position` (INTEGER): 1=GK, 2=DEF, 3=MID, 4=FWD
- `status` (VARCHAR(1)): a/d/i/s/u (available/doubtful/injured/suspended/unavailable)
- `news` (TEXT), `news_added` (TIMESTAMP): Injury/availability news
- `chance_of_playing` (INTEGER): 0-100 percentage
- Season totals: `total_points`, `goals_scored`, `assists`, `clean_sheets`, `saves`, `bonus`, `minutes`, `yellow_cards`, `red_cards`
- Form metrics: `form`, `points_per_game`, `ict_index`, `influence`, `creativity`, `threat`
- Expected stats: `expected_goals`, `expected_assists`, `expected_goal_involvements`
- `draft_rank` (INTEGER): Draft rank
- `updated_at` (TIMESTAMP)

**Relationships**:
- References: `pl_teams.id`
- Referenced by: `player_gameweeks.player_id`, `fpl_squads.player_id`, `predicted_lineups.player_id`

---

#### `player_gameweeks`
**CRITICAL FOR PREDICTIONS**: Stores per-gameweek performance history for each player.

**Purpose**: Historical performance data used for form analysis and predictions.

**Updated When**: Player details import from FPL API data.

**Depends On**: `pl_players`, `pl_teams`

**Columns**:
- `player_id` (INTEGER, FK → pl_players): Player
- `gameweek` (INTEGER): Gameweek number
- `opponent_id` (INTEGER, FK → pl_teams): Opponent faced
- `was_home` (BOOLEAN): Home/away fixture
- `minutes` (INTEGER), `started` (BOOLEAN): Playing time
- Points breakdown: `total_points`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `saves`, `bonus`, `penalties_saved`, `penalties_missed`, `yellow_cards`, `red_cards`, `own_goals`
- Expected stats: `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`
- Performance metrics: `ict_index`, `influence`, `creativity`, `threat`, `bps` (bonus point system)
- Draft-specific: `selected` (selected by FPL manager), `transfers_in`, `transfers_out`, `value`
- `kickoff_time` (TIMESTAMP)
- PRIMARY KEY: `(player_id, gameweek)`

**Relationships**:
- References: `pl_players.id`, `pl_teams.id`

**Usage**:
- Form calculation: Recent N gameweeks
- Opponent-based predictions: Performance vs similar teams
- Home/away analysis: Venue-specific performance
- Batch analysis: Performance against team tiers

---

#### `pl_fixtures`
Stores Premier League fixture schedule.

**Purpose**: Upcoming and completed fixtures for prediction and analysis.

**Updated When**: Bootstrap import from FPL API data.

**Depends On**: `pl_teams`

**Columns**:
- `id` (INTEGER, PK): FPL fixture ID
- `gameweek` (INTEGER): Gameweek number
- `home_team_id`, `away_team_id` (INTEGER, FK → pl_teams): Teams
- `home_score`, `away_score` (INTEGER): Final scores (NULL if not played)
- `finished` (BOOLEAN): Match completed
- `kickoff_time` (TIMESTAMP): Scheduled kickoff
- `home_fdr`, `away_fdr` (INTEGER): Fixture Difficulty Rating (1-5)
- `updated_at` (TIMESTAMP)

**Relationships**:
- References: `pl_teams.id`

---

### FPL Draft League Data

#### `fpl_league`
Stores FPL Draft league information.

**Purpose**: League configuration and settings.

**Updated When**: League import from bookmarklet JSON.

**Depends On**: None

**Columns**:
- `id` (INTEGER, PK): League ID
- `name` (VARCHAR): League name
- `admin_entry` (INTEGER): League admin's entry ID
- `scoring` (VARCHAR(1)): 'h' for H2H scoring
- `start_event`, `stop_event` (INTEGER): Season range
- `draft_status`, `transaction_mode` (VARCHAR): League settings
- `updated_at` (TIMESTAMP)

---

#### `fpl_entries`
Stores FPL Draft league entries (teams/managers).

**Purpose**: List of all managers in the league.

**Updated When**: League import from bookmarklet JSON.

**Depends On**: None (independent root for FPL side)

**Columns**:
- `id` (INTEGER, PK): Auto-increment ID
- `entry_id` (INTEGER, UNIQUE): FPL entry ID
- `entry_name` (VARCHAR): Team name
- `player_first_name`, `player_last_name` (VARCHAR): Manager name
- `short_name` (VARCHAR(2)): 2-letter abbreviation
- `waiver_pick` (INTEGER): Current waiver priority
- `joined_time` (TIMESTAMP)

**Relationships**:
- Referenced by: `fpl_squads.entry_id`, `fpl_transactions.entry_id`, `fpl_matches.league_entry_1/2`

---

#### `fpl_squads`
**CRITICAL**: Stores squad ownership per gameweek. This is the current state of who owns which players.

**Purpose**: Track squad composition over time. Used for ownership checks, free agent identification, and squad analysis.

**Updated When**: 
- Initial import from squads JSON (baseline)
- **Transaction processing** (add/remove players based on waivers/trades)
- Updated incrementally each gameweek

**Depends On**: `fpl_entries`, `pl_players`

**Columns**:
- `entry_id` (INTEGER, FK → fpl_entries): Owner
- `player_id` (INTEGER, FK → pl_players): Player owned
- `gameweek` (INTEGER): When owned
- `squad_position` (INTEGER): 1-15 position in squad
- `is_captain`, `is_vice_captain` (BOOLEAN): Captain flags
- PRIMARY KEY: `(entry_id, player_id, gameweek)`

**Relationships**:
- References: `fpl_entries.entry_id`, `pl_players.id`
- Updates: `element_status` (derived)

**Data Integrity Rules**:
- Each entry must have EXACTLY 15 players per gameweek
- Position constraints: 2 GK, 5 DEF, 5 MID, 3 FWD
- No player can be owned by multiple entries in same gameweek

**Update Pattern**:
```
Initial Squad (from JSON) → Apply Transactions → Current Squad
```

---

#### `fpl_transactions`
Stores all waiver and trade transactions.

**Purpose**: Historical record of player acquisitions and drops.

**Updated When**: Transaction import from bookmarklet JSON.

**Depends On**: `fpl_entries`, `pl_players`

**Columns**:
- `id` (INTEGER, PK): Transaction ID
- `entry_id` (INTEGER, FK → fpl_entries): Entry making transaction
- `player_in` (INTEGER, FK → pl_players): Player acquired (NULL for drops)
- `player_out` (INTEGER, FK → pl_players): Player dropped (NULL for adds)
- `transaction_type` (VARCHAR(20)): 'waiver', 'trade', etc.
- `gameweek` (INTEGER): When transaction occurred
- `priority` (INTEGER): Waiver priority
- `result` (VARCHAR(10)): 'success', 'pending', 'failed'
- `added_time` (TIMESTAMP): When transaction was submitted

**Relationships**:
- References: `fpl_entries.entry_id`, `pl_players.id`
- Used to update: `fpl_squads`

**Processing Logic**:
Transactions are applied in chronological order (`added_time`) to reconstruct accurate squad state:
1. For each successful transaction with `player_out`: Remove from squad
2. For each successful transaction with `player_in`: Add to squad
3. Validate: Squad still has 15 players and correct positions

---

#### `fpl_matches`
Stores H2H match results.

**Purpose**: Head-to-head match history for league standings.

**Updated When**: Matches import from bookmarklet JSON.

**Depends On**: `fpl_entries`

**Columns**:
- `id` (INTEGER, PK): Match ID
- `gameweek` (INTEGER): Gameweek of match
- `league_entry_1`, `league_entry_2` (INTEGER, FK → fpl_entries): Competing entries
- `entry_1_points`, `entry_2_points` (INTEGER): Points scored
- `entry_1_win`, `entry_2_win` (INTEGER): Win count (0, 1, or draw)
- `finished` (BOOLEAN): Match completed

---

#### `element_status`
**DERIVED TABLE**: Current ownership and availability status for each player.

**Purpose**: Quick lookup for "who owns this player?" and free agent identification.

**Updated When**: Automatically synced after `fpl_squads` changes.

**Depends On**: `fpl_squads`

**Columns**:
- `element_id` (INTEGER, PK, FK → pl_players): Player
- `owner_entry_id` (INTEGER, FK → fpl_entries): Current owner (NULL = free agent)
- `status` (VARCHAR(1)): 'a' = available
- `in_squad` (BOOLEAN): TRUE if owned
- `updated_at` (TIMESTAMP)

**Sync Logic**:
```sql
-- After fpl_squads update for gameweek X:
UPDATE element_status
SET owner_entry_id = (
    SELECT entry_id FROM fpl_squads 
    WHERE player_id = element_id AND gameweek = X
),
in_squad = (owner_entry_id IS NOT NULL)
```

---

### Supporting Tables

#### `fixture_difficulty`
Custom/weighted FDR calculations.

**Purpose**: Store custom fixture difficulty ratings that override official FDR.

**Updated When**: Manual updates or calculation scripts.

**Columns**:
- `team_id`, `gameweek` (PK): Team and week
- `opponent_id` (INTEGER): Opponent
- `is_home` (BOOLEAN)
- `official_fdr`, `weighted_fdr`, `manual_override` (DECIMAL): Different FDR sources

---

#### `wishlist_players`
External player rankings (e.g., from analyst sites).

**Purpose**: Import and track player rankings from external sources.

**Updated When**: Manual import or scraping scripts.

**Columns**:
- `id` (INTEGER, PK)
- `fpl_id` (INTEGER, FK → pl_players): Link to player
- `name`, `team`, `position`: Player info
- `rank`, `score`: Ranking data
- `source` (VARCHAR): Data source
- `updated_at`

---

#### `predicted_lineups`
**WEB-SCRAPED DATA**: Predicted starting lineups from multiple sources.

**Purpose**: Store and aggregate lineup predictions for rotation risk analysis.

**Updated When**: Scraper runs (typically daily or before gameweek deadline).

**Depends On**: `pl_players`, `pl_teams`

**Columns**:
- `player_id` (INTEGER, FK → pl_players)
- `team_id` (INTEGER, FK → pl_teams)
- `gameweek` (INTEGER)
- `fixture_id` (INTEGER, FK → pl_fixtures): Specific fixture
- `start_probability` (FLOAT): 0.0-1.0 chance of starting
- `bench_probability` (FLOAT): Probability of bench appearance
- `injured`, `suspended`, `doubtful` (BOOLEAN): Status flags
- `injury_details` (TEXT)
- `sources_count` (INTEGER): Number of sources predicting
- `sources_data` (TEXT): JSON with per-source probabilities
- `validation_note` (TEXT): Lineup validation warnings
- `last_updated` (TIMESTAMP)
- PRIMARY KEY: `(player_id, gameweek)`

**Multi-Source Aggregation**:
- Combines predictions from RotoWire, Fantasy Football Scout, etc.
- Weighted average based on source reliability
- Deduplicates players from different sources by `player_id`

---

#### `unmatched_players`
Players found by scrapers but not in FPL database.

**Purpose**: Track players that couldn't be matched for future import.

**Updated When**: Scraper runs encounter unknown player names.

**Columns**:
- `id` (INTEGER, PK)
- `scraped_name` (VARCHAR): Original name from source
- `team_code` (VARCHAR): Team abbreviation
- `position_code` (VARCHAR): Position
- `first_seen`, `last_seen` (TIMESTAMP)
- `occurrences` (INTEGER): Times seen
- `sources` (TEXT): Which sources mentioned this player

---

### Cache & Configuration

#### `cache`
General-purpose cache for computed values.

**Purpose**: Store expensive query results to avoid recomputation.

**Columns**:
- `key` (VARCHAR, PK): Cache key
- `value` (TEXT): JSON-encoded cached data
- `computed_at`, `expires_at` (TIMESTAMP): Validity
- `gameweek` (INTEGER): Associated gameweek

**Invalidation Rules**:
- `squad:*` keys: Invalidate when `fpl_squads` changes
- `prediction:*` keys: Invalidate when predictions run
- Gameweek-specific: Clear when gameweek advances

---

#### `user_preferences`
User settings and bookmarks.

**Purpose**: Store application state and user preferences.

**Columns**:
- `key` (VARCHAR, PK): Setting key
- `value` (TEXT): Setting value
- `updated_at` (TIMESTAMP)

**Key Settings**:
- `last_transaction_bookmark`: Last processed transaction ID (for incremental updates)
- `current_gameweek`: Current active gameweek
- `auto_sync_enabled`: Auto-sync preference

---

## Data Flow Diagrams

### Import Flow

```
JSON File (fpl_league_data_YYYY-MM-DD.json)
    ↓
DataImporter.import_from_json()
    ↓
    ├─→ _import_teams() → pl_teams
    ├─→ _import_players() → pl_players
    ├─→ _import_player_history() → player_gameweeks
    ├─→ _import_fixtures() → pl_fixtures
    ├─→ _import_entries() → fpl_entries
    ├─→ _import_squads() → SquadProcessor → fpl_squads + element_status
    ├─→ _import_matches() → fpl_matches
    └─→ _import_transactions() → fpl_transactions
```

### Squad Reconstruction Flow

```
1. Initial Squad Import (from JSON)
   ↓
   fpl_squads (baseline for gameweek N)
   
2. Transaction Processing
   ↓
   Read fpl_transactions (sorted by added_time)
   ↓
   For each transaction:
     - Remove player_out from entry's squad
     - Add player_in to entry's squad
   ↓
   Updated fpl_squads (current state)
   
3. Element Status Sync
   ↓
   element_status.owner_entry_id = fpl_squads.entry_id
```

### Prediction Flow

```
1. User Requests Predictions
   ↓
2. Check Cache (cache table)
   ↓
3. If cache miss:
   ├─→ Load player data (pl_players, player_gameweeks)
   ├─→ Load fixtures (pl_fixtures)
   ├─→ Load predicted lineups (predicted_lineups)
   ├─→ Calculate expected points
   └─→ Store in cache
   ↓
4. Return predictions
```

---

## Maintenance & Integrity

### Critical Relationships to Maintain

1. **Squad Ownership Consistency**:
   - `fpl_squads` must always have exactly 15 players per entry per gameweek
   - `element_status` must reflect current `fpl_squads` state
   - No player can appear in multiple squads for same gameweek

2. **Transaction Processing Order**:
   - Transactions MUST be applied in chronological order
   - Bookmark tracking prevents reprocessing same transactions

3. **Gameweek History Completeness**:
   - `player_gameweeks` should have entries for all gameweeks up to current
   - Missing gameweeks indicate player didn't play (0 minutes)

### Update Triggers

| Data Change | Tables to Update | Dependencies |
|-------------|------------------|--------------|
| New JSON import | All tables | Full cascade |
| New transactions | `fpl_transactions` → `fpl_squads` → `element_status` | Sequential |
| Scraper run | `predicted_lineups`, `unmatched_players` | Independent |
| Gameweek advance | `cache` (clear gameweek-specific) | All queries |

### Validation Queries

Check squad integrity:
```sql
-- Each entry should have exactly 15 players
SELECT entry_id, COUNT(*) as player_count
FROM fpl_squads
WHERE gameweek = 21
GROUP BY entry_id
HAVING COUNT(*) != 15;
```

Check element_status sync:
```sql
-- Compare ownership in fpl_squads vs element_status
SELECT p.web_name, fs.entry_id, es.owner_entry_id
FROM pl_players p
LEFT JOIN fpl_squads fs ON p.id = fs.player_id AND fs.gameweek = 21
LEFT JOIN element_status es ON p.id = es.element_id
WHERE fs.entry_id != es.owner_entry_id OR (fs.entry_id IS NULL AND es.owner_entry_id IS NOT NULL);
```

---

## Performance Considerations

### Indexes (Recommended)

```sql
-- Primary lookups
CREATE INDEX idx_player_gameweeks_player ON player_gameweeks(player_id, gameweek);
CREATE INDEX idx_fpl_squads_entry ON fpl_squads(entry_id, gameweek);
CREATE INDEX idx_predicted_lineups_gameweek ON predicted_lineups(gameweek, team_id);

-- Joins
CREATE INDEX idx_players_team ON pl_players(team_id);
CREATE INDEX idx_fixtures_gameweek ON pl_fixtures(gameweek);
```

### Query Patterns

- **Avoid**: Full table scans on `player_gameweeks` (796 players × 38 GWs = 30K+ rows)
- **Use**: Filtered queries with `player_id` and `gameweek` range
- **Cache**: Expensive aggregations (form calculations, predictions) in `cache` table

---

## Schema Version

**Version**: 1.0  
**Last Updated**: 2026-01-17  
**DuckDB Version**: 0.9.x+
