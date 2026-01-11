"""
DuckDB Database Module for FPL Analyzer

Provides database connection management and schema initialization.
Uses DuckDB for high-performance analytical queries on FPL data.
"""

import duckdb
import os
from pathlib import Path
from typing import Optional
import threading
import atexit

# Database file location (project root)
DB_PATH = Path(__file__).parent.parent.parent / "fpl_data.duckdb"

# Global connection (DuckDB is thread-safe for read operations)
_global_connection: Optional[duckdb.DuckDBPyConnection] = None
_lock = threading.Lock()
_schema_initialized = False


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Get the global DuckDB connection.
    
    DuckDB handles thread-safety internally for read operations.
    We use a single connection to avoid lock conflicts.
    
    Returns:
        DuckDB connection
    """
    global _global_connection, _schema_initialized
    
    with _lock:
        if _global_connection is None:
            _global_connection = duckdb.connect(str(DB_PATH))
            
            # Initialize schema on first connection only
            if not _schema_initialized:
                _init_schema_internal(_global_connection)
                _schema_initialized = True
                
        return _global_connection


def close_connection():
    """Close the global connection if it exists."""
    global _global_connection, _schema_initialized
    
    with _lock:
        if _global_connection is not None:
            try:
                _global_connection.close()
            except:
                pass
            _global_connection = None
            _schema_initialized = False


# Register cleanup on exit
atexit.register(close_connection)


def _init_schema_internal(con: duckdb.DuckDBPyConnection):
    """
    Internal: Initialize the database schema.
    
    Creates all tables if they don't exist. Called automatically on first connection.
    """
    pass  # Schema creation follows below


def init_schema(con: Optional[duckdb.DuckDBPyConnection] = None):
    """
    Initialize the database schema.
    
    Creates all tables if they don't exist. Safe to call multiple times.
    
    Args:
        con: Optional connection to use. If None, gets global connection.
    """
    if con is None:
        con = get_connection()
    _init_schema_internal(con)


def _init_schema_internal(con: duckdb.DuckDBPyConnection):
    
    # Premier League Teams
    con.execute("""
        CREATE TABLE IF NOT EXISTS pl_teams (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            short_name VARCHAR(3),
            code INTEGER,
            -- Strength ratings from FPL
            strength_overall_home INTEGER,
            strength_overall_away INTEGER,
            strength_attack_home INTEGER,
            strength_attack_away INTEGER,
            strength_defence_home INTEGER,
            strength_defence_away INTEGER,
            -- Current standings
            position INTEGER,
            played INTEGER DEFAULT 0,
            won INTEGER DEFAULT 0,
            drawn INTEGER DEFAULT 0,
            lost INTEGER DEFAULT 0,
            goals_for INTEGER DEFAULT 0,
            goals_against INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            clean_sheets INTEGER DEFAULT 0,
            -- Batch classification (1-5 based on position)
            batch_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Premier League Players
    con.execute("""
        CREATE TABLE IF NOT EXISTS pl_players (
            id INTEGER PRIMARY KEY,
            web_name VARCHAR NOT NULL,
            first_name VARCHAR,
            second_name VARCHAR,
            team_id INTEGER,
            position INTEGER,  -- 1=GK, 2=DEF, 3=MID, 4=FWD
            status VARCHAR(1) DEFAULT 'a',  -- a/d/i/s/u
            news TEXT,
            news_added TIMESTAMP,
            chance_of_playing INTEGER,
            -- Season totals
            total_points INTEGER DEFAULT 0,
            goals_scored INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            clean_sheets INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            bonus INTEGER DEFAULT 0,
            minutes INTEGER DEFAULT 0,
            yellow_cards INTEGER DEFAULT 0,
            red_cards INTEGER DEFAULT 0,
            -- Form and rankings
            form DECIMAL(4,2),
            points_per_game DECIMAL(4,2),
            ict_index DECIMAL(6,2),
            influence DECIMAL(6,2),
            creativity DECIMAL(6,2),
            threat DECIMAL(6,2),
            -- Expected stats
            expected_goals DECIMAL(6,2),
            expected_assists DECIMAL(6,2),
            expected_goal_involvements DECIMAL(6,2),
            -- Draft specific
            draft_rank INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Player Gameweek History (CRITICAL for predictions)
    con.execute("""
        CREATE TABLE IF NOT EXISTS player_gameweeks (
            player_id INTEGER NOT NULL,
            gameweek INTEGER NOT NULL,
            opponent_id INTEGER,
            was_home BOOLEAN,
            -- Playing time
            minutes INTEGER DEFAULT 0,
            started BOOLEAN,
            -- Points breakdown
            total_points INTEGER DEFAULT 0,
            goals_scored INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            clean_sheets INTEGER DEFAULT 0,
            goals_conceded INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            bonus INTEGER DEFAULT 0,
            penalties_saved INTEGER DEFAULT 0,
            penalties_missed INTEGER DEFAULT 0,
            yellow_cards INTEGER DEFAULT 0,
            red_cards INTEGER DEFAULT 0,
            own_goals INTEGER DEFAULT 0,
            -- Expected stats
            expected_goals DECIMAL(4,2),
            expected_assists DECIMAL(4,2),
            expected_goal_involvements DECIMAL(4,2),
            expected_goals_conceded DECIMAL(4,2),
            -- BPS breakdown
            bps INTEGER DEFAULT 0,
            -- Match detail string (e.g., "MCI(H) 2-1")
            detail VARCHAR(50),
            PRIMARY KEY (player_id, gameweek)
        )
    """)
    
    # PL Fixtures
    con.execute("""
        CREATE TABLE IF NOT EXISTS pl_fixtures (
            id INTEGER PRIMARY KEY,
            gameweek INTEGER,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            finished BOOLEAN DEFAULT FALSE,
            kickoff_time TIMESTAMP,
            -- FDR ratings
            home_fdr INTEGER,
            away_fdr INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # FPL Draft League
    con.execute("""
        CREATE TABLE IF NOT EXISTS fpl_league (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            admin_entry INTEGER,
            scoring VARCHAR(1),  -- 'h' for H2H
            start_event INTEGER,
            stop_event INTEGER,
            draft_status VARCHAR(20),
            transaction_mode VARCHAR(20),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # FPL League Entries (Teams in your draft league)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fpl_entries (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER UNIQUE NOT NULL,
            entry_name VARCHAR NOT NULL,
            player_first_name VARCHAR,
            player_last_name VARCHAR,
            short_name VARCHAR(2),
            waiver_pick INTEGER,
            joined_time TIMESTAMP
        )
    """)
    
    # Squad Ownership (per gameweek for history tracking)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fpl_squads (
            entry_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            gameweek INTEGER NOT NULL,
            squad_position INTEGER,
            is_captain BOOLEAN DEFAULT FALSE,
            is_vice_captain BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (entry_id, player_id, gameweek)
        )
    """)
    
    # H2H Matches
    con.execute("""
        CREATE TABLE IF NOT EXISTS fpl_matches (
            id INTEGER PRIMARY KEY,
            gameweek INTEGER NOT NULL,
            league_entry_1 INTEGER,
            league_entry_2 INTEGER,
            entry_1_points INTEGER,
            entry_2_points INTEGER,
            entry_1_win INTEGER,
            entry_2_win INTEGER,
            finished BOOLEAN DEFAULT FALSE
        )
    """)
    
    # Transactions (Waivers/Trades)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fpl_transactions (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            player_in INTEGER,
            player_out INTEGER,
            transaction_type VARCHAR(20),
            gameweek INTEGER,
            priority INTEGER,
            result VARCHAR(10),
            added_time TIMESTAMP
        )
    """)
    
    # Element Status (FPL availability/ownership)
    con.execute("""
        CREATE TABLE IF NOT EXISTS element_status (
            element_id INTEGER PRIMARY KEY,
            owner_entry_id INTEGER,
            status VARCHAR(1),
            in_squad BOOLEAN,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Fixture Difficulty Ratings (custom/weighted)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fixture_difficulty (
            team_id INTEGER NOT NULL,
            gameweek INTEGER NOT NULL,
            opponent_id INTEGER,
            is_home BOOLEAN,
            official_fdr INTEGER,
            weighted_fdr DECIMAL(3,2),
            manual_override DECIMAL(3,2),
            PRIMARY KEY (team_id, gameweek)
        )
    """)
    
    # Wishlist Players (external rankings)
    con.execute("""
        CREATE TABLE IF NOT EXISTS wishlist_players (
            id INTEGER PRIMARY KEY,
            fpl_id INTEGER,
            name VARCHAR NOT NULL,
            team VARCHAR,
            position VARCHAR(3),
            rank INTEGER,
            score DECIMAL(5,2),
            source VARCHAR(50),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # User Preferences
    con.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Computed Cache
    con.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            gameweek INTEGER
        )
    """)
    
    # Create indexes for performance
    _create_indexes(con)
    
    print(f"[Database] Schema initialized at {DB_PATH}")


def _create_indexes(con: duckdb.DuckDBPyConnection):
    """Create indexes for common query patterns."""
    
    indexes = [
        ("idx_player_gameweeks_player", "player_gameweeks", "player_id"),
        ("idx_player_gameweeks_gw", "player_gameweeks", "gameweek"),
        ("idx_player_gameweeks_opponent", "player_gameweeks", "opponent_id"),
        ("idx_fpl_squads_entry", "fpl_squads", "entry_id"),
        ("idx_fpl_squads_player", "fpl_squads", "player_id"),
        ("idx_fpl_squads_gw", "fpl_squads", "gameweek"),
        ("idx_pl_players_team", "pl_players", "team_id"),
        ("idx_pl_players_position", "pl_players", "position"),
        ("idx_element_status_owner", "element_status", "owner_entry_id"),
        ("idx_fixture_difficulty_gw", "fixture_difficulty", "gameweek"),
        ("idx_pl_fixtures_gw", "pl_fixtures", "gameweek"),
        ("idx_fpl_matches_gw", "fpl_matches", "gameweek"),
    ]
    
    for idx_name, table, column in indexes:
        try:
            con.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
        except Exception as e:
            # Index might already exist or table might not exist yet
            pass


def get_db_stats(con: Optional[duckdb.DuckDBPyConnection] = None) -> dict:
    """
    Get database statistics.
    
    Returns:
        Dictionary with table row counts and database info
    """
    if con is None:
        con = get_connection()
    
    tables = [
        'pl_teams', 'pl_players', 'player_gameweeks', 'pl_fixtures',
        'fpl_league', 'fpl_entries', 'fpl_squads', 'fpl_matches',
        'fpl_transactions', 'element_status', 'fixture_difficulty',
        'wishlist_players', 'cache'
    ]
    
    stats = {
        'db_path': str(DB_PATH),
        'db_exists': DB_PATH.exists(),
        'tables': {}
    }
    
    for table in tables:
        try:
            result = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats['tables'][table] = result[0] if result else 0
        except:
            stats['tables'][table] = 0
    
    return stats


def reset_database():
    """
    Drop all tables and recreate schema.
    
    WARNING: This will delete all data!
    """
    con = get_connection()
    
    tables = [
        'cache', 'user_preferences', 'wishlist_players', 'fixture_difficulty',
        'element_status', 'fpl_transactions', 'fpl_matches', 'fpl_squads',
        'fpl_entries', 'fpl_league', 'pl_fixtures', 'player_gameweeks',
        'pl_players', 'pl_teams'
    ]
    
    for table in tables:
        try:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        except:
            pass
    
    init_schema(con)
    print("[Database] Schema reset complete")


# Schema is now initialized lazily on first get_connection() call
# This avoids lock issues during server startup
