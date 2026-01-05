"""
Weighted average calculations for combining statistics

Uses Bayesian-inspired weighting to combine batch-specific stats
with overall averages based on sample size and reliability.
"""

from typing import List, Tuple, Optional, Dict
import math
from dataclasses import dataclass

from ..config import STATS_CONFIG


@dataclass
class WeightedResult:
    """Result of a weighted calculation"""
    value: float
    confidence: float
    components: Dict[str, Tuple[float, float]]  # name -> (value, weight)


class WeightedAverageCalculator:
    """
    Calculates weighted averages for combining multiple data sources.
    
    Uses concepts from Bayesian statistics to weight specific observations
    against prior expectations based on sample size.
    """
    
    def __init__(self,
                 batch_weight: float = None,
                 form_weight: float = None,
                 regression_factor: float = None):
        """
        Initialize the calculator.
        
        Args:
            batch_weight: Weight for batch-specific stats vs overall
            form_weight: Weight for recent form vs season average
            regression_factor: How much to regress extreme values to mean
        """
        self.batch_weight = batch_weight or STATS_CONFIG.BATCH_WEIGHT_FACTOR
        self.form_weight = form_weight or STATS_CONFIG.FORM_WEIGHT
        self.regression_factor = regression_factor or STATS_CONFIG.REGRESSION_FACTOR
    
    def combine_with_prior(self, 
                           observed_value: float,
                           observed_n: int,
                           prior_value: float,
                           prior_strength: int = 10) -> WeightedResult:
        """
        Combine an observed statistic with a prior expectation.
        
        Uses a simple Bayesian-like update where the weight of observations
        increases with sample size.
        
        Args:
            observed_value: The observed statistic
            observed_n: Number of observations
            prior_value: Prior expectation (e.g., league average)
            prior_strength: Equivalent number of observations for prior
            
        Returns:
            WeightedResult with combined value
        """
        total_weight = observed_n + prior_strength
        
        if total_weight <= 0:
            return WeightedResult(
                value=prior_value,
                confidence=0.0,
                components={'prior': (prior_value, 1.0)}
            )
        
        observed_weight = observed_n / total_weight
        prior_weight = prior_strength / total_weight
        
        combined = (observed_value * observed_weight) + (prior_value * prior_weight)
        
        # Confidence increases with more observations
        confidence = min(observed_n / (prior_strength * 2), 1.0)
        
        return WeightedResult(
            value=combined,
            confidence=confidence,
            components={
                'observed': (observed_value, observed_weight),
                'prior': (prior_value, prior_weight)
            }
        )
    
    def combine_batch_and_overall(self,
                                   batch_value: float,
                                   batch_games: int,
                                   overall_value: float,
                                   overall_games: int) -> WeightedResult:
        """
        Combine batch-specific stats with overall stats.
        
        Uses configurable batch weight with sample size adjustment.
        
        Args:
            batch_value: Stat from games against specific batch
            batch_games: Number of games against that batch
            overall_value: Stat from all games
            overall_games: Total games played
            
        Returns:
            WeightedResult with combined value
        """
        if batch_games <= 0:
            return WeightedResult(
                value=overall_value,
                confidence=0.3,
                components={'overall': (overall_value, 1.0)}
            )
        
        if overall_games <= 0:
            return WeightedResult(
                value=batch_value,
                confidence=0.3,
                components={'batch': (batch_value, 1.0)}
            )
        
        # Adjust batch weight based on sample size
        # More batch games = more trust in batch-specific stats
        sample_factor = min(batch_games / 5, 1.0)  # Full weight at 5+ games
        effective_batch_weight = self.batch_weight * sample_factor
        
        overall_weight = 1 - effective_batch_weight
        
        combined = (batch_value * effective_batch_weight) + (overall_value * overall_weight)
        
        # Confidence based on total sample
        confidence = min((batch_games + overall_games) / 20, 1.0)
        
        return WeightedResult(
            value=combined,
            confidence=confidence,
            components={
                'batch': (batch_value, effective_batch_weight),
                'overall': (overall_value, overall_weight)
            }
        )
    
    def combine_form_and_season(self,
                                 recent_value: float,
                                 recent_games: int,
                                 season_value: float,
                                 season_games: int) -> WeightedResult:
        """
        Combine recent form with season average.
        
        Recent form captures current performance trends.
        
        Args:
            recent_value: Stat from recent games
            recent_games: Number of recent games
            season_value: Season average
            season_games: Total games this season
            
        Returns:
            WeightedResult with combined value
        """
        if recent_games <= 0:
            return WeightedResult(
                value=season_value,
                confidence=0.4,
                components={'season': (season_value, 1.0)}
            )
        
        if season_games <= 0:
            return WeightedResult(
                value=recent_value,
                confidence=0.3,
                components={'recent': (recent_value, 1.0)}
            )
        
        # Adjust form weight based on how many recent games
        form_factor = min(recent_games / STATS_CONFIG.RECENT_GAMES_COUNT, 1.0)
        effective_form_weight = self.form_weight * form_factor
        
        season_weight = 1 - effective_form_weight
        
        combined = (recent_value * effective_form_weight) + (season_value * season_weight)
        
        return WeightedResult(
            value=combined,
            confidence=form_factor,
            components={
                'recent': (recent_value, effective_form_weight),
                'season': (season_value, season_weight)
            }
        )
    
    def regress_to_mean(self, 
                        value: float,
                        mean: float,
                        sample_size: int,
                        min_sample_for_full_value: int = 15) -> float:
        """
        Regress an extreme value toward the mean.
        
        With small samples, extreme values are likely to regress.
        
        Args:
            value: Observed value
            mean: Population/league mean
            sample_size: Number of observations
            min_sample_for_full_value: Games needed to trust observed value
            
        Returns:
            Regressed value
        """
        if sample_size >= min_sample_for_full_value:
            return value
        
        # Calculate regression amount
        # More regression with smaller samples
        regression_amount = 1 - (sample_size / min_sample_for_full_value)
        regression_amount *= (1 - self.regression_factor)
        
        # Regress toward mean
        regressed = value - (regression_amount * (value - mean))
        
        return regressed
    
    def calculate_multi_source_average(self,
                                        sources: List[Tuple[str, float, float]]) -> WeightedResult:
        """
        Calculate weighted average from multiple sources.
        
        Args:
            sources: List of (name, value, weight) tuples
            
        Returns:
            WeightedResult with combined value
        """
        if not sources:
            return WeightedResult(value=0.0, confidence=0.0, components={})
        
        total_weight = sum(w for _, _, w in sources)
        
        if total_weight <= 0:
            # Equal weights fallback
            avg = sum(v for _, v, _ in sources) / len(sources)
            return WeightedResult(
                value=avg,
                confidence=0.5,
                components={name: (val, 1/len(sources)) for name, val, _ in sources}
            )
        
        # Normalize weights
        normalized = [(name, val, w/total_weight) for name, val, w in sources]
        
        weighted_sum = sum(val * w for _, val, w in normalized)
        
        return WeightedResult(
            value=weighted_sum,
            confidence=min(total_weight, 1.0),
            components={name: (val, w) for name, val, w in normalized}
        )


def exponential_decay_weight(games_ago: int, decay_rate: float = 0.9) -> float:
    """
    Calculate exponential decay weight for a game.
    
    More recent games get higher weight.
    
    Args:
        games_ago: How many games ago (0 = most recent)
        decay_rate: Decay factor per game (0.9 = 10% reduction per game)
        
    Returns:
        Weight for that game
    """
    return math.pow(decay_rate, games_ago)


def calculate_ewma(values: List[float], alpha: float = 0.3) -> float:
    """
    Calculate Exponentially Weighted Moving Average.
    
    Args:
        values: List of values (most recent last)
        alpha: Smoothing factor (higher = more weight to recent)
        
    Returns:
        EWMA value
    """
    if not values:
        return 0.0
    
    ewma = values[0]
    for val in values[1:]:
        ewma = alpha * val + (1 - alpha) * ewma
    
    return ewma

