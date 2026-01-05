"""
FPL Score Predictor Configuration

Contains FPL scoring rules, team batch definitions, and system constants.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
from enum import IntEnum


class Position(IntEnum):
    """FPL position IDs"""
    GK = 1
    DEF = 2
    MID = 3
    FWD = 4


# =============================================================================
# FPL SCORING RULES (2024/25 Season)
# =============================================================================

@dataclass(frozen=True)
class ScoringRules:
    """FPL points for each action by position"""
    
    # Playing time points
    MINUTES_1_59: int = 1
    MINUTES_60_PLUS: int = 2
    
    # Goals scored by position
    GOALS: Dict[Position, int] = None
    
    # Assists (same for all positions)
    ASSIST: int = 3
    
    # Clean sheets by position (must play 60+ mins)
    CLEAN_SHEET: Dict[Position, int] = None
    
    # Goalkeeper specific
    SAVES_PER_POINT: int = 3  # 1 point per 3 saves
    PENALTY_SAVE: int = 5
    
    # Penalties
    PENALTY_MISS: int = -2
    
    # Goals conceded (GK/DEF only, must play 60+ mins)
    GOALS_CONCEDED_PER_PENALTY: int = 2  # -1 point per 2 goals conceded
    
    # Disciplinary
    YELLOW_CARD: int = -1
    RED_CARD: int = -3
    OWN_GOAL: int = -2
    
    # Bonus points (awarded based on BPS - Bonus Point System)
    BONUS_MAX: int = 3
    BONUS_MID: int = 2
    BONUS_MIN: int = 1
    
    def __post_init__(self):
        # Initialize mutable defaults
        object.__setattr__(self, 'GOALS', {
            Position.GK: 6,
            Position.DEF: 6,
            Position.MID: 5,
            Position.FWD: 4
        })
        object.__setattr__(self, 'CLEAN_SHEET', {
            Position.GK: 4,
            Position.DEF: 4,
            Position.MID: 1,
            Position.FWD: 0
        })


# Global scoring rules instance
SCORING = ScoringRules()


# =============================================================================
# TEAM BATCH CONFIGURATION
# =============================================================================

# Default batch definitions: (start_position, end_position)
DEFAULT_BATCHES: List[Tuple[int, int]] = [
    (1, 4),    # Top 4 - Title contenders / Champions League
    (5, 8),    # Upper mid-table - Europa League contenders
    (9, 12),   # Mid-table
    (13, 16),  # Lower mid-table
    (17, 20),  # Relegation zone
]

# Batch names for display
BATCH_NAMES: Dict[Tuple[int, int], str] = {
    (1, 4): "Top 4",
    (5, 8): "Upper Mid",
    (9, 12): "Mid Table",
    (13, 16): "Lower Mid",
    (17, 20): "Relegation",
}


def get_batch_for_position(position: int, batches: List[Tuple[int, int]] = None) -> Tuple[int, int]:
    """Get the batch tuple for a given league position"""
    if batches is None:
        batches = DEFAULT_BATCHES
    
    for start, end in batches:
        if start <= position <= end:
            return (start, end)
    
    # Fallback for invalid positions
    return batches[-1] if position > 20 else batches[0]


def get_batch_name(batch: Tuple[int, int]) -> str:
    """Get human-readable name for a batch"""
    return BATCH_NAMES.get(batch, f"{batch[0]}-{batch[1]}")


# =============================================================================
# STATISTICAL PARAMETERS
# =============================================================================

@dataclass(frozen=True)
class StatsConfig:
    """Configuration for statistical calculations"""
    
    # Minimum minutes to count a game appearance
    MIN_MINUTES_PLAYED: int = 10
    
    # Minutes threshold for clean sheet eligibility
    CLEAN_SHEET_MINUTES: int = 60
    
    # Standard deviation multiplier for outlier detection
    OUTLIER_SIGMA: float = 2.0
    
    # Minimum games in a batch for reliable stats
    MIN_BATCH_GAMES: int = 2
    
    # Weight given to batch-specific stats vs overall stats
    # Higher = more weight to batch-specific
    BATCH_WEIGHT_FACTOR: float = 0.6
    
    # Regression to mean factor (0 = full regression, 1 = no regression)
    REGRESSION_FACTOR: float = 0.7
    
    # Sample size for "recent form" calculations
    RECENT_GAMES_COUNT: int = 5
    
    # Weight for recent form vs season average
    FORM_WEIGHT: float = 0.4


STATS_CONFIG = StatsConfig()


# =============================================================================
# FPL TEAM MAPPINGS
# =============================================================================

# Short code to full name mapping
TEAM_SHORT_TO_FULL: Dict[str, str] = {
    'ARS': 'Arsenal',
    'AVL': 'Aston Villa',
    'BOU': 'Bournemouth',
    'BRE': 'Brentford',
    'BHA': 'Brighton',
    'CHE': 'Chelsea',
    'CRY': 'Crystal Palace',
    'EVE': 'Everton',
    'FUL': 'Fulham',
    'IPS': 'Ipswich',
    'LEI': 'Leicester',
    'LIV': 'Liverpool',
    'MCI': 'Man City',
    'MUN': 'Man Utd',
    'NEW': 'Newcastle',
    'NFO': "Nott'm Forest",
    'SOU': 'Southampton',
    'TOT': 'Spurs',
    'WHU': 'West Ham',
    'WOL': 'Wolves',
}

# Reverse mapping
TEAM_FULL_TO_SHORT: Dict[str, str] = {v: k for k, v in TEAM_SHORT_TO_FULL.items()}


# =============================================================================
# API CONFIGURATION
# =============================================================================

# Football-Data.org API (free tier)
FOOTBALL_DATA_API_URL = "https://api.football-data.org/v4"
FOOTBALL_DATA_COMPETITION_ID = "PL"  # Premier League

# FPL Draft API base URL
FPL_DRAFT_API_URL = "https://draft.premierleague.com/api"

# API request timeout in seconds
API_TIMEOUT = 30

# Cache duration for standings (in seconds)
STANDINGS_CACHE_DURATION = 3600  # 1 hour


# =============================================================================
# FILE PATHS
# =============================================================================

import os

# Default paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'exported_data')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

