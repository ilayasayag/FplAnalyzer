"""
Configuration for FPL Predictor.

Contains settings for prediction sources, weights, and other configuration.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Tuple, List, Optional, Dict


# Position constants (matches FPL API)
class Position:
    """Player position constants"""
    GK = 1
    DEF = 2
    MID = 3
    FWD = 4


@dataclass
class StatsConfig:
    """Statistical analysis configuration"""
    MIN_MINUTES_PLAYED: int = 10      # Ignore games with < 10 min
    OUTLIER_SIGMA: float = 2.0        # Std devs for outlier detection
    MIN_BATCH_GAMES: int = 2          # Min games for reliable batch stats
    BATCH_WEIGHT_FACTOR: float = 0.6  # Weight for batch vs overall
    FORM_WEIGHT: float = 0.4          # Weight for recent form
    RECENT_GAMES_COUNT: int = 5       # Number of games to consider for form
    REGRESSION_FACTOR: float = 0.3    # Regression to mean factor


@dataclass
class ScoringRules:
    """FPL scoring rules"""
    MINUTES_60_PLUS: int = 2
    MINUTES_1_59: int = 1
    
    # Goals by position
    GOALS: Dict[int, int] = None
    
    # Clean sheets by position
    CLEAN_SHEET: Dict[int, int] = None
    
    # Other scoring
    ASSIST: int = 3
    SAVES_PER_POINT: int = 3  # 3 saves = 1 point
    PENALTY_SAVE: int = 5
    PENALTY_MISS: int = -2
    GOALS_CONCEDED_PER_PENALTY: int = 2  # 2 goals conceded = -1 point
    YELLOW_CARD: int = -1
    RED_CARD: int = -3
    OWN_GOAL: int = -2
    
    def __post_init__(self):
        if self.GOALS is None:
            self.GOALS = {
                Position.GK: 6,
                Position.DEF: 6,
                Position.MID: 5,
                Position.FWD: 4
            }
        if self.CLEAN_SHEET is None:
            self.CLEAN_SHEET = {
                Position.GK: 4,
                Position.DEF: 4,
                Position.MID: 1,
                Position.FWD: 0
            }


# Directory paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'fpl_predictor' / 'output'

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# API Configuration
API_TIMEOUT = 10  # seconds
STANDINGS_CACHE_DURATION = 3600  # 1 hour in seconds
FOOTBALL_DATA_API_URL = "https://api.football-data.org/v4"
FOOTBALL_DATA_COMPETITION_ID = 2021  # Premier League

# Batch definitions
DEFAULT_BATCHES: List[Tuple[int, int]] = [
    (1, 4),    # Top 4
    (5, 8),    # Upper mid
    (9, 12),   # Mid table
    (13, 16),  # Lower mid
    (17, 20),  # Relegation
]

# Batch names mapping
BATCH_NAMES = {
    (1, 4): "Top 4",
    (5, 8): "Upper Mid",
    (9, 12): "Mid Table",
    (13, 16): "Lower Mid",
    (17, 20): "Relegation"
}

# Configuration instances
STATS_CONFIG = StatsConfig()
SCORING = ScoringRules()


def get_batch_for_position(position: int, batches: List[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
    """
    Get batch tuple for a given league position.
    
    Args:
        position: League position (1-20)
        batches: List of batch tuples (default: DEFAULT_BATCHES)
        
    Returns:
        Batch tuple or None if not found
    """
    if batches is None:
        batches = DEFAULT_BATCHES
    
    for start, end in batches:
        if start <= position <= end:
            return (start, end)
    return None


def get_batch_name(batch: Tuple[int, int]) -> str:
    """
    Get human-readable name for a batch.
    
    Args:
        batch: Batch tuple (start, end)
        
    Returns:
        Batch name or "Unknown Batch"
    """
    return BATCH_NAMES.get(batch, f"Positions {batch[0]}-{batch[1]}")


# Prediction Source Configuration
# Each source can be enabled/disabled and has a weight for aggregation
PREDICTION_SOURCES = {
    'rotowire_enhanced': {
        'weight': 0.6,
        'enabled': True,
        'name': 'RotoWire + Premier Injuries',
        'description': 'Stable source with 340+ predictions per gameweek'
    },
    'ffscout': {
        'weight': 0.4,
        'enabled': True,  # Re-enabled with text extraction approach!
        'name': 'Fantasy Football Scout',
        'description': 'Team news with percentage-based injury doubts (text extraction)'
    }
}


def get_enabled_sources():
    """
    Get list of enabled prediction sources.
    
    Returns:
        List of tuples: [(source_key, source_config), ...]
    """
    return [(key, config) for key, config in PREDICTION_SOURCES.items() if config['enabled']]


def get_source_weights():
    """
    Get weights for enabled sources (for weighted aggregation).
    
    Returns:
        Dict: {source_key: weight, ...}
    """
    return {key: config['weight'] for key, config in PREDICTION_SOURCES.items() if config['enabled']}


def get_total_weight():
    """
    Get total weight of enabled sources.
    
    Returns:
        Float: Sum of all enabled source weights
    """
    return sum(config['weight'] for config in PREDICTION_SOURCES.values() if config['enabled'])
