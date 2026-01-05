"""
Outlier filtering and data cleaning utilities

Handles edge cases like injuries, rotation, and exceptional performances
to improve prediction accuracy.
"""

from typing import List, Tuple, Optional
import statistics
from dataclasses import dataclass

from ..config import STATS_CONFIG
from ..models.player import Player, PlayerGameweek


@dataclass
class FilteredStats:
    """Result of filtering with metadata"""
    games: List[PlayerGameweek]
    removed_count: int
    removal_reasons: List[str]
    

class OutlierFilter:
    """
    Filters and adjusts player gameweek data to remove outliers
    and improve statistical reliability.
    """
    
    def __init__(self, 
                 min_minutes: int = None,
                 outlier_sigma: float = None):
        """
        Initialize the outlier filter.
        
        Args:
            min_minutes: Minimum minutes to count as a valid appearance
            outlier_sigma: Standard deviations for outlier detection
        """
        self.min_minutes = min_minutes or STATS_CONFIG.MIN_MINUTES_PLAYED
        self.outlier_sigma = outlier_sigma or STATS_CONFIG.OUTLIER_SIGMA
    
    def filter_games(self, games: List[PlayerGameweek], 
                     remove_injury_games: bool = True,
                     dampen_outliers: bool = True) -> FilteredStats:
        """
        Filter gameweek data to remove unreliable entries.
        
        Args:
            games: List of player gameweeks
            remove_injury_games: Remove games with very low minutes
            dampen_outliers: Cap extreme performances
            
        Returns:
            FilteredStats with cleaned data and metadata
        """
        filtered = list(games)
        removal_reasons = []
        removed_count = 0
        
        # 1. Remove injury/rotation games (very low minutes)
        if remove_injury_games:
            before_count = len(filtered)
            filtered = [g for g in filtered if g.minutes >= self.min_minutes]
            removed = before_count - len(filtered)
            if removed > 0:
                removed_count += removed
                removal_reasons.append(f"Low minutes (<{self.min_minutes}): {removed}")
        
        # 2. Identify and flag outliers (but don't remove, just mark)
        if dampen_outliers and len(filtered) >= 3:
            # We don't remove outliers, but we'll track them
            points = [g.total_points for g in filtered]
            outlier_indices = self._find_outlier_indices(points)
            if outlier_indices:
                removal_reasons.append(f"Outlier games flagged: {len(outlier_indices)}")
        
        return FilteredStats(
            games=filtered,
            removed_count=removed_count,
            removal_reasons=removal_reasons
        )
    
    def _find_outlier_indices(self, values: List[float]) -> List[int]:
        """
        Find indices of outlier values using IQR method.
        
        Args:
            values: List of values to check
            
        Returns:
            List of indices that are outliers
        """
        if len(values) < 3:
            return []
        
        sorted_values = sorted(values)
        q1_idx = len(sorted_values) // 4
        q3_idx = (3 * len(sorted_values)) // 4
        
        q1 = sorted_values[q1_idx]
        q3 = sorted_values[q3_idx]
        iqr = q3 - q1
        
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)
        
        outliers = []
        for i, val in enumerate(values):
            if val < lower_bound or val > upper_bound:
                outliers.append(i)
        
        return outliers
    
    def get_dampened_value(self, values: List[float], 
                           target_idx: int) -> float:
        """
        Get a dampened value for an outlier point.
        
        Uses winsorization to cap extreme values.
        
        Args:
            values: List of all values
            target_idx: Index of the value to potentially dampen
            
        Returns:
            Original or dampened value
        """
        if len(values) < 3:
            return values[target_idx]
        
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        
        value = values[target_idx]
        
        upper_limit = mean + (self.outlier_sigma * stdev)
        lower_limit = mean - (self.outlier_sigma * stdev)
        
        # Winsorize
        if value > upper_limit:
            return upper_limit
        elif value < lower_limit:
            return max(lower_limit, 0)  # Don't go negative for points
        
        return value
    
    def calculate_robust_average(self, values: List[float]) -> float:
        """
        Calculate a robust average that's resistant to outliers.
        
        Uses trimmed mean (removes top and bottom 10%).
        
        Args:
            values: List of values
            
        Returns:
            Robust average
        """
        if not values:
            return 0.0
        
        if len(values) <= 4:
            return statistics.mean(values)
        
        # Trimmed mean - remove top and bottom 10%
        sorted_vals = sorted(values)
        trim_count = max(1, len(sorted_vals) // 10)
        trimmed = sorted_vals[trim_count:-trim_count]
        
        return statistics.mean(trimmed) if trimmed else statistics.mean(values)
    
    def get_sample_weight(self, sample_size: int, 
                          min_reliable: int = None) -> float:
        """
        Calculate a weight for a statistic based on sample size.
        
        Smaller samples get less weight in final calculations.
        
        Args:
            sample_size: Number of games in the sample
            min_reliable: Minimum games for full weight
            
        Returns:
            Weight between 0 and 1
        """
        min_reliable = min_reliable or STATS_CONFIG.MIN_BATCH_GAMES
        
        if sample_size <= 0:
            return 0.0
        
        if sample_size >= min_reliable * 3:
            return 1.0
        
        # Gradual increase from 0.3 (1 game) to 1.0 (min_reliable*3 games)
        return 0.3 + (0.7 * min(sample_size, min_reliable * 3) / (min_reliable * 3))
    
    def detect_rotation_risk(self, player: Player) -> float:
        """
        Detect if a player is at risk of rotation.
        
        Args:
            player: Player object with gameweek history
            
        Returns:
            Rotation risk score (0 = always plays, 1 = heavy rotation)
        """
        if not player.gameweeks:
            return 0.5  # Unknown
        
        # Look at recent games
        recent = player.gameweeks[-10:] if len(player.gameweeks) >= 10 else player.gameweeks
        
        minutes_list = [gw.minutes for gw in recent]
        
        if not minutes_list:
            return 0.5
        
        # Calculate variance in minutes
        avg_minutes = statistics.mean(minutes_list)
        
        if avg_minutes < 30:
            return 0.9  # Barely plays
        
        if len(minutes_list) > 1:
            stdev = statistics.stdev(minutes_list)
            cv = stdev / avg_minutes if avg_minutes > 0 else 0
            
            # High coefficient of variation = high rotation
            return min(cv, 1.0)
        
        return 0.3  # Default low risk
    
    def get_data_quality_score(self, player: Player, 
                                batch: Optional[Tuple[int, int]] = None) -> Tuple[float, str]:
        """
        Assess the quality/reliability of data for predictions.
        
        Args:
            player: Player object
            batch: Optional specific batch to assess
            
        Returns:
            Tuple of (quality_score 0-1, quality_label)
        """
        games = player.gameweeks
        
        if batch:
            games = player.get_games_vs_batch(batch, self.min_minutes)
        else:
            games = [g for g in games if g.minutes >= self.min_minutes]
        
        num_games = len(games)
        
        # Scoring criteria
        score = 0.0
        
        # Games played (up to 0.5)
        if num_games >= 15:
            score += 0.5
        elif num_games >= 10:
            score += 0.4
        elif num_games >= 5:
            score += 0.3
        elif num_games >= 2:
            score += 0.15
        
        # Consistency (up to 0.3)
        if num_games >= 3:
            minutes = [g.minutes for g in games]
            avg_min = statistics.mean(minutes)
            if avg_min >= 70:
                score += 0.3
            elif avg_min >= 50:
                score += 0.2
            elif avg_min >= 30:
                score += 0.1
        
        # Recent activity (up to 0.2)
        if games:
            recent_gws = [g.gameweek for g in games]
            max_gw = max(recent_gws)
            if max_gw >= 18:  # Played recently
                score += 0.2
            elif max_gw >= 15:
                score += 0.1
        
        # Determine label
        if score >= 0.7:
            label = "high"
        elif score >= 0.4:
            label = "medium"
        else:
            label = "low"
        
        return (round(score, 2), label)


def filter_valid_games(games: List[PlayerGameweek], 
                       min_minutes: int = 10) -> List[PlayerGameweek]:
    """
    Simple utility to filter games by minimum minutes.
    
    Args:
        games: List of gameweeks
        min_minutes: Minimum minutes threshold
        
    Returns:
        Filtered list of games
    """
    return [g for g in games if g.minutes >= min_minutes]


def calculate_per_90(total: float, minutes: int) -> float:
    """
    Calculate a per-90-minutes statistic.
    
    Args:
        total: Total stat value
        minutes: Total minutes played
        
    Returns:
        Stat normalized to 90 minutes
    """
    if minutes <= 0:
        return 0.0
    return (total / minutes) * 90

