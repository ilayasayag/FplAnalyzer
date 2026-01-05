"""
Player data models for FPL predictor
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class PlayerGameweek:
    """Represents a player's performance in a single gameweek"""
    
    gameweek: int
    opponent_team_id: int
    opponent_team_name: str
    was_home: bool
    
    # Playing time
    minutes: int
    
    # Attacking stats
    goals_scored: int = 0
    assists: int = 0
    
    # Defensive stats
    clean_sheets: int = 0
    goals_conceded: int = 0
    
    # Goalkeeper specific
    saves: int = 0
    penalties_saved: int = 0
    
    # Defensive contribution
    tackles: int = 0
    interceptions: int = 0
    clearances_blocks_interceptions: int = 0  # Combined stat from FPL
    
    # Disciplinary
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    penalties_missed: int = 0
    
    # Points
    total_points: int = 0
    bonus: int = 0
    bps: int = 0  # Bonus Point System score
    
    # Opponent info (to be filled from standings)
    opponent_position: Optional[int] = None
    opponent_batch: Optional[tuple] = None
    
    @property
    def defensive_contribution(self) -> int:
        """Total defensive contribution"""
        return self.clearances_blocks_interceptions + self.tackles
    
    @property
    def played_full_game(self) -> bool:
        """Whether player played 60+ minutes"""
        return self.minutes >= 60
    
    @property
    def played_any(self) -> bool:
        """Whether player made an appearance"""
        return self.minutes > 0
    
    @classmethod
    def from_fpl_history(cls, gw_data: Dict[str, Any], team_map: Dict[int, str]) -> 'PlayerGameweek':
        """Create from FPL API history data"""
        opponent_id = gw_data.get('opponent_team', 0)
        
        return cls(
            gameweek=gw_data.get('round', gw_data.get('event', 0)),
            opponent_team_id=opponent_id,
            opponent_team_name=team_map.get(opponent_id, f"Team {opponent_id}"),
            was_home=gw_data.get('was_home', False),
            minutes=gw_data.get('minutes', 0),
            goals_scored=gw_data.get('goals_scored', 0),
            assists=gw_data.get('assists', 0),
            clean_sheets=gw_data.get('clean_sheets', 0),
            goals_conceded=gw_data.get('goals_conceded', 0),
            saves=gw_data.get('saves', 0),
            penalties_saved=gw_data.get('penalties_saved', 0),
            tackles=gw_data.get('tackles', 0),
            interceptions=gw_data.get('interceptions', 0),
            clearances_blocks_interceptions=gw_data.get('clearances_blocks_interceptions', 0),
            yellow_cards=gw_data.get('yellow_cards', 0),
            red_cards=gw_data.get('red_cards', 0),
            own_goals=gw_data.get('own_goals', 0),
            penalties_missed=gw_data.get('penalties_missed', 0),
            total_points=gw_data.get('total_points', 0),
            bonus=gw_data.get('bonus', 0),
            bps=gw_data.get('bps', 0),
        )


@dataclass
class Player:
    """Represents an FPL player with their season data"""
    
    # Identifiers
    id: int
    web_name: str
    first_name: str = ""
    second_name: str = ""
    
    # Team info
    team_id: int = 0
    team_name: str = ""
    team_short: str = ""
    
    # Position (1=GK, 2=DEF, 3=MID, 4=FWD)
    position: int = 3  # Default to MID
    
    # Season totals (from bootstrap-static)
    total_points: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    minutes: int = 0
    goals_conceded: int = 0
    saves: int = 0
    bonus: int = 0
    bps: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    
    # Form and status
    form: float = 0.0
    points_per_game: float = 0.0
    news: str = ""
    chance_of_playing_next_round: Optional[int] = None
    
    # Gameweek history
    gameweeks: List[PlayerGameweek] = field(default_factory=list)
    
    @property
    def position_name(self) -> str:
        """Human-readable position name"""
        return {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}.get(self.position, 'UNK')
    
    @property
    def games_played(self) -> int:
        """Number of games with at least 1 minute played"""
        return len([gw for gw in self.gameweeks if gw.minutes > 0])
    
    @property
    def full_name(self) -> str:
        """Full player name"""
        return f"{self.first_name} {self.second_name}".strip() or self.web_name
    
    def get_games_vs_batch(self, batch: tuple, min_minutes: int = 10) -> List[PlayerGameweek]:
        """Get all games played against teams in a specific batch"""
        return [
            gw for gw in self.gameweeks
            if gw.opponent_batch == batch and gw.minutes >= min_minutes
        ]
    
    def get_recent_games(self, count: int = 5, min_minutes: int = 10) -> List[PlayerGameweek]:
        """Get most recent games with meaningful playing time"""
        valid_games = [gw for gw in self.gameweeks if gw.minutes >= min_minutes]
        return sorted(valid_games, key=lambda x: x.gameweek, reverse=True)[:count]
    
    @classmethod
    def from_fpl_data(cls, bootstrap_element: Dict[str, Any], 
                      team_map: Dict[int, str],
                      history: Optional[List[Dict[str, Any]]] = None) -> 'Player':
        """Create Player from FPL bootstrap-static element data"""
        team_id = bootstrap_element.get('team', 0)
        
        player = cls(
            id=bootstrap_element.get('id', 0),
            web_name=bootstrap_element.get('web_name', 'Unknown'),
            first_name=bootstrap_element.get('first_name', ''),
            second_name=bootstrap_element.get('second_name', ''),
            team_id=team_id,
            team_name=team_map.get(team_id, f"Team {team_id}"),
            position=bootstrap_element.get('element_type', 3),
            total_points=bootstrap_element.get('total_points', 0),
            goals_scored=bootstrap_element.get('goals_scored', 0),
            assists=bootstrap_element.get('assists', 0),
            clean_sheets=bootstrap_element.get('clean_sheets', 0),
            minutes=bootstrap_element.get('minutes', 0),
            goals_conceded=bootstrap_element.get('goals_conceded', 0),
            saves=bootstrap_element.get('saves', 0),
            bonus=bootstrap_element.get('bonus', 0),
            bps=bootstrap_element.get('bps', 0),
            yellow_cards=bootstrap_element.get('yellow_cards', 0),
            red_cards=bootstrap_element.get('red_cards', 0),
            form=float(bootstrap_element.get('form', 0) or 0),
            points_per_game=float(bootstrap_element.get('points_per_game', 0) or 0),
            news=bootstrap_element.get('news', ''),
            chance_of_playing_next_round=bootstrap_element.get('chance_of_playing_next_round'),
        )
        
        # Parse gameweek history if provided
        if history:
            player.gameweeks = [
                PlayerGameweek.from_fpl_history(gw, team_map)
                for gw in history
            ]
        
        return player
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'web_name': self.web_name,
            'full_name': self.full_name,
            'team': self.team_name,
            'team_short': self.team_short,
            'position': self.position_name,
            'total_points': self.total_points,
            'games_played': self.games_played,
            'form': self.form,
            'ppg': self.points_per_game,
        }

