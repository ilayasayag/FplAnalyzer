"""
Prediction result models for FPL predictor
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class PredictionBreakdown:
    """Detailed breakdown of how expected points were calculated"""
    
    # Playing time
    playing_prob_60_plus: float = 0.0
    playing_prob_1_59: float = 0.0
    playing_points: float = 0.0
    
    # Goals
    expected_goals: float = 0.0
    goal_points: float = 0.0
    
    # Assists
    expected_assists: float = 0.0
    assist_points: float = 0.0
    
    # Clean sheets
    clean_sheet_prob: float = 0.0
    clean_sheet_points: float = 0.0
    
    # Goalkeeper specific
    expected_saves: float = 0.0
    saves_points: float = 0.0
    
    # Conceded penalty (GK/DEF)
    expected_goals_conceded: float = 0.0
    conceded_penalty: float = 0.0
    
    # Bonus
    expected_bonus: float = 0.0
    
    # Cards
    yellow_card_risk: float = 0.0
    yellow_card_penalty: float = 0.0
    
    # Own goals
    own_goal_risk: float = 0.0
    own_goal_penalty: float = 0.0
    
    @property
    def total_expected_points(self) -> float:
        """Calculate total expected points"""
        return (
            self.playing_points +
            self.goal_points +
            self.assist_points +
            self.clean_sheet_points +
            self.saves_points +
            self.expected_bonus +
            self.conceded_penalty +  # Already negative
            self.yellow_card_penalty +  # Already negative
            self.own_goal_penalty  # Already negative
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'playing': {
                'prob_60_plus': round(self.playing_prob_60_plus, 3),
                'prob_1_59': round(self.playing_prob_1_59, 3),
                'points': round(self.playing_points, 2),
            },
            'goals': {
                'expected': round(self.expected_goals, 3),
                'points': round(self.goal_points, 2),
            },
            'assists': {
                'expected': round(self.expected_assists, 3),
                'points': round(self.assist_points, 2),
            },
            'clean_sheet': {
                'probability': round(self.clean_sheet_prob, 3),
                'points': round(self.clean_sheet_points, 2),
            },
            'saves': {
                'expected': round(self.expected_saves, 2),
                'points': round(self.saves_points, 2),
            },
            'conceded': {
                'expected': round(self.expected_goals_conceded, 2),
                'penalty': round(self.conceded_penalty, 2),
            },
            'bonus': {
                'expected': round(self.expected_bonus, 2),
            },
            'cards': {
                'yellow_risk': round(self.yellow_card_risk, 3),
                'penalty': round(self.yellow_card_penalty, 2),
            },
            'total': round(self.total_expected_points, 2),
        }
    
    def to_short_string(self) -> str:
        """Get a short summary string"""
        parts = []
        if self.expected_goals > 0.05:
            parts.append(f"{self.expected_goals:.1f}g")
        if self.expected_assists > 0.05:
            parts.append(f"{self.expected_assists:.1f}a")
        if self.clean_sheet_prob > 0.1:
            parts.append(f"{self.clean_sheet_prob*100:.0f}%CS")
        if self.expected_bonus > 0.2:
            parts.append(f"+{self.expected_bonus:.1f}b")
        return " ".join(parts) if parts else "2pts base"


@dataclass
class Prediction:
    """A prediction for a player's expected points in a gameweek"""
    
    # Player info
    player_id: int
    player_name: str
    position: str
    team: str
    
    # Opponent info
    gameweek: int
    opponent_id: int
    opponent_name: str
    opponent_short: str
    opponent_position: int
    opponent_batch: str
    is_home: bool
    
    # Prediction results
    expected_points: float
    breakdown: PredictionBreakdown = field(default_factory=PredictionBreakdown)
    
    # Confidence/reliability metrics
    confidence: float = 0.5  # 0-1 based on data quality
    sample_size: int = 0  # Games used to calculate
    data_quality: str = "medium"  # low/medium/high
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    @property
    def fixture_string(self) -> str:
        """Human-readable fixture string"""
        if self.is_home:
            return f"vs {self.opponent_short}"
        return f"@ {self.opponent_short}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'player': {
                'id': self.player_id,
                'name': self.player_name,
                'position': self.position,
                'team': self.team,
            },
            'fixture': {
                'gameweek': self.gameweek,
                'opponent': self.opponent_name,
                'opponent_short': self.opponent_short,
                'opponent_position': self.opponent_position,
                'opponent_batch': self.opponent_batch,
                'is_home': self.is_home,
                'fixture_string': self.fixture_string,
            },
            'prediction': {
                'expected_points': round(self.expected_points, 2),
                'breakdown': self.breakdown.to_dict(),
                'breakdown_short': self.breakdown.to_short_string(),
            },
            'confidence': {
                'score': round(self.confidence, 2),
                'sample_size': self.sample_size,
                'data_quality': self.data_quality,
            },
            'warnings': self.warnings,
        }


@dataclass
class SquadPrediction:
    """Predictions for an entire squad"""
    
    squad_name: str
    entry_id: int
    gameweek: int
    
    # Individual predictions
    predictions: List[Prediction] = field(default_factory=list)
    
    # Optimal 11 selection
    optimal_11: List[Prediction] = field(default_factory=list)
    optimal_formation: str = ""
    
    @property
    def total_expected_points(self) -> float:
        """Total expected points for optimal 11"""
        return sum(p.expected_points for p in self.optimal_11)
    
    @property
    def all_players_expected(self) -> float:
        """Total expected points if all 15 played"""
        return sum(p.expected_points for p in self.predictions)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'squad_name': self.squad_name,
            'entry_id': self.entry_id,
            'gameweek': self.gameweek,
            'total_expected': round(self.total_expected_points, 2),
            'optimal_formation': self.optimal_formation,
            'optimal_11': [p.to_dict() for p in self.optimal_11],
            'bench': [p.to_dict() for p in self.predictions if p not in self.optimal_11],
            'all_players': [p.to_dict() for p in self.predictions],
        }

