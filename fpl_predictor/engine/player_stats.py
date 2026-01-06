"""
Player statistics engine

Analyzes individual player performance across different opponent batches
and calculates per-90 statistics for prediction.
"""

from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass, field
import statistics

from ..config import STATS_CONFIG, Position
from ..models.player import Player, PlayerGameweek
from ..utils.outlier_filter import OutlierFilter, filter_valid_games, calculate_per_90
from ..utils.weighted_average import WeightedAverageCalculator, calculate_ewma


@dataclass
class PlayerBatchStats:
    """Statistics for a player against a specific opponent batch"""
    
    batch: Tuple[int, int] = (0, 0)  # Default to 'overall' batch
    games_played: int = 0
    total_minutes: int = 0
    
    # Attacking
    goals: int = 0
    assists: int = 0
    
    # Defensive
    clean_sheets: int = 0
    goals_conceded: int = 0
    defensive_contribution: int = 0
    
    # Goalkeeper
    saves: int = 0
    penalties_saved: int = 0
    
    # Bonus
    bonus_points: int = 0
    total_bps: int = 0
    
    # Disciplinary
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    penalties_missed: int = 0
    
    # Points
    total_points: int = 0
    
    @property
    def goals_per_90(self) -> float:
        return calculate_per_90(self.goals, self.total_minutes)
    
    @property
    def assists_per_90(self) -> float:
        return calculate_per_90(self.assists, self.total_minutes)
    
    @property
    def clean_sheet_rate(self) -> float:
        """Rate of clean sheets when playing 60+ minutes"""
        return self.clean_sheets / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def saves_per_90(self) -> float:
        return calculate_per_90(self.saves, self.total_minutes)
    
    @property
    def defensive_per_90(self) -> float:
        return calculate_per_90(self.defensive_contribution, self.total_minutes)
    
    @property
    def avg_bonus(self) -> float:
        return self.bonus_points / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def avg_bps(self) -> float:
        return self.total_bps / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def points_per_game(self) -> float:
        return self.total_points / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def yellow_rate(self) -> float:
        """Yellow cards per game"""
        return self.yellow_cards / self.games_played if self.games_played > 0 else 0.0


@dataclass
class PlayerAnalysis:
    """Complete analysis of a player's performance"""
    
    player_id: int
    player_name: str
    position: int
    team_id: int
    
    # Overall stats
    overall_stats: PlayerBatchStats = field(default_factory=PlayerBatchStats)
    
    # Stats by batch
    batch_stats: Dict[Tuple[int, int], PlayerBatchStats] = field(default_factory=dict)
    
    # Recent form (last 5 games)
    recent_form: PlayerBatchStats = field(default_factory=PlayerBatchStats)
    
    # Reliability metrics
    rotation_risk: float = 0.0
    data_quality: float = 0.5
    
    def get_stats_vs_batch(self, batch: Tuple[int, int]) -> PlayerBatchStats:
        """Get stats for a specific batch, falling back to overall if needed"""
        if batch in self.batch_stats and self.batch_stats[batch].games_played >= 2:
            return self.batch_stats[batch]
        return self.overall_stats


class PlayerStatsEngine:
    """
    Analyzes player performance data to calculate statistics
    for prediction models.
    """
    
    def __init__(self):
        self.outlier_filter = OutlierFilter()
        self.weighted_calc = WeightedAverageCalculator()
        self.player_analyses: Dict[int, PlayerAnalysis] = {}
        
        # League averages by position
        self.position_averages: Dict[int, Dict[str, float]] = {}
    
    def analyze_player(self, player: Player) -> PlayerAnalysis:
        """
        Perform complete analysis of a player.
        
        Args:
            player: Player object with gameweek history
            
        Returns:
            PlayerAnalysis with all statistics
        """
        analysis = PlayerAnalysis(
            player_id=player.id,
            player_name=player.web_name,
            position=player.position,
            team_id=player.team_id,
        )
        
        # Filter valid games
        valid_games = filter_valid_games(player.gameweeks, STATS_CONFIG.MIN_MINUTES_PLAYED)
        
        if not valid_games:
            self.player_analyses[player.id] = analysis
            return analysis
        
        # Calculate overall stats
        analysis.overall_stats = self._calculate_stats(valid_games, (1, 20))
        
        # Calculate stats by batch
        games_by_batch: Dict[Tuple[int, int], List[PlayerGameweek]] = defaultdict(list)
        for gw in valid_games:
            if gw.opponent_batch:
                games_by_batch[gw.opponent_batch].append(gw)
        
        for batch, games in games_by_batch.items():
            analysis.batch_stats[batch] = self._calculate_stats(games, batch)
        
        # Calculate recent form
        recent_games = player.get_recent_games(
            STATS_CONFIG.RECENT_GAMES_COUNT, 
            STATS_CONFIG.MIN_MINUTES_PLAYED
        )
        if recent_games:
            analysis.recent_form = self._calculate_stats(recent_games, (1, 20))
        
        # Calculate reliability metrics
        analysis.rotation_risk = self.outlier_filter.detect_rotation_risk(player)
        quality_score, _ = self.outlier_filter.get_data_quality_score(player)
        analysis.data_quality = quality_score
        
        self.player_analyses[player.id] = analysis
        return analysis
    
    def _calculate_stats(self, games: List[PlayerGameweek], 
                          batch: Tuple[int, int]) -> PlayerBatchStats:
        """Calculate aggregated stats from a list of games"""
        stats = PlayerBatchStats(batch=batch)
        
        if not games:
            return stats
        
        stats.games_played = len(games)
        stats.total_minutes = sum(g.minutes for g in games)
        stats.goals = sum(g.goals_scored for g in games)
        stats.assists = sum(g.assists for g in games)
        stats.saves = sum(g.saves for g in games)
        stats.penalties_saved = sum(g.penalties_saved for g in games)
        stats.defensive_contribution = sum(g.defensive_contribution for g in games)
        stats.bonus_points = sum(g.bonus for g in games)
        stats.total_bps = sum(g.bps for g in games)
        stats.yellow_cards = sum(g.yellow_cards for g in games)
        stats.red_cards = sum(g.red_cards for g in games)
        stats.own_goals = sum(g.own_goals for g in games)
        stats.penalties_missed = sum(g.penalties_missed for g in games)
        stats.total_points = sum(g.total_points for g in games)
        
        # Clean sheets (only count when player played 60+ minutes)
        full_games = [g for g in games if g.minutes >= 60]
        stats.clean_sheets = sum(g.clean_sheets for g in full_games)
        
        # Goals conceded (for GK/DEF)
        stats.goals_conceded = sum(g.goals_conceded for g in full_games)
        
        return stats
    
    def analyze_all_players(self, players: Dict[int, Player]) -> Dict[int, PlayerAnalysis]:
        """
        Analyze all players.
        
        Args:
            players: Dictionary of player_id -> Player
            
        Returns:
            Dictionary of player_id -> PlayerAnalysis
        """
        for player_id, player in players.items():
            self.analyze_player(player)
        
        # Calculate league averages
        self._calculate_position_averages()
        
        return self.player_analyses
    
    def _calculate_position_averages(self) -> None:
        """Calculate league average stats by position"""
        position_stats: Dict[int, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        
        for analysis in self.player_analyses.values():
            if analysis.overall_stats.games_played < 3:
                continue
            
            pos = analysis.position
            stats = analysis.overall_stats
            
            position_stats[pos]['goals_per_90'].append(stats.goals_per_90)
            position_stats[pos]['assists_per_90'].append(stats.assists_per_90)
            position_stats[pos]['clean_sheet_rate'].append(stats.clean_sheet_rate)
            position_stats[pos]['bonus_avg'].append(stats.avg_bonus)
            position_stats[pos]['ppg'].append(stats.points_per_game)
            
            if pos == Position.GK:
                position_stats[pos]['saves_per_90'].append(stats.saves_per_90)
        
        # Calculate averages
        for pos, stats_dict in position_stats.items():
            self.position_averages[pos] = {
                key: statistics.mean(values) if values else 0.0
                for key, values in stats_dict.items()
            }
    
    def get_player_analysis(self, player_id: int) -> Optional[PlayerAnalysis]:
        """Get analysis for a specific player"""
        return self.player_analyses.get(player_id)
    
    def get_position_average(self, position: int, stat: str) -> float:
        """Get league average for a position and stat"""
        pos_avgs = self.position_averages.get(position, {})
        return pos_avgs.get(stat, 0.0)
    
    def get_weighted_stat(self, player_id: int, stat_name: str,
                          batch: Optional[Tuple[int, int]] = None) -> float:
        """
        Get a weighted statistic combining batch, overall, and form.
        
        Args:
            player_id: Player ID
            stat_name: Name of stat (e.g., 'goals_per_90')
            batch: Optional opponent batch
            
        Returns:
            Weighted stat value
        """
        analysis = self.player_analyses.get(player_id)
        if not analysis:
            return 0.0
        
        overall = analysis.overall_stats
        form = analysis.recent_form
        
        # Get overall value
        overall_value = getattr(overall, stat_name, 0.0)
        overall_games = overall.games_played
        
        # Get batch-specific value if available
        batch_value = overall_value
        batch_games = 0
        if batch and batch in analysis.batch_stats:
            batch_stats = analysis.batch_stats[batch]
            batch_value = getattr(batch_stats, stat_name, 0.0)
            batch_games = batch_stats.games_played
        
        # Get recent form value
        form_value = getattr(form, stat_name, overall_value)
        form_games = form.games_played
        
        # Combine batch and overall
        batch_overall = self.weighted_calc.combine_batch_and_overall(
            batch_value, batch_games,
            overall_value, overall_games
        )
        
        # Combine with form
        final = self.weighted_calc.combine_form_and_season(
            form_value, form_games,
            batch_overall.value, overall_games
        )
        
        # Regress extreme values
        position_avg = self.get_position_average(analysis.position, stat_name)
        if position_avg > 0:
            final_value = self.weighted_calc.regress_to_mean(
                final.value,
                position_avg,
                overall_games
            )
        else:
            final_value = final.value
        
        return final_value
    
    def get_player_summary(self, player_id: int) -> Dict[str, Any]:
        """Get a summary of player stats for display"""
        analysis = self.player_analyses.get(player_id)
        if not analysis:
            return {}
        
        stats = analysis.overall_stats
        
        return {
            'player_id': player_id,
            'name': analysis.player_name,
            'position': {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}.get(analysis.position, 'UNK'),
            'games_played': stats.games_played,
            'total_points': stats.total_points,
            'ppg': round(stats.points_per_game, 2),
            'goals_per_90': round(stats.goals_per_90, 3),
            'assists_per_90': round(stats.assists_per_90, 3),
            'clean_sheet_rate': round(stats.clean_sheet_rate * 100, 1),
            'avg_bonus': round(stats.avg_bonus, 2),
            'rotation_risk': round(analysis.rotation_risk, 2),
            'data_quality': round(analysis.data_quality, 2),
            'batches_analyzed': len(analysis.batch_stats),
        }

