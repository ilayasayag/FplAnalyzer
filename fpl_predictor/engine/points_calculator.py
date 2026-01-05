"""
Points calculator

Converts event probabilities into expected FPL points using
official FPL scoring rules.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from ..config import SCORING, Position
from ..models.player import Player
from ..models.team import Team
from ..models.prediction import Prediction, PredictionBreakdown, SquadPrediction
from .player_stats import PlayerStatsEngine
from .batch_analyzer import BatchAnalyzer
from .event_probability import EventProbabilityCalculator, EventProbabilities


class PointsCalculator:
    """
    Calculates expected FPL points from event probabilities.
    
    Uses official FPL scoring rules to convert probabilities
    into expected points.
    """
    
    def __init__(self,
                 player_stats: PlayerStatsEngine,
                 batch_analyzer: BatchAnalyzer,
                 event_calculator: EventProbabilityCalculator):
        """
        Initialize the calculator.
        
        Args:
            player_stats: Player statistics engine
            batch_analyzer: Batch analyzer
            event_calculator: Event probability calculator
        """
        self.player_stats = player_stats
        self.batch_analyzer = batch_analyzer
        self.event_calc = event_calculator
    
    def calculate_expected_points(self,
                                   player: Player,
                                   opponent_team: Team,
                                   gameweek: int,
                                   is_home: bool = True) -> Prediction:
        """
        Calculate expected points for a player.
        
        Args:
            player: Player object
            opponent_team: Opponent Team object
            gameweek: Gameweek number
            is_home: Whether playing at home
            
        Returns:
            Prediction with expected points and breakdown
        """
        # Get event probabilities
        probs = self.event_calc.calculate_probabilities(
            player, opponent_team.id, is_home
        )
        
        # Calculate points breakdown
        breakdown = self._calculate_breakdown(player, probs)
        
        # Get opponent batch info
        opponent_batch = self.batch_analyzer.get_batch_for_team(opponent_team.id)
        batch_name = self.batch_analyzer.get_batch_name_for_team(opponent_team.id)
        
        # Get data quality
        analysis = self.player_stats.get_player_analysis(player.id)
        quality_score = analysis.data_quality if analysis else 0.3
        sample_size = analysis.overall_stats.games_played if analysis else 0
        quality_label = "high" if quality_score >= 0.7 else "medium" if quality_score >= 0.4 else "low"
        
        # Build prediction
        prediction = Prediction(
            player_id=player.id,
            player_name=player.web_name,
            position=player.position_name,
            team=player.team_name,
            gameweek=gameweek,
            opponent_id=opponent_team.id,
            opponent_name=opponent_team.name,
            opponent_short=opponent_team.short_name,
            opponent_position=opponent_team.position,
            opponent_batch=batch_name,
            is_home=is_home,
            expected_points=breakdown.total_expected_points,
            breakdown=breakdown,
            confidence=quality_score,
            sample_size=sample_size,
            data_quality=quality_label,
        )
        
        # Add warnings
        self._add_warnings(prediction, player, probs)
        
        return prediction
    
    def _calculate_breakdown(self, player: Player, 
                              probs: EventProbabilities) -> PredictionBreakdown:
        """Calculate detailed points breakdown"""
        breakdown = PredictionBreakdown()
        position = Position(player.position)
        
        # Playing time points
        breakdown.playing_prob_60_plus = probs.prob_play_60_plus
        breakdown.playing_prob_1_59 = probs.prob_play_1_59
        breakdown.playing_points = (
            probs.prob_play_60_plus * SCORING.MINUTES_60_PLUS +
            probs.prob_play_1_59 * SCORING.MINUTES_1_59
        )
        
        # Goals
        breakdown.expected_goals = probs.expected_goals
        goal_points = SCORING.GOALS.get(position, 4)
        breakdown.goal_points = probs.expected_goals * goal_points
        
        # Assists
        breakdown.expected_assists = probs.expected_assists
        breakdown.assist_points = probs.expected_assists * SCORING.ASSIST
        
        # Clean sheets
        if position in (Position.GK, Position.DEF, Position.MID):
            breakdown.clean_sheet_prob = probs.prob_clean_sheet
            cs_points = SCORING.CLEAN_SHEET.get(position, 0)
            breakdown.clean_sheet_points = probs.prob_clean_sheet * cs_points
        
        # Saves (GK only)
        if position == Position.GK:
            breakdown.expected_saves = probs.expected_saves
            breakdown.saves_points = probs.expected_saves / SCORING.SAVES_PER_POINT
        
        # Goals conceded penalty (GK/DEF only)
        if position in (Position.GK, Position.DEF):
            breakdown.expected_goals_conceded = probs.expected_goals_conceded
            # -1 point per 2 goals conceded
            # But only when playing 60+
            penalty_per_conceded = -1 / SCORING.GOALS_CONCEDED_PER_PENALTY
            breakdown.conceded_penalty = (
                probs.expected_goals_conceded * 
                penalty_per_conceded * 
                probs.prob_play_60_plus
            )
        
        # Bonus
        breakdown.expected_bonus = probs.expected_bonus
        
        # Yellow cards
        breakdown.yellow_card_risk = probs.prob_yellow_card
        breakdown.yellow_card_penalty = probs.prob_yellow_card * SCORING.YELLOW_CARD
        
        # Own goals
        breakdown.own_goal_risk = probs.prob_own_goal
        breakdown.own_goal_penalty = probs.prob_own_goal * SCORING.OWN_GOAL
        
        return breakdown
    
    def _add_warnings(self, prediction: Prediction, 
                      player: Player, probs: EventProbabilities) -> None:
        """Add warning messages to prediction"""
        warnings = []
        
        # Low playing chance
        if probs.prob_not_play > 0.5:
            warnings.append("High risk of not playing")
        elif probs.prob_not_play > 0.3:
            warnings.append("Some rotation risk")
        
        # Injury news
        if player.news:
            warnings.append(f"News: {player.news[:50]}")
        
        if player.chance_of_playing_next_round is not None:
            if player.chance_of_playing_next_round < 50:
                warnings.append(f"Injury doubt ({player.chance_of_playing_next_round}% chance)")
        
        # Low data quality
        if prediction.data_quality == "low":
            warnings.append("Limited historical data")
        
        prediction.warnings = warnings
    
    def calculate_squad_predictions(self,
                                     entry_id: int,
                                     entry_name: str,
                                     players: List[Player],
                                     opponents: Dict[int, Tuple[Team, bool]],
                                     gameweek: int) -> SquadPrediction:
        """
        Calculate predictions for an entire squad.
        
        Args:
            entry_id: Fantasy entry ID
            entry_name: Team name
            players: List of 15 squad players
            opponents: Dict mapping team_id -> (opponent Team, is_home)
            gameweek: Gameweek number
            
        Returns:
            SquadPrediction with all player predictions and optimal 11
        """
        predictions = []
        
        for player in players:
            # Get opponent for this player's team
            opp_info = opponents.get(player.team_id)
            if opp_info:
                opponent, is_home = opp_info
                pred = self.calculate_expected_points(
                    player, opponent, gameweek, is_home
                )
            else:
                # No fixture info - use placeholder
                pred = self._get_blank_prediction(player, gameweek)
            
            predictions.append(pred)
        
        # Select optimal 11
        optimal_11, formation = self._select_optimal_11(predictions)
        
        return SquadPrediction(
            squad_name=entry_name,
            entry_id=entry_id,
            gameweek=gameweek,
            predictions=predictions,
            optimal_11=optimal_11,
            optimal_formation=formation,
        )
    
    def _select_optimal_11(self, 
                           predictions: List[Prediction]) -> Tuple[List[Prediction], str]:
        """
        Select optimal 11 players from 15, respecting FPL formation rules.
        
        Rules: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD
        
        Args:
            predictions: All 15 player predictions
            
        Returns:
            Tuple of (optimal 11 predictions, formation string)
        """
        # Group by position
        by_position = {
            'GK': [],
            'DEF': [],
            'MID': [],
            'FWD': [],
        }
        
        for pred in predictions:
            pos = pred.position
            if pos in by_position:
                by_position[pos].append(pred)
        
        # Sort each position by expected points
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x.expected_points, reverse=True)
        
        # Must have: 1 GK, at least 3 DEF, at least 2 MID, at least 1 FWD
        optimal = []
        
        # 1 GK (required)
        if by_position['GK']:
            optimal.append(by_position['GK'][0])
        
        # Get minimum requirements
        defs = by_position['DEF'][:3]  # Min 3
        mids = by_position['MID'][:2]  # Min 2
        fwds = by_position['FWD'][:1]  # Min 1
        
        optimal.extend(defs)
        optimal.extend(mids)
        optimal.extend(fwds)
        
        # Now fill remaining 4 spots with best available
        remaining_pool = (
            by_position['DEF'][3:] +
            by_position['MID'][2:] +
            by_position['FWD'][1:]
        )
        remaining_pool.sort(key=lambda x: x.expected_points, reverse=True)
        
        # Track position counts
        pos_counts = {
            'DEF': 3,
            'MID': 2,
            'FWD': 1,
        }
        
        # Fill remaining spots (need 4 more for 11 total, including GK)
        needed = 11 - len(optimal)
        
        for pred in remaining_pool:
            if needed <= 0:
                break
            
            pos = pred.position
            
            # Check position limits
            if pos == 'DEF' and pos_counts['DEF'] >= 5:
                continue
            if pos == 'MID' and pos_counts['MID'] >= 5:
                continue
            if pos == 'FWD' and pos_counts['FWD'] >= 3:
                continue
            
            optimal.append(pred)
            pos_counts[pos] = pos_counts.get(pos, 0) + 1
            needed -= 1
        
        # Determine formation string
        formation = f"{pos_counts['DEF']}-{pos_counts['MID']}-{pos_counts['FWD']}"
        
        return optimal, formation
    
    def _get_blank_prediction(self, player: Player, gameweek: int) -> Prediction:
        """Create a blank prediction when no fixture data available"""
        return Prediction(
            player_id=player.id,
            player_name=player.web_name,
            position=player.position_name,
            team=player.team_name,
            gameweek=gameweek,
            opponent_id=0,
            opponent_name="Unknown",
            opponent_short="???",
            opponent_position=0,
            opponent_batch="Unknown",
            is_home=True,
            expected_points=0.0,
            breakdown=PredictionBreakdown(),
            confidence=0.0,
            sample_size=0,
            data_quality="low",
            warnings=["No fixture data available"],
        )


def create_prediction_engine(player_stats: PlayerStatsEngine,
                              batch_analyzer: BatchAnalyzer) -> PointsCalculator:
    """
    Factory function to create a fully configured prediction engine.
    
    Args:
        player_stats: Player statistics engine
        batch_analyzer: Batch analyzer
        
    Returns:
        Configured PointsCalculator
    """
    event_calc = EventProbabilityCalculator(player_stats, batch_analyzer)
    return PointsCalculator(player_stats, batch_analyzer, event_calc)

