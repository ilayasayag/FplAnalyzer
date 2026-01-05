"""
Team and batch data models for FPL predictor
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple


@dataclass
class TeamStats:
    """Statistics for a team's performance"""
    
    games_played: int = 0
    
    # Goals
    goals_scored: int = 0
    goals_conceded: int = 0
    
    # Clean sheets
    clean_sheets: int = 0
    
    # Points
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    
    @property
    def goals_per_game(self) -> float:
        """Average goals scored per game"""
        return self.goals_scored / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def goals_conceded_per_game(self) -> float:
        """Average goals conceded per game"""
        return self.goals_conceded / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def clean_sheet_rate(self) -> float:
        """Percentage of games with clean sheet"""
        return self.clean_sheets / self.games_played if self.games_played > 0 else 0.0
    
    @property
    def goal_difference(self) -> int:
        """Goal difference"""
        return self.goals_scored - self.goals_conceded


@dataclass
class Team:
    """Represents a Premier League team"""
    
    # Identifiers
    id: int
    name: str
    short_name: str = ""
    
    # Current league position
    position: int = 0
    
    # Season stats
    overall_stats: TeamStats = field(default_factory=TeamStats)
    
    # Stats vs different batches (batch tuple -> TeamStats)
    stats_vs_batch: Dict[Tuple[int, int], TeamStats] = field(default_factory=dict)
    
    # Home/Away split
    home_stats: TeamStats = field(default_factory=TeamStats)
    away_stats: TeamStats = field(default_factory=TeamStats)
    
    @property
    def points(self) -> int:
        """Total league points"""
        return self.overall_stats.points
    
    @property
    def goal_difference(self) -> int:
        """Total goal difference"""
        return self.overall_stats.goal_difference
    
    def get_expected_goals_vs_batch(self, batch: Tuple[int, int]) -> float:
        """Get expected goals scored against teams in a batch"""
        batch_stats = self.stats_vs_batch.get(batch)
        if batch_stats and batch_stats.games_played >= 2:
            # Use batch-specific stats with weight
            return batch_stats.goals_per_game
        # Fallback to overall average
        return self.overall_stats.goals_per_game
    
    def get_expected_conceded_vs_batch(self, batch: Tuple[int, int]) -> float:
        """Get expected goals conceded against teams in a batch"""
        batch_stats = self.stats_vs_batch.get(batch)
        if batch_stats and batch_stats.games_played >= 2:
            return batch_stats.goals_conceded_per_game
        return self.overall_stats.goals_conceded_per_game
    
    def get_clean_sheet_prob_vs_batch(self, batch: Tuple[int, int]) -> float:
        """Get clean sheet probability against teams in a batch"""
        batch_stats = self.stats_vs_batch.get(batch)
        if batch_stats and batch_stats.games_played >= 2:
            return batch_stats.clean_sheet_rate
        return self.overall_stats.clean_sheet_rate
    
    @classmethod
    def from_fpl_bootstrap(cls, team_data: Dict[str, Any]) -> 'Team':
        """Create Team from FPL bootstrap-static teams data"""
        return cls(
            id=team_data.get('id', 0),
            name=team_data.get('name', 'Unknown'),
            short_name=team_data.get('short_name', ''),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'short_name': self.short_name,
            'position': self.position,
            'points': self.points,
            'goal_difference': self.goal_difference,
            'goals_per_game': round(self.overall_stats.goals_per_game, 2),
            'goals_conceded_per_game': round(self.overall_stats.goals_conceded_per_game, 2),
            'clean_sheet_rate': round(self.overall_stats.clean_sheet_rate, 2),
        }


@dataclass
class TeamBatch:
    """Represents a batch/tier of teams by league position"""
    
    # Batch definition
    start_position: int
    end_position: int
    name: str = ""
    
    # Teams in this batch
    teams: List[Team] = field(default_factory=list)
    
    @property
    def batch_tuple(self) -> Tuple[int, int]:
        """Get batch as tuple for dictionary keys"""
        return (self.start_position, self.end_position)
    
    @property
    def team_ids(self) -> List[int]:
        """Get list of team IDs in this batch"""
        return [team.id for team in self.teams]
    
    @property
    def average_goals_per_game(self) -> float:
        """Average goals scored per game by teams in this batch"""
        if not self.teams:
            return 0.0
        total = sum(t.overall_stats.goals_per_game for t in self.teams)
        return total / len(self.teams)
    
    @property
    def average_goals_conceded_per_game(self) -> float:
        """Average goals conceded per game by teams in this batch"""
        if not self.teams:
            return 0.0
        total = sum(t.overall_stats.goals_conceded_per_game for t in self.teams)
        return total / len(self.teams)
    
    @property
    def average_clean_sheet_rate(self) -> float:
        """Average clean sheet rate of teams in this batch"""
        if not self.teams:
            return 0.0
        total = sum(t.overall_stats.clean_sheet_rate for t in self.teams)
        return total / len(self.teams)
    
    def contains_team(self, team_id: int) -> bool:
        """Check if a team is in this batch"""
        return team_id in self.team_ids
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'range': f"{self.start_position}-{self.end_position}",
            'name': self.name,
            'teams': [t.short_name or t.name for t in self.teams],
            'avg_goals_per_game': round(self.average_goals_per_game, 2),
            'avg_goals_conceded': round(self.average_goals_conceded_per_game, 2),
            'avg_clean_sheet_rate': round(self.average_clean_sheet_rate, 2),
        }

