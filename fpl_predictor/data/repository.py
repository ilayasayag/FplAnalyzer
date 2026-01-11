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
        return self.con.execute("""
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
        """, [gw_start, gw_end]).fetchdf().to_dict('records')
    
    def get_team_fixtures(self, team_id: int, gw_start: int, gw_end: int) -> List[Dict]:
        """Get fixtures for a specific team."""
        return self.con.execute("""
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
        """, [team_id, gw_start, gw_end]).fetchdf().to_dict('records')


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
        'cache': CacheRepository(con)
    }
