"""
Event probability calculator

Calculates probabilities for various FPL events (goals, assists, clean sheets)
based on player stats and opponent analysis.
"""

from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

from ..config import STATS_CONFIG, Position
from ..models.player import Player
from ..models.team import Team
from .player_stats import PlayerStatsEngine, PlayerAnalysis
from .batch_analyzer import BatchAnalyzer, BatchStatistics
from ..utils.weighted_average import WeightedAverageCalculator


@dataclass
class EventProbabilities:
    """Probabilities for all FPL scoring events"""
    
    # Playing time
    prob_play_60_plus: float = 0.0
    prob_play_1_59: float = 0.0
    prob_not_play: float = 0.0
    
    # Attacking
    expected_goals: float = 0.0
    expected_assists: float = 0.0
    
    # Defensive
    prob_clean_sheet: float = 0.0
    expected_goals_conceded: float = 0.0
    
    # Goalkeeper
    expected_saves: float = 0.0
    prob_penalty_save: float = 0.0
    
    # Bonus
    expected_bonus: float = 0.0
    
    # Disciplinary
    prob_yellow_card: float = 0.0
    prob_red_card: float = 0.0
    prob_own_goal: float = 0.0
    prob_penalty_miss: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            'prob_play_60_plus': round(self.prob_play_60_plus, 3),
            'prob_play_1_59': round(self.prob_play_1_59, 3),
            'expected_goals': round(self.expected_goals, 3),
            'expected_assists': round(self.expected_assists, 3),
            'prob_clean_sheet': round(self.prob_clean_sheet, 3),
            'expected_goals_conceded': round(self.expected_goals_conceded, 2),
            'expected_saves': round(self.expected_saves, 2),
            'expected_bonus': round(self.expected_bonus, 2),
            'prob_yellow_card': round(self.prob_yellow_card, 3),
        }


class EventProbabilityCalculator:
    """
    Calculates event probabilities for FPL scoring.
    
    Combines player historical data with opponent batch analysis
    to estimate likelihood of various events.
    """
    
    def __init__(self, 
                 player_stats: PlayerStatsEngine,
                 batch_analyzer: BatchAnalyzer):
        """
        Initialize the calculator.
        
        Args:
            player_stats: Player statistics engine
            batch_analyzer: Batch analyzer with team data
        """
        self.player_stats = player_stats
        self.batch_analyzer = batch_analyzer
        self.batch_stats = BatchStatistics(batch_analyzer)
        self.weighted_calc = WeightedAverageCalculator()
        
        # League average event rates
        self.league_averages = {
            'goals_per_game': 2.8,  # Average goals per team per game
            'clean_sheet_rate': 0.28,  # ~28% of games are clean sheets
            'yellow_per_game': 1.8,  # Yellow cards per team per game
            'saves_per_game': 3.2,  # Average saves by GK per game
            'penalty_per_game': 0.08,  # Penalty frequency
        }
    
    def calculate_probabilities(self, 
                                 player: Player,
                                 opponent_team_id: int,
                                 is_home: bool = True) -> EventProbabilities:
        """
        Calculate event probabilities for a player vs opponent.
        
        Args:
            player: Player object
            opponent_team_id: FPL team ID of opponent
            is_home: Whether playing at home
            
        Returns:
            EventProbabilities with all calculated values
        """
        probs = EventProbabilities()
        
        # Get opponent batch
        opponent_batch = self.batch_analyzer.get_batch_for_team(opponent_team_id)
        if not opponent_batch:
            opponent_batch = (9, 12)  # Default to mid-table
        
        # Get player analysis
        analysis = self.player_stats.get_player_analysis(player.id)
        if not analysis:
            return self._get_fallback_probabilities(player)
        
        # Get batch strength multipliers
        batch_strength = self.batch_stats.get_batch_strength_index(opponent_batch)
        
        # Calculate playing time probabilities
        probs.prob_play_60_plus, probs.prob_play_1_59, probs.prob_not_play = \
            self._calculate_playing_time(analysis, player)
        
        # Calculate attacking probabilities (only if likely to play)
        play_prob = probs.prob_play_60_plus + probs.prob_play_1_59
        
        if play_prob > 0.1:
            probs.expected_goals = self._calculate_expected_goals(
                analysis, opponent_batch, batch_strength, is_home
            )
            probs.expected_assists = self._calculate_expected_assists(
                analysis, opponent_batch, batch_strength, is_home
            )
        
        # Calculate defensive probabilities
        if player.position in (Position.GK, Position.DEF):
            probs.prob_clean_sheet = self._calculate_clean_sheet_prob(
                analysis, player, opponent_batch, batch_strength
            )
            probs.expected_goals_conceded = self._calculate_expected_conceded(
                opponent_batch, batch_strength
            )
        elif player.position == Position.MID:
            # Midfielders get reduced CS points
            probs.prob_clean_sheet = self._calculate_clean_sheet_prob(
                analysis, player, opponent_batch, batch_strength
            ) * 0.7  # Reduce probability slightly for MIDs
        
        # Goalkeeper specific
        if player.position == Position.GK:
            probs.expected_saves = self._calculate_expected_saves(
                analysis, opponent_batch, batch_strength
            )
            probs.prob_penalty_save = self._calculate_penalty_save_prob(analysis)
        
        # Bonus points
        probs.expected_bonus = self._calculate_expected_bonus(
            analysis, probs, player.position
        )
        
        # Disciplinary
        probs.prob_yellow_card = self._calculate_yellow_prob(analysis)
        probs.prob_red_card = self._calculate_red_prob(analysis)
        probs.prob_own_goal = self._calculate_own_goal_prob(analysis)
        probs.prob_penalty_miss = self._calculate_penalty_miss_prob(analysis)
        
        return probs
    
    def _calculate_playing_time(self, analysis: PlayerAnalysis, 
                                 player: Player) -> Tuple[float, float, float]:
        """Calculate probability distribution for playing time"""
        stats = analysis.overall_stats
        
        if stats.games_played == 0:
            # No history - use news/injury status
            if player.chance_of_playing_next_round is not None:
                prob = player.chance_of_playing_next_round / 100
                return (prob * 0.7, prob * 0.3, 1 - prob)
            return (0.3, 0.2, 0.5)  # Unknown player
        
        total_minutes = stats.total_minutes
        games = stats.games_played
        
        # Calculate average minutes per game
        avg_minutes = total_minutes / games if games > 0 else 0
        
        # Estimate probabilities based on average minutes
        if avg_minutes >= 75:
            prob_60_plus = 0.85
            prob_1_59 = 0.10
        elif avg_minutes >= 60:
            prob_60_plus = 0.70
            prob_1_59 = 0.20
        elif avg_minutes >= 45:
            prob_60_plus = 0.50
            prob_1_59 = 0.30
        elif avg_minutes >= 30:
            prob_60_plus = 0.30
            prob_1_59 = 0.40
        elif avg_minutes >= 15:
            prob_60_plus = 0.15
            prob_1_59 = 0.45
        else:
            prob_60_plus = 0.05
            prob_1_59 = 0.35
        
        # Adjust for rotation risk
        rotation_adj = 1 - (analysis.rotation_risk * 0.3)
        prob_60_plus *= rotation_adj
        
        # Adjust for injury news
        if player.chance_of_playing_next_round is not None:
            injury_factor = player.chance_of_playing_next_round / 100
            prob_60_plus *= injury_factor
            prob_1_59 *= injury_factor
        
        prob_not_play = 1 - prob_60_plus - prob_1_59
        prob_not_play = max(0, prob_not_play)
        
        return (prob_60_plus, prob_1_59, prob_not_play)
    
    def _calculate_expected_goals(self, analysis: PlayerAnalysis,
                                   opponent_batch: Tuple[int, int],
                                   batch_strength: Dict[str, float],
                                   is_home: bool) -> float:
        """Calculate expected goals for the player"""
        # Get weighted goals per 90
        base_g90 = self.player_stats.get_weighted_stat(
            analysis.player_id, 'goals_per_90', opponent_batch
        )
        
        # Apply batch defense adjustment
        # Weaker defensive batch = more goals expected
        defense_factor = 1 / batch_strength.get('defense', 1.0)
        
        # Home advantage
        home_factor = 1.1 if is_home else 0.9
        
        # Convert per-90 to per-game (assume ~70 minutes average)
        expected = base_g90 * (70 / 90) * defense_factor * home_factor
        
        return max(0, expected)
    
    def _calculate_expected_assists(self, analysis: PlayerAnalysis,
                                     opponent_batch: Tuple[int, int],
                                     batch_strength: Dict[str, float],
                                     is_home: bool) -> float:
        """Calculate expected assists for the player"""
        base_a90 = self.player_stats.get_weighted_stat(
            analysis.player_id, 'assists_per_90', opponent_batch
        )
        
        # Weaker defense = more goals = more assists
        defense_factor = 1 / batch_strength.get('defense', 1.0)
        
        home_factor = 1.08 if is_home else 0.92
        
        expected = base_a90 * (70 / 90) * defense_factor * home_factor
        
        return max(0, expected)
    
    def _calculate_clean_sheet_prob(self, analysis: PlayerAnalysis,
                                     player: Player,
                                     opponent_batch: Tuple[int, int],
                                     batch_strength: Dict[str, float]) -> float:
        """Calculate clean sheet probability"""
        # Base rate from player history
        base_cs_rate = self.player_stats.get_weighted_stat(
            analysis.player_id, 'clean_sheet_rate', opponent_batch
        )
        
        # Adjust based on opponent attack strength
        attack_factor = 1 / batch_strength.get('attack', 1.0)
        
        # Can't exceed 1.0
        cs_prob = min(base_cs_rate * attack_factor, 0.65)
        
        # Must play 60+ for CS
        prob_60_plus = analysis.overall_stats.total_minutes / (analysis.overall_stats.games_played * 90) \
            if analysis.overall_stats.games_played > 0 else 0.5
        prob_60_plus = min(prob_60_plus, 0.95)
        
        return cs_prob * prob_60_plus
    
    def _calculate_expected_conceded(self, opponent_batch: Tuple[int, int],
                                      batch_strength: Dict[str, float]) -> float:
        """Calculate expected goals conceded"""
        # Base rate is league average
        base = self.league_averages['goals_per_game'] / 2  # Per team
        
        # Stronger attacking batch = more goals conceded
        attack_factor = batch_strength.get('attack', 1.0)
        
        return base * attack_factor
    
    def _calculate_expected_saves(self, analysis: PlayerAnalysis,
                                   opponent_batch: Tuple[int, int],
                                   batch_strength: Dict[str, float]) -> float:
        """Calculate expected saves for goalkeeper"""
        base_saves = self.player_stats.get_weighted_stat(
            analysis.player_id, 'saves_per_90', opponent_batch
        )
        
        # More saves against stronger attacking teams
        attack_factor = batch_strength.get('attack', 1.0)
        
        # Convert to per-game
        expected = base_saves * (70 / 90) * attack_factor
        
        return max(0, expected)
    
    def _calculate_penalty_save_prob(self, analysis: PlayerAnalysis) -> float:
        """Calculate probability of saving a penalty"""
        stats = analysis.overall_stats
        
        if stats.penalties_saved > 0:
            # Player has saved penalties before
            return 0.02 + (stats.penalties_saved * 0.005)
        
        # Base probability
        return 0.01
    
    def _calculate_expected_bonus(self, analysis: PlayerAnalysis,
                                   probs: EventProbabilities,
                                   position: int) -> float:
        """Calculate expected bonus points"""
        # Base from historical average
        base_bonus = analysis.overall_stats.avg_bonus
        
        # Adjust based on expected attacking output
        attacking_factor = 1.0
        if probs.expected_goals > 0.3:
            attacking_factor += probs.expected_goals * 0.5
        if probs.expected_assists > 0.3:
            attacking_factor += probs.expected_assists * 0.3
        
        # Clean sheet bonus for defenders/GKs
        if position in (Position.GK, Position.DEF) and probs.prob_clean_sheet > 0.3:
            attacking_factor += probs.prob_clean_sheet * 0.2
        
        expected = base_bonus * attacking_factor
        
        # Cap at 3
        return min(expected, 2.5)
    
    def _calculate_yellow_prob(self, analysis: PlayerAnalysis) -> float:
        """Calculate yellow card probability"""
        stats = analysis.overall_stats
        if stats.games_played == 0:
            return 0.15  # Default
        
        yellow_rate = stats.yellow_rate
        
        # Cap at reasonable maximum
        return min(yellow_rate, 0.4)
    
    def _calculate_red_prob(self, analysis: PlayerAnalysis) -> float:
        """Calculate red card probability"""
        stats = analysis.overall_stats
        if stats.games_played == 0:
            return 0.01
        
        if stats.red_cards > 0:
            return min(stats.red_cards / stats.games_played, 0.05)
        
        return 0.005  # Very rare
    
    def _calculate_own_goal_prob(self, analysis: PlayerAnalysis) -> float:
        """Calculate own goal probability"""
        stats = analysis.overall_stats
        if stats.games_played == 0:
            return 0.01
        
        if stats.own_goals > 0:
            return min(stats.own_goals / stats.games_played, 0.03)
        
        return 0.005
    
    def _calculate_penalty_miss_prob(self, analysis: PlayerAnalysis) -> float:
        """Calculate penalty miss probability"""
        stats = analysis.overall_stats
        if stats.games_played == 0:
            return 0.01
        
        if stats.penalties_missed > 0:
            return min(stats.penalties_missed / stats.games_played, 0.03)
        
        return 0.005
    
    def _get_fallback_probabilities(self, player: Player) -> EventProbabilities:
        """Get default probabilities when no analysis available"""
        probs = EventProbabilities()
        
        # Basic playing probability
        probs.prob_play_60_plus = 0.3
        probs.prob_play_1_59 = 0.2
        probs.prob_not_play = 0.5
        
        # Position-based defaults
        if player.position == Position.GK:
            probs.prob_clean_sheet = 0.25
            probs.expected_saves = 3.0
        elif player.position == Position.DEF:
            probs.expected_goals = 0.05
            probs.expected_assists = 0.08
            probs.prob_clean_sheet = 0.25
        elif player.position == Position.MID:
            probs.expected_goals = 0.12
            probs.expected_assists = 0.12
            probs.prob_clean_sheet = 0.15
        else:  # FWD
            probs.expected_goals = 0.25
            probs.expected_assists = 0.1
        
        probs.prob_yellow_card = 0.15
        probs.expected_bonus = 0.3
        
        return probs

