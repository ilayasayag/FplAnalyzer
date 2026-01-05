"""
Team batch analyzer

Assigns teams to batches based on league position and calculates
performance statistics for each team against each batch.
"""

from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from ..config import (
    DEFAULT_BATCHES,
    BATCH_NAMES,
    get_batch_for_position,
    get_batch_name,
    STATS_CONFIG,
)
from ..models.team import Team, TeamBatch, TeamStats
from ..models.player import Player, PlayerGameweek
from ..data.standings import StandingsFetcher


class BatchAnalyzer:
    """
    Analyzes team performance across different opposition batches.
    
    Batches group teams by league position (e.g., Top 4, Mid-table, Relegation).
    This allows for more nuanced prediction based on opposition quality.
    """
    
    def __init__(self, batches: Optional[List[Tuple[int, int]]] = None):
        """
        Initialize the batch analyzer.
        
        Args:
            batches: Custom batch definitions, or None for defaults
        """
        self.batches = batches or DEFAULT_BATCHES
        self.team_batches: Dict[Tuple[int, int], TeamBatch] = {}
        self.standings: Dict[int, int] = {}  # team_id -> position
        self._initialized = False
    
    def initialize(self, teams: Dict[int, Team], 
                   standings_fetcher: Optional[StandingsFetcher] = None) -> None:
        """
        Initialize batches with current team standings.
        
        Args:
            teams: Dictionary of team_id -> Team
            standings_fetcher: Optional fetcher for live standings
        """
        # Get current standings
        if standings_fetcher:
            self.standings = standings_fetcher.fetch_standings()
        else:
            # Use team positions from Team objects if available
            self.standings = {
                team_id: team.position 
                for team_id, team in teams.items()
                if team.position > 0
            }
        
        # Update team positions and create batch groups
        for team_id, team in teams.items():
            if team_id in self.standings:
                team.position = self.standings[team_id]
        
        # Create TeamBatch objects
        for start, end in self.batches:
            batch_tuple = (start, end)
            batch = TeamBatch(
                start_position=start,
                end_position=end,
                name=get_batch_name(batch_tuple),
            )
            
            # Add teams that belong to this batch
            for team_id, team in teams.items():
                if start <= team.position <= end:
                    batch.teams.append(team)
            
            self.team_batches[batch_tuple] = batch
        
        self._initialized = True
    
    def get_batch_for_team(self, team_id: int) -> Optional[Tuple[int, int]]:
        """
        Get the batch for a given team.
        
        Args:
            team_id: FPL team ID
            
        Returns:
            Batch tuple (start, end) or None if team not found
        """
        position = self.standings.get(team_id)
        if position is None:
            return None
        
        return get_batch_for_position(position, self.batches)
    
    def get_batch_name_for_team(self, team_id: int) -> str:
        """Get human-readable batch name for a team"""
        batch = self.get_batch_for_team(team_id)
        if batch:
            return get_batch_name(batch)
        return "Unknown"
    
    def analyze_team_performance(self, team: Team, 
                                  players: List[Player]) -> None:
        """
        Analyze a team's performance against each batch.
        
        Uses player gameweek data to calculate team-level stats.
        
        Args:
            team: Team object to analyze
            players: List of players from this team
        """
        # Group games by opponent batch
        batch_games: Dict[Tuple[int, int], List[PlayerGameweek]] = defaultdict(list)
        
        for player in players:
            for gw in player.gameweeks:
                if gw.minutes >= STATS_CONFIG.MIN_MINUTES_PLAYED:
                    opp_batch = self.get_batch_for_team(gw.opponent_team_id)
                    if opp_batch:
                        gw.opponent_batch = opp_batch
                        batch_games[opp_batch].append(gw)
        
        # Calculate stats for each batch
        for batch_tuple, games in batch_games.items():
            stats = self._calculate_batch_stats(games, team.id)
            team.stats_vs_batch[batch_tuple] = stats
        
        # Calculate overall stats
        all_games = [gw for games in batch_games.values() for gw in games]
        team.overall_stats = self._calculate_batch_stats(all_games, team.id)
    
    def _calculate_batch_stats(self, games: List[PlayerGameweek], 
                                team_id: int) -> TeamStats:
        """
        Calculate aggregated team stats from player gameweek data.
        
        This is an approximation based on outfield players' data.
        """
        if not games:
            return TeamStats()
        
        # Group games by gameweek to avoid double-counting
        games_by_gw: Dict[int, List[PlayerGameweek]] = defaultdict(list)
        for gw in games:
            games_by_gw[gw.gameweek].append(gw)
        
        num_matches = len(games_by_gw)
        total_goals = 0
        total_conceded = 0
        clean_sheets = 0
        
        for gw_num, gw_games in games_by_gw.items():
            # Get goals from attacking players
            gw_goals = sum(g.goals_scored for g in gw_games)
            gw_conceded = max(g.goals_conceded for g in gw_games) if gw_games else 0
            
            # Count as clean sheet if any defender/GK had clean sheet
            gw_cs = any(g.clean_sheets > 0 for g in gw_games)
            
            # Use a reasonable estimate for goals (avoid over-counting)
            total_goals += min(gw_goals, 5)  # Cap at 5 goals per game
            total_conceded += min(gw_conceded, 5)
            if gw_cs:
                clean_sheets += 1
        
        return TeamStats(
            games_played=num_matches,
            goals_scored=total_goals,
            goals_conceded=total_conceded,
            clean_sheets=clean_sheets,
        )
    
    def analyze_all_teams(self, teams: Dict[int, Team],
                          players: Dict[int, Player]) -> None:
        """
        Analyze performance for all teams.
        
        Args:
            teams: Dictionary of team_id -> Team
            players: Dictionary of player_id -> Player
        """
        # Group players by team
        players_by_team: Dict[int, List[Player]] = defaultdict(list)
        for player in players.values():
            players_by_team[player.team_id].append(player)
        
        # Analyze each team
        for team_id, team in teams.items():
            team_players = players_by_team.get(team_id, [])
            self.analyze_team_performance(team, team_players)
    
    def assign_opponent_batches_to_players(self, 
                                            players: Dict[int, Player]) -> None:
        """
        Assign opponent batch info to all player gameweeks.
        
        Args:
            players: Dictionary of player_id -> Player
        """
        for player in players.values():
            for gw in player.gameweeks:
                batch = self.get_batch_for_team(gw.opponent_team_id)
                if batch:
                    gw.opponent_batch = batch
                    gw.opponent_position = self.standings.get(gw.opponent_team_id, 0)
    
    def get_batch_summary(self) -> List[Dict[str, Any]]:
        """
        Get a summary of all batches.
        
        Returns:
            List of batch info dictionaries
        """
        summary = []
        
        for batch_tuple, batch in sorted(self.team_batches.items()):
            summary.append({
                'range': f"{batch_tuple[0]}-{batch_tuple[1]}",
                'name': batch.name,
                'team_count': len(batch.teams),
                'teams': [t.short_name for t in batch.teams],
                'avg_goals_per_game': round(batch.average_goals_per_game, 2),
                'avg_goals_conceded': round(batch.average_goals_conceded_per_game, 2),
                'avg_clean_sheet_rate': round(batch.average_clean_sheet_rate * 100, 1),
            })
        
        return summary
    
    def get_team_batch_performance(self, team_id: int, 
                                    team: Team) -> List[Dict[str, Any]]:
        """
        Get a team's performance breakdown by opponent batch.
        
        Args:
            team_id: FPL team ID
            team: Team object with stats
            
        Returns:
            List of performance stats per batch
        """
        results = []
        
        for batch_tuple in sorted(self.batches):
            stats = team.stats_vs_batch.get(batch_tuple, TeamStats())
            
            results.append({
                'batch': f"{batch_tuple[0]}-{batch_tuple[1]}",
                'batch_name': get_batch_name(batch_tuple),
                'games': stats.games_played,
                'goals_per_game': round(stats.goals_per_game, 2),
                'conceded_per_game': round(stats.goals_conceded_per_game, 2),
                'clean_sheet_rate': round(stats.clean_sheet_rate * 100, 1),
            })
        
        return results
    
    def get_opposition_difficulty(self, opponent_team_id: int) -> float:
        """
        Get a difficulty rating for an opponent (0-1 scale).
        
        Lower position = harder opponent = higher difficulty.
        
        Args:
            opponent_team_id: FPL team ID of opponent
            
        Returns:
            Difficulty rating (0 = easiest, 1 = hardest)
        """
        position = self.standings.get(opponent_team_id, 10)
        # Normalize to 0-1 (position 1 = 1.0, position 20 = 0.0)
        return (21 - position) / 20


class BatchStatistics:
    """
    Aggregate statistics calculated across batches.
    """
    
    def __init__(self, batch_analyzer: BatchAnalyzer):
        self.analyzer = batch_analyzer
        self.league_avg_goals: float = 0.0
        self.league_avg_conceded: float = 0.0
        self.league_clean_sheet_rate: float = 0.0
        
        self._calculate_league_averages()
    
    def _calculate_league_averages(self) -> None:
        """Calculate league-wide averages"""
        total_gpg = 0.0
        total_cpg = 0.0
        total_csr = 0.0
        count = 0
        
        for batch in self.analyzer.team_batches.values():
            for team in batch.teams:
                if team.overall_stats.games_played > 0:
                    total_gpg += team.overall_stats.goals_per_game
                    total_cpg += team.overall_stats.goals_conceded_per_game
                    total_csr += team.overall_stats.clean_sheet_rate
                    count += 1
        
        if count > 0:
            self.league_avg_goals = total_gpg / count
            self.league_avg_conceded = total_cpg / count
            self.league_clean_sheet_rate = total_csr / count
    
    def get_batch_strength_index(self, batch: Tuple[int, int]) -> Dict[str, float]:
        """
        Calculate how much stronger/weaker a batch is vs league average.
        
        Returns multipliers for various stats.
        """
        team_batch = self.analyzer.team_batches.get(batch)
        if not team_batch:
            return {'attack': 1.0, 'defense': 1.0}
        
        # Attack strength: how many goals they score vs average
        attack = (team_batch.average_goals_per_game / self.league_avg_goals 
                  if self.league_avg_goals > 0 else 1.0)
        
        # Defense strength: inverse of conceded (lower = stronger)
        defense = (self.league_avg_conceded / team_batch.average_goals_conceded_per_game
                   if team_batch.average_goals_conceded_per_game > 0 else 1.0)
        
        return {
            'attack': round(attack, 3),
            'defense': round(defense, 3),
            'clean_sheet_factor': round(
                team_batch.average_clean_sheet_rate / self.league_clean_sheet_rate
                if self.league_clean_sheet_rate > 0 else 1.0, 3
            ),
        }

