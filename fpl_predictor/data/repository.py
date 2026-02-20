"""
Repository Layer for FPL Database

Provides data access objects (DAOs) for querying the DuckDB database.
All SQL queries are centralized here for maintainability.
"""

import duckdb
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass
from datetime import datetime

from .database import get_connection


class CacheManager:
    """
    Manages cache invalidation for database updates.
    
    When data changes in the database, related cache entries must be
    invalidated to prevent stale data from being served.
    """
    
    @staticmethod
    def invalidate_squads(con: duckdb.DuckDBPyConnection, gameweek: int):
        """
        Invalidate squad-related caches for a specific gameweek.
        
        Call this after:
        - Squad imports
        - Transaction processing
        - Squad updates
        
        Args:
            con: Database connection
            gameweek: Gameweek to invalidate
        """
        con.execute("""
            DELETE FROM cache 
            WHERE key LIKE 'squad:%' AND gameweek = ?
        """, [gameweek])
        print(f"[CacheManager] Invalidated squad caches for GW{gameweek}")
    
    @staticmethod
    def invalidate_predictions(con: duckdb.DuckDBPyConnection, gameweek: int):
        """
        Invalidate prediction-related caches for a specific gameweek.
        
        Call this after:
        - Player data updates
        - Fixture updates
        - Prediction recalculations
        
        Args:
            con: Database connection
            gameweek: Gameweek to invalidate
        """
        con.execute("""
            DELETE FROM cache 
            WHERE key LIKE 'prediction:%' AND gameweek = ?
        """, [gameweek])
        print(f"[CacheManager] Invalidated prediction caches for GW{gameweek}")
    
    @staticmethod
    def invalidate_player_history(con: duckdb.DuckDBPyConnection, player_id: int):
        """
        Invalidate caches for a specific player's history.
        
        Call this after:
        - Player gameweek data updates
        - Player stats recalculations
        
        Args:
            con: Database connection
            player_id: Player ID to invalidate
        """
        con.execute("""
            DELETE FROM cache 
            WHERE key LIKE ?
        """, [f'player:{player_id}:%'])
        print(f"[CacheManager] Invalidated caches for player {player_id}")
    
    @staticmethod
    def invalidate_all(con: duckdb.DuckDBPyConnection):
        """
        Clear all caches.
        
        Call this after:
        - Full data imports
        - Major schema changes
        - System maintenance
        
        Args:
            con: Database connection
        """
        count = con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        con.execute("DELETE FROM cache")
        print(f"[CacheManager] Cleared all caches ({count} entries)")
    
    @staticmethod
    def invalidate_gameweek(con: duckdb.DuckDBPyConnection, gameweek: int):
        """
        Invalidate all caches for a specific gameweek.
        
        Call this when:
        - Gameweek advances
        - Gameweek data is updated
        
        Args:
            con: Database connection
            gameweek: Gameweek to invalidate
        """
        count = con.execute("""
            SELECT COUNT(*) FROM cache WHERE gameweek = ?
        """, [gameweek]).fetchone()[0]
        
        con.execute("DELETE FROM cache WHERE gameweek = ?", [gameweek])
        print(f"[CacheManager] Invalidated all caches for GW{gameweek} ({count} entries)")
    
    @staticmethod
    def set_cache(
        con: duckdb.DuckDBPyConnection,
        key: str,
        value: str,
        gameweek: Optional[int] = None,
        ttl_minutes: int = 60
    ):
        """
        Set a cache value with optional TTL.
        
        Args:
            con: Database connection
            key: Cache key
            value: JSON-encoded value
            gameweek: Optional gameweek association
            ttl_minutes: Time-to-live in minutes
        """
        con.execute("""
            INSERT OR REPLACE INTO cache (
                key, value, computed_at, expires_at, gameweek
            ) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL ? MINUTE, ?)
        """, [key, value, ttl_minutes, gameweek])
    
    @staticmethod
    def get_cache(
        con: duckdb.DuckDBPyConnection,
        key: str
    ) -> Optional[str]:
        """
        Get a cache value if not expired.
        
        Args:
            con: Database connection
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        result = con.execute("""
            SELECT value FROM cache
            WHERE key = ? 
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """, [key]).fetchone()
        
        return result[0] if result else None


@dataclass
class PlayerDTO:
    """Data transfer object for player data."""
    id: int
    web_name: str
    first_name: Optional[str]
    second_name: Optional[str]
    team_id: int
    team_name: Optional[str] = None
    position: int = 3  # Default MID
    status: str = 'a'
    total_points: int = 0
    form: float = 0.0
    points_per_game: float = 0.0
    chance_of_playing: Optional[int] = None
    recent_form: Optional[float] = None
    games_played: Optional[int] = None


class PlayerRepository:
    """Repository for player-related queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_all(self, position: Optional[int] = None, 
                team_id: Optional[int] = None,
                status: Optional[str] = None,
                limit: int = 1000) -> List[Dict]:
        """Get all players with optional filters."""
        query = """
            SELECT 
                p.*,
                t.short_name as team_name,
                t.position as team_position
            FROM pl_players p
            LEFT JOIN pl_teams t ON p.team_id = t.id
            WHERE 1=1
        """
        params = []
        
        if position:
            query += " AND p.position = ?"
            params.append(position)
        
        if team_id:
            query += " AND p.team_id = ?"
            params.append(team_id)
        
        if status:
            query += " AND p.status = ?"
            params.append(status)
        
        query += " ORDER BY p.total_points DESC LIMIT ?"
        params.append(limit)
        
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_by_id(self, player_id: int) -> Optional[Dict]:
        """Get a single player by ID with full details."""
        result = self.con.execute("""
            SELECT 
                p.*,
                t.short_name as team_name,
                t.name as team_full_name,
                t.position as team_position,
                t.batch_id
            FROM pl_players p
            LEFT JOIN pl_teams t ON p.team_id = t.id
            WHERE p.id = ?
        """, [player_id]).fetchdf()
        
        if result.empty:
            return None
        return result.to_dict('records')[0]
    
    def get_with_history(self, player_id: int) -> Dict:
        """Get player with full gameweek history."""
        player = self.get_by_id(player_id)
        if not player:
            return {}
        
        history = self.con.execute("""
            SELECT 
                pg.*,
                pg.opponent_id as opponent_team,
                pg.gameweek as round,
                pg.gameweek as event,
                t.short_name as opponent_name
            FROM player_gameweeks pg
            LEFT JOIN pl_teams t ON pg.opponent_id = t.id
            WHERE pg.player_id = ?
            ORDER BY pg.gameweek ASC
        """, [player_id]).fetchdf().to_dict('records')
        
        player['history'] = history
        return player
    
    def get_player_vs_batch_stats(self, player_id: int) -> List[Dict]:
        """Get player performance breakdown by opponent batch."""
        return self.con.execute("""
            WITH opponent_batches AS (
                SELECT id, batch_id,
                    CASE batch_id
                        WHEN 1 THEN 'Elite (1-4)'
                        WHEN 2 THEN 'Strong (5-8)'
                        WHEN 3 THEN 'Mid (9-12)'
                        WHEN 4 THEN 'Weak (13-17)'
                        WHEN 5 THEN 'Bottom (18-20)'
                        ELSE 'Unknown'
                    END as batch_name
                FROM pl_teams
            )
            SELECT 
                ob.batch_name,
                ob.batch_id,
                COUNT(*) as games,
                ROUND(AVG(pg.total_points), 2) as avg_points,
                SUM(pg.goals_scored) as goals,
                SUM(pg.assists) as assists,
                SUM(pg.clean_sheets) as clean_sheets,
                ROUND(AVG(pg.minutes), 0) as avg_minutes,
                ROUND(AVG(pg.bonus), 2) as avg_bonus
            FROM player_gameweeks pg
            JOIN opponent_batches ob ON pg.opponent_id = ob.id
            WHERE pg.player_id = ? AND pg.minutes > 0
            GROUP BY ob.batch_id, ob.batch_name
            ORDER BY ob.batch_id
        """, [player_id]).fetchdf().to_dict('records')
    
    def get_player_form(self, player_id: int, last_n: int = 5) -> Dict:
        """Get player's recent form statistics."""
        result = self.con.execute("""
            SELECT 
                ROUND(AVG(total_points), 2) as avg_points,
                ROUND(AVG(minutes), 0) as avg_minutes,
                SUM(goals_scored) as total_goals,
                SUM(assists) as total_assists,
                SUM(clean_sheets) as clean_sheets,
                SUM(bonus) as total_bonus,
                COUNT(*) as games_played,
                ROUND(STDDEV(total_points), 2) as std_points
            FROM (
                SELECT * FROM player_gameweeks
                WHERE player_id = ? AND minutes > 0
                ORDER BY gameweek DESC
                LIMIT ?
            )
        """, [player_id, last_n]).fetchone()
        
        if result:
            return {
                'avg_points': result[0] or 0,
                'avg_minutes': result[1] or 0,
                'total_goals': result[2] or 0,
                'total_assists': result[3] or 0,
                'clean_sheets': result[4] or 0,
                'total_bonus': result[5] or 0,
                'games_played': result[6] or 0,
                'std_points': result[7] or 0
            }
        return {}
    
    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Search players by name."""
        search_term = f"%{query}%"
        return self.con.execute("""
            SELECT 
                p.id, p.web_name, p.first_name, p.second_name,
                p.team_id, p.position, p.total_points, p.form,
                t.short_name as team_name
            FROM pl_players p
            LEFT JOIN pl_teams t ON p.team_id = t.id
            WHERE p.web_name ILIKE ? 
               OR p.first_name ILIKE ?
               OR p.second_name ILIKE ?
            ORDER BY p.total_points DESC
            LIMIT ?
        """, [search_term, search_term, search_term, limit]).fetchdf().to_dict('records')


class TeamRepository:
    """Repository for team-related queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_all(self) -> List[Dict]:
        """Get all teams with standings."""
        return self.con.execute("""
            SELECT * FROM pl_teams
            ORDER BY position ASC, points DESC
        """).fetchdf().to_dict('records')
    
    def get_by_id(self, team_id: int) -> Optional[Dict]:
        """Get a single team by ID."""
        result = self.con.execute("""
            SELECT * FROM pl_teams WHERE id = ?
        """, [team_id]).fetchdf()
        
        if result.empty:
            return None
        return result.to_dict('records')[0]
    
    def get_standings(self) -> List[Dict]:
        """Get current PL standings."""
        return self.con.execute("""
            SELECT 
                id, name, short_name, position,
                played, won, drawn, lost,
                goals_for, goals_against,
                (goals_for - goals_against) as goal_difference,
                points, batch_id
            FROM pl_teams
            WHERE played > 0
            ORDER BY position ASC
        """).fetchdf().to_dict('records')
    
    def get_venue_stats(self, team_id: Optional[int] = None) -> List[Dict]:
        """Get home vs away performance for teams."""
        query = """
            SELECT 
                p.team_id,
                t.short_name,
                pg.was_home,
                COUNT(*) as games,
                ROUND(AVG(pg.total_points), 2) as avg_points,
                SUM(pg.goals_scored) as goals,
                SUM(pg.clean_sheets) as clean_sheets,
                ROUND(AVG(pg.goals_conceded), 2) as avg_conceded
            FROM player_gameweeks pg
            JOIN pl_players p ON pg.player_id = p.id
            JOIN pl_teams t ON p.team_id = t.id
            WHERE pg.minutes >= 60 AND p.position = 1
        """
        params = []
        
        if team_id:
            query += " AND p.team_id = ?"
            params.append(team_id)
        
        query += " GROUP BY p.team_id, t.short_name, pg.was_home"
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_batch_statistics(self, batch_id: int) -> Dict:
        """Get aggregated stats for teams in a batch."""
        result = self.con.execute("""
            SELECT 
                COUNT(*) as team_count,
                ROUND(AVG(goals_for::FLOAT / NULLIF(played, 0)), 2) as avg_goals_for,
                ROUND(AVG(goals_against::FLOAT / NULLIF(played, 0)), 2) as avg_goals_against,
                ROUND(AVG(points::FLOAT / NULLIF(played, 0)), 2) as avg_ppg
            FROM pl_teams
            WHERE batch_id = ?
        """, [batch_id]).fetchone()
        
        if result:
            return {
                'team_count': result[0] or 0,
                'avg_goals_for': result[1] or 0,
                'avg_goals_against': result[2] or 0,
                'avg_ppg': result[3] or 0
            }
        return {}


class SquadRepository:
    """Repository for squad and ownership queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_owned_player_ids(self, gameweek: int) -> Set[int]:
        """
        Get all player IDs owned by any squad.
        
        This is the CRITICAL query that fixes the free agents bug!
        """
        result = self.con.execute("""
            SELECT DISTINCT player_id 
            FROM fpl_squads 
            WHERE gameweek = ?
        """, [gameweek]).fetchall()
        return {row[0] for row in result}
    
    def get_all_squads(self, gameweek: int) -> Dict[int, List[Dict]]:
        """Get all squads for a gameweek."""
        result = self.con.execute("""
            SELECT 
                s.entry_id,
                s.player_id,
                s.squad_position,
                s.is_captain,
                s.is_vice_captain,
                p.web_name,
                p.position as player_position,
                p.total_points,
                t.short_name as team_name
            FROM fpl_squads s
            JOIN pl_players p ON s.player_id = p.id
            LEFT JOIN pl_teams t ON p.team_id = t.id
            WHERE s.gameweek = ?
            ORDER BY s.entry_id, s.squad_position
        """, [gameweek]).fetchdf()
        
        squads = {}
        for _, row in result.iterrows():
            entry_id = row['entry_id']
            if entry_id not in squads:
                squads[entry_id] = []
            squads[entry_id].append(row.to_dict())
        
        return squads
    
    def get_squad_by_entry(self, entry_id: int, gameweek: int) -> List[Dict]:
        """Get a single squad."""
        return self.con.execute("""
            SELECT 
                s.*,
                p.web_name,
                p.position as player_position,
                p.total_points,
                p.form,
                t.short_name as team_name
            FROM fpl_squads s
            JOIN pl_players p ON s.player_id = p.id
            LEFT JOIN pl_teams t ON p.team_id = t.id
            WHERE s.entry_id = ? AND s.gameweek = ?
            ORDER BY s.squad_position
        """, [entry_id, gameweek]).fetchdf().to_dict('records')
    
    def get_free_agents(self, gameweek: int, position: Optional[int] = None,
                        limit: int = 50) -> List[Dict]:
        """
        Get unowned, available players with predictions.
        
        This is the main free agents query that properly filters
        out owned players using the fpl_squads table.
        """
        query = """
            WITH owned AS (
                SELECT DISTINCT player_id 
                FROM fpl_squads 
                WHERE gameweek = ?
            ),
            player_form AS (
                SELECT 
                    player_id,
                    ROUND(AVG(total_points), 2) as avg_points,
                    COUNT(*) as games_played,
                    ROUND(STDDEV(total_points), 2) as std_points
                FROM player_gameweeks
                WHERE gameweek >= ? - 5 AND minutes > 0
                GROUP BY player_id
            )
            SELECT 
                p.id,
                p.web_name,
                p.first_name,
                p.second_name,
                p.team_id,
                p.position,
                p.status,
                p.total_points,
                p.form,
                p.points_per_game,
                p.chance_of_playing,
                t.short_name as team_name,
                t.position as team_position,
                t.batch_id,
                pf.avg_points as recent_form,
                pf.games_played,
                pf.std_points
            FROM pl_players p
            JOIN pl_teams t ON p.team_id = t.id
            LEFT JOIN player_form pf ON p.id = pf.player_id
            WHERE p.id NOT IN (SELECT player_id FROM owned)
              AND p.status = 'a'
              AND (p.chance_of_playing IS NULL OR p.chance_of_playing >= 50)
        """
        params = [gameweek, gameweek]
        
        if position:
            query += " AND p.position = ?"
            params.append(position)
        
        query += """
            ORDER BY COALESCE(pf.avg_points, p.points_per_game, 0) DESC
            LIMIT ?
        """
        params.append(limit)
        
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_free_agents_by_position(self, gameweek: int, 
                                     per_position: int = 3) -> Dict[str, List[Dict]]:
        """Get top free agents for each position."""
        positions = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        result = {}
        
        for pos_id, pos_name in positions.items():
            players = self.get_free_agents(gameweek, position=pos_id, limit=per_position)
            result[pos_name] = players
        
        return result


class LeagueRepository:
    """Repository for FPL Draft league queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_league(self) -> Optional[Dict]:
        """Get the current league info."""
        result = self.con.execute("""
            SELECT * FROM fpl_league LIMIT 1
        """).fetchdf()
        
        if result.empty:
            return None
        return result.to_dict('records')[0]
    
    def get_entries(self) -> List[Dict]:
        """Get all league entries (teams)."""
        return self.con.execute("""
            SELECT * FROM fpl_entries
            ORDER BY waiver_pick ASC
        """).fetchdf().to_dict('records')
    
    def get_entry_by_id(self, entry_id: int) -> Optional[Dict]:
        """Get a single entry."""
        result = self.con.execute("""
            SELECT * FROM fpl_entries WHERE entry_id = ?
        """, [entry_id]).fetchdf()
        
        if result.empty:
            return None
        return result.to_dict('records')[0]
    
    def get_matches(self, gameweek: Optional[int] = None) -> List[Dict]:
        """Get H2H matches."""
        query = """
            SELECT 
                m.*,
                m.gameweek as event,
                e1.entry_name as team1_name,
                e2.entry_name as team2_name
            FROM fpl_matches m
            LEFT JOIN fpl_entries e1 ON m.league_entry_1 = e1.id
            LEFT JOIN fpl_entries e2 ON m.league_entry_2 = e2.id
        """
        params = []
        
        if gameweek:
            query += " WHERE m.gameweek = ?"
            params.append(gameweek)
        
        query += " ORDER BY m.gameweek, m.id"
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_transactions(self, gameweek: Optional[int] = None,
                         entry_id: Optional[int] = None) -> List[Dict]:
        """Get transactions with player names."""
        query = """
            SELECT 
                t.*,
                t.transaction_type as kind,
                t.gameweek as event,
                e.entry_name,
                pin.web_name as player_in_name,
                pout.web_name as player_out_name
            FROM fpl_transactions t
            LEFT JOIN fpl_entries e ON t.entry_id = e.entry_id
            LEFT JOIN pl_players pin ON t.player_in = pin.id
            LEFT JOIN pl_players pout ON t.player_out = pout.id
            WHERE 1=1
        """
        params = []
        
        if gameweek:
            query += " AND t.gameweek = ?"
            params.append(gameweek)
        
        if entry_id:
            query += " AND t.entry_id = ?"
            params.append(entry_id)
        
        query += " ORDER BY t.added_time DESC"
        return self.con.execute(query, params).fetchdf().to_dict('records')


class FixtureRepository:
    """Repository for fixture and FDR queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_fixtures(self, gameweek: Optional[int] = None,
                     finished: Optional[bool] = None) -> List[Dict]:
        """Get PL fixtures."""
        query = """
            SELECT 
                f.*,
                ht.short_name as home_team_name,
                away_t.short_name as away_team_name
            FROM pl_fixtures f
            LEFT JOIN pl_teams ht ON f.home_team_id = ht.id
            LEFT JOIN pl_teams away_t ON f.away_team_id = away_t.id
            WHERE 1=1
        """
        params = []
        
        if gameweek:
            query += " AND f.gameweek = ?"
            params.append(gameweek)
        
        if finished is not None:
            query += " AND f.finished = ?"
            params.append(finished)
        
        query += " ORDER BY f.gameweek, f.kickoff_time"
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_fixture_grid(self, gw_start: int, gw_end: int) -> List[Dict]:
        """Get FDR grid for fixture display."""
        df = self.con.execute("""
            SELECT 
                t.short_name as team,
                t.id as team_id,
                fd.gameweek,
                opp.short_name as opponent,
                fd.is_home,
                COALESCE(fd.manual_override, fd.weighted_fdr, fd.official_fdr) as fdr,
                fd.official_fdr,
                fd.weighted_fdr
            FROM fixture_difficulty fd
            JOIN pl_teams t ON fd.team_id = t.id
            JOIN pl_teams opp ON fd.opponent_id = opp.id
            WHERE fd.gameweek BETWEEN ? AND ?
            ORDER BY t.short_name, fd.gameweek
        """, [gw_start, gw_end]).fetchdf()
        
        # Replace NaN with None before converting to dict
        df = df.where(df.notna(), None)
        return df.to_dict('records')
    
    def get_team_fixtures(self, team_id: int, gw_start: int, gw_end: int) -> List[Dict]:
        """Get fixtures for a specific team."""
        df = self.con.execute("""
            SELECT 
                fd.gameweek,
                opp.short_name as opponent,
                opp.id as opponent_id,
                fd.is_home,
                COALESCE(fd.manual_override, fd.weighted_fdr, fd.official_fdr) as fdr,
                opp.position as opponent_position,
                opp.batch_id as opponent_batch
            FROM fixture_difficulty fd
            JOIN pl_teams opp ON fd.opponent_id = opp.id
            WHERE fd.team_id = ? AND fd.gameweek BETWEEN ? AND ?
            ORDER BY fd.gameweek
        """, [team_id, gw_start, gw_end]).fetchdf()
        
        # Replace NaN with None before converting to dict
        df = df.where(df.notna(), None)
        return df.to_dict('records')


class PredictedLineupRepository:
    """Repository for predicted lineups data."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        # Store reference but don't use for reads (isolation issues)
        self.con = con or get_connection()
        self._use_fresh_connections_for_reads = (con is None)
    
    def upsert_predictions(self, predictions: List[dict]):
        """Insert or update predicted lineups for a gameweek."""
        cursor = self.con.cursor()
        
        for pred in predictions:
            # Skip predictions without player_id (unmatched)
            if pred.get('player_id') is None:
                continue
            
            # Handle fixture_id: use None if not present (for compatibility)
            fixture_id = pred.get('fixture_id')
            
            cursor.execute("""
                INSERT INTO predicted_lineups 
                (player_id, team_id, gameweek, fixture_id, start_probability, 
                 bench_probability, injured, injury_details, suspended, doubtful,
                 sources_count, sources_data, validation_note, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
                ON CONFLICT(player_id, gameweek) 
                DO UPDATE SET
                    team_id = excluded.team_id,
                    fixture_id = excluded.fixture_id,
                    start_probability = excluded.start_probability,
                    bench_probability = excluded.bench_probability,
                    injured = excluded.injured,
                    injury_details = excluded.injury_details,
                    suspended = excluded.suspended,
                    doubtful = excluded.doubtful,
                    sources_count = excluded.sources_count,
                    sources_data = excluded.sources_data,
                    validation_note = excluded.validation_note,
                    last_updated = NOW()
            """, (
                pred.get('player_id'), pred.get('team_id'), pred['gameweek'],
                fixture_id, pred['start_probability'],
                pred.get('bench_probability'), pred.get('injured', False),
                pred.get('injury_details'), pred.get('suspended', False),
                pred.get('doubtful', False), pred['sources_count'],
                pred['sources_data'], pred.get('validation_note')
            ))
        
        self.con.commit()
        return len(predictions)
    
    def get_predictions_for_gameweek(self, gameweek: int) -> List[dict]:
        """Get all predicted lineups for a gameweek with FPL ownership info."""
        # Use existing connection to avoid lock conflicts
        conn = self.con
        
        result = conn.execute("""
            SELECT 
                pl.*,
                p.web_name,
                p.first_name,
                p.second_name,
                t.short_name as team_name,
                p.position,
                CASE p.position
                    WHEN 1 THEN 'GK'
                    WHEN 2 THEN 'DEF'
                    WHEN 3 THEN 'MID'
                    WHEN 4 THEN 'FWD'
                    ELSE 'UNKNOWN'
                END as position_name,
                es.owner_entry_id,
                fe.short_name as fpl_club,
                fe.entry_name as fpl_club_name
            FROM predicted_lineups pl
            JOIN pl_players p ON pl.player_id = p.id
            LEFT JOIN pl_teams t ON pl.team_id = t.id
            LEFT JOIN element_status es ON p.id = es.element_id
            LEFT JOIN fpl_entries fe ON es.owner_entry_id = fe.entry_id
            WHERE pl.gameweek = ?
            ORDER BY t.short_name, pl.start_probability DESC
        """, [gameweek])
        
        records = result.fetchdf().to_dict('records')
        return records
    
    def get_player_lineup_probability(self, player_id: int, gameweek: int) -> Optional[float]:
        """Get a specific player's starting probability."""
        result = self.con.execute("""
            SELECT start_probability, injured, suspended, doubtful
            FROM predicted_lineups
            WHERE player_id = ? AND gameweek = ?
        """, [player_id, gameweek]).fetchone()
        
        if not result:
            return None
        
        start_prob, injured, suspended, doubtful = result
        
        # Return None if player is unavailable
        if injured or suspended:
            return 0.0
        
        return start_prob
    
    def get_team_lineup(self, team_id: int, gameweek: int) -> List[dict]:
        """Get predicted lineup for a specific team."""
        result = self.con.execute("""
            SELECT 
                pl.*,
                p.web_name,
                p.position,
                CASE p.position
                    WHEN 1 THEN 'GK'
                    WHEN 2 THEN 'DEF'
                    WHEN 3 THEN 'MID'
                    WHEN 4 THEN 'FWD'
                    ELSE 'UNKNOWN'
                END as position_name
            FROM predicted_lineups pl
            JOIN pl_players p ON pl.player_id = p.id
            WHERE pl.team_id = ? AND pl.gameweek = ?
            ORDER BY pl.start_probability DESC
        """, [team_id, gameweek])
        
        return result.fetchdf().to_dict('records')
    
    def get_unavailable_players(self, gameweek: int) -> List[dict]:
        """Get players who are injured, suspended, or doubtful."""
        result = self.con.execute("""
            SELECT 
                pl.*,
                p.web_name,
                t.short_name as team_name,
                p.position
            FROM predicted_lineups pl
            JOIN pl_players p ON pl.player_id = p.id
            LEFT JOIN pl_teams t ON pl.team_id = t.id
            WHERE pl.gameweek = ?
              AND (pl.injured = TRUE OR pl.suspended = TRUE OR pl.doubtful = TRUE)
            ORDER BY pl.start_probability DESC
        """, [gameweek])
        
        return result.fetchdf().to_dict('records')
    
    def delete_predictions_for_gameweek(self, gameweek: int):
        """Delete all predictions for a gameweek (for re-scraping)."""
        self.con.execute("DELETE FROM predicted_lineups WHERE gameweek = ?", [gameweek])
        self.con.commit()
    
    def upsert_unmatched_player(self, scraped_name: str, team_code: str, 
                                 position_code: str = None, source: str = None):
        """Track an unmatched player for future matching attempts."""
        self.con.execute("""
            INSERT INTO unmatched_players (scraped_name, team_code, position_code, sources, occurrences)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(scraped_name, team_code) 
            DO UPDATE SET
                last_seen = now(),
                occurrences = unmatched_players.occurrences + 1,
                sources = CASE 
                    WHEN unmatched_players.sources LIKE '%' || ? || '%' 
                    THEN unmatched_players.sources 
                    ELSE unmatched_players.sources || ', ' || ?
                END
        """, [scraped_name, team_code, position_code, source or 'unknown', source or 'unknown', source or 'unknown'])
        self.con.commit()
    
    def get_unmatched_players(self, min_occurrences: int = 1) -> List[dict]:
        """Get list of players that couldn't be matched."""
        result = self.con.execute("""
            SELECT * FROM unmatched_players 
            WHERE occurrences >= ?
            ORDER BY occurrences DESC, last_seen DESC
        """, [min_occurrences])
        return result.fetchdf().to_dict('records')
    
    def save_unmatched_predictions(self, gameweek: int, unmatched_predictions: List[dict]):
        """Save unmatched predictions for a gameweek (stored as JSON in cache)."""
        import json
        cache_key = f"unmatched_predictions_gw{gameweek}"
        cache_value = json.dumps(unmatched_predictions)
        
        self.con.execute("""
            INSERT OR REPLACE INTO cache (key, value, computed_at, gameweek)
            VALUES (?, ?, now(), ?)
        """, [cache_key, cache_value, gameweek])
        self.con.commit()
    
    def get_unmatched_predictions(self, gameweek: int) -> List[dict]:
        """Get unmatched predictions for a gameweek."""
        import json
        cache_key = f"unmatched_predictions_gw{gameweek}"
        
        result = self.con.execute("""
            SELECT value FROM cache 
            WHERE key = ?
        """, [cache_key]).fetchone()
        
        if result:
            return json.loads(result[0])
        return []


class SquadAnalysisRepository:
    """Repository for squad fixture analysis queries."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get_squad_with_teams(self, entry_id: int, gameweek: int) -> List[Dict]:
        """Get squad with PL team info for fixture analysis."""
        return self.con.execute("""
            SELECT 
                s.player_id,
                p.web_name,
                p.position,
                p.team_id,
                t.short_name as pl_team,
                p.total_points,
                p.form,
                p.points_per_game,
                CASE 
                    WHEN w.fpl_id IS NOT NULL THEN TRUE 
                    ELSE FALSE 
                END as is_star_player
            FROM fpl_squads s
            JOIN pl_players p ON s.player_id = p.id
            JOIN pl_teams t ON p.team_id = t.id
            LEFT JOIN wishlist_players w ON p.id = w.fpl_id
            WHERE s.entry_id = ? AND s.gameweek = ?
        """, [entry_id, gameweek]).fetchdf().to_dict('records')
    
    def get_fixture_difficulty_range(self, gw_start: int, gw_end: int) -> List[Dict]:
        """Get FDR for all teams in GW range."""
        return self.con.execute("""
            SELECT 
                team_id,
                gameweek,
                COALESCE(manual_override, weighted_fdr, official_fdr) as fdr,
                opponent_id,
                is_home
            FROM fixture_difficulty
            WHERE gameweek BETWEEN ? AND ?
        """, [gw_start, gw_end]).fetchdf().to_dict('records')
    
    def get_free_agents_with_fixtures(
        self, 
        gameweek: int, 
        gw_start: int, 
        gw_end: int,
        position: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get free agents filtered by position with upcoming fixture info."""
        query = """
            WITH owned AS (
                SELECT DISTINCT player_id 
                FROM fpl_squads 
                WHERE gameweek = ?
            ),
            player_form AS (
                SELECT 
                    player_id,
                    ROUND(AVG(total_points), 2) as avg_points,
                    COUNT(*) as games_played
                FROM player_gameweeks
                WHERE gameweek >= ? - 5 AND minutes > 0
                GROUP BY player_id
            ),
            player_fixtures AS (
                SELECT 
                    p.id as player_id,
                    COUNT(CASE WHEN COALESCE(fd.manual_override, fd.weighted_fdr, fd.official_fdr) <= 2 THEN 1 END) as easy_fixtures,
                    COUNT(*) as total_fixtures,
                    ROUND(AVG(COALESCE(fd.manual_override, fd.weighted_fdr, fd.official_fdr)), 2) as avg_fdr
                FROM pl_players p
                JOIN fixture_difficulty fd ON p.team_id = fd.team_id
                WHERE fd.gameweek BETWEEN ? AND ?
                GROUP BY p.id
            )
            SELECT 
                p.id,
                p.web_name,
                p.first_name,
                p.second_name,
                p.team_id,
                p.position,
                p.status,
                p.total_points,
                p.form,
                p.points_per_game,
                t.short_name as team_name,
                t.position as team_position,
                t.batch_id,
                pf.avg_points as recent_form,
                pf.games_played,
                px.easy_fixtures,
                px.total_fixtures,
                px.avg_fdr
            FROM pl_players p
            JOIN pl_teams t ON p.team_id = t.id
            LEFT JOIN player_form pf ON p.id = pf.player_id
            LEFT JOIN player_fixtures px ON p.id = px.player_id
            WHERE p.id NOT IN (SELECT player_id FROM owned)
              AND p.status = 'a'
              AND (p.chance_of_playing IS NULL OR p.chance_of_playing >= 50)
        """
        params = [gameweek, gameweek, gw_start, gw_end]
        
        if position:
            query += " AND p.position = ?"
            params.append(position)
        
        query += """
            ORDER BY px.easy_fixtures DESC, COALESCE(pf.avg_points, p.points_per_game, 0) DESC
            LIMIT ?
        """
        params.append(limit)
        
        return self.con.execute(query, params).fetchdf().to_dict('records')
    
    def get_all_entries(self) -> List[Dict]:
        """Get all league entries for manager selection."""
        return self.con.execute("""
            SELECT entry_id, entry_name, short_name, player_first_name, player_last_name
            FROM fpl_entries
            ORDER BY entry_name
        """).fetchdf().to_dict('records')
    
    def get_current_gameweek(self) -> int:
        """Get the most recent gameweek from fpl_squads."""
        result = self.con.execute("""
            SELECT MAX(gameweek) as current_gw FROM fpl_squads
        """).fetchone()
        return result[0] if result and result[0] else 22


class CacheRepository:
    """Repository for caching computed results."""
    
    def __init__(self, con: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = con or get_connection()
    
    def get(self, key: str) -> Optional[str]:
        """Get a cached value."""
        result = self.con.execute("""
            SELECT value FROM cache 
            WHERE key = ? 
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """, [key]).fetchone()
        
        return result[0] if result else None
    
    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None,
            gameweek: Optional[int] = None):
        """Set a cached value."""
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.now().timestamp() + ttl_seconds
        
        self.con.execute("""
            INSERT OR REPLACE INTO cache (key, value, computed_at, expires_at, gameweek)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
        """, [key, value, expires_at, gameweek])
    
    def delete(self, key: str):
        """Delete a cached value."""
        self.con.execute("DELETE FROM cache WHERE key = ?", [key])
    
    def clear_expired(self):
        """Clear all expired cache entries."""
        self.con.execute("""
            DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
        """)
    
    def clear_gameweek(self, gameweek: int):
        """Clear all cache entries for a specific gameweek."""
        self.con.execute("DELETE FROM cache WHERE gameweek = ?", [gameweek])
    
    def clear_all(self):
        """Clear all cache entries."""
        self.con.execute("DELETE FROM cache")


# Convenience function to get all repositories
def get_repositories(con: Optional[duckdb.DuckDBPyConnection] = None) -> Dict[str, Any]:
    """Get all repository instances."""
    if con is None:
        con = get_connection()
    
    return {
        'players': PlayerRepository(con),
        'teams': TeamRepository(con),
        'squads': SquadRepository(con),
        'league': LeagueRepository(con),
        'fixtures': FixtureRepository(con),
        'cache': CacheRepository(con),
        'predicted_lineups': PredictedLineupRepository(con),
        'squad_analysis': SquadAnalysisRepository(con)
    }
