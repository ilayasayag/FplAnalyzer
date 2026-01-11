"""
Form Analyzer

Implements EWMA (Exponentially Weighted Moving Average) and EWMV 
(Exponentially Weighted Moving Variance) for player form analysis.

Features:
- Adaptive window sizing based on player consistency
- Recent form vs baseline comparison
- Form trend detection (hot/cold streaks)
"""

from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
import math

from ..models.player import Player, PlayerGameweek


@dataclass
class FormAnalysis:
    """Results of form analysis for a player"""
    
    # Current form metrics
    ewma_score: float = 0.0  # Exponentially weighted mean
    ewmv_score: float = 0.0  # Exponentially weighted variance
    
    # Baseline comparison
    season_average: float = 0.0
    form_vs_baseline: float = 0.0  # Positive = hot, negative = cold
    
    # Trend indicators
    trend_direction: str = "stable"  # "hot", "cold", "stable"
    trend_strength: float = 0.0  # 0-1 scale
    streak_length: int = 0  # Consecutive games above/below average
    
    # Volatility metrics
    consistency_score: float = 0.0  # 0-1, higher = more consistent
    volatility_ratio: float = 0.0  # CV = std_dev / mean
    
    # Window metrics
    effective_window_size: int = 5
    games_analyzed: int = 0
    
    # Recent game breakdown
    recent_scores: List[int] = field(default_factory=list)
    recent_weights: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            'ewma': round(self.ewma_score, 2),
            'ewmv': round(self.ewmv_score, 2),
            'season_avg': round(self.season_average, 2),
            'form_delta': round(self.form_vs_baseline, 2),
            'trend': self.trend_direction,
            'trend_strength': round(self.trend_strength, 2),
            'streak': self.streak_length,
            'consistency': round(self.consistency_score, 2),
            'volatility': round(self.volatility_ratio, 2),
            'window_size': self.effective_window_size,
            'games': self.games_analyzed,
            'recent_scores': self.recent_scores[:5],
        }


class FormAnalyzer:
    """
    Analyzes player form using exponentially weighted statistics.
    
    Key concepts:
    - EWMA captures recent performance trend
    - EWMV captures recent consistency/volatility
    - Adaptive window expands for consistent players, shrinks for volatile ones
    """
    
    # Default decay weights for games (most recent first)
    # These sum to ~1.0 over first 8 games
    DEFAULT_WEIGHTS = [0.30, 0.22, 0.16, 0.12, 0.08, 0.05, 0.04, 0.03]
    
    def __init__(self,
                 alpha: float = 0.3,
                 min_games: int = 3,
                 max_window: int = 15):
        """
        Args:
            alpha: EWMA smoothing factor (higher = more weight to recent)
            min_games: Minimum games needed for form analysis
            max_window: Maximum games to consider in window
        """
        self.alpha = alpha
        self.min_games = min_games
        self.max_window = max_window
    
    def analyze_form(self,
                     player: Player,
                     min_minutes: int = 10) -> FormAnalysis:
        """
        Perform complete form analysis for a player.
        
        Args:
            player: Player with gameweek history
            min_minutes: Minimum minutes to count as valid game
            
        Returns:
            FormAnalysis with all metrics
        """
        analysis = FormAnalysis()
        
        # Filter valid games and sort by recency (most recent last)
        valid_games = [
            gw for gw in player.gameweeks 
            if gw.minutes >= min_minutes
        ]
        valid_games.sort(key=lambda g: g.gameweek)
        
        if len(valid_games) < self.min_games:
            return self._fallback_analysis(player, valid_games)
        
        analysis.games_analyzed = len(valid_games)
        
        # Extract scores (most recent last)
        scores = [float(gw.total_points) for gw in valid_games]
        
        # Calculate season average
        analysis.season_average = sum(scores) / len(scores)
        
        # Calculate adaptive window size
        analysis.effective_window_size = self._calculate_adaptive_window(scores)
        
        # Calculate EWMA and EWMV with adaptive window
        recent_scores = scores[-analysis.effective_window_size:]
        analysis.recent_scores = [int(s) for s in recent_scores[-5:]]
        
        analysis.ewma_score, analysis.ewmv_score = self._calculate_ewma_ewmv(
            recent_scores
        )
        
        # Calculate form weights for recent games
        analysis.recent_weights = self._get_game_weights(len(recent_scores))
        
        # Compare form to baseline
        analysis.form_vs_baseline = analysis.ewma_score - analysis.season_average
        
        # Detect trend
        analysis.trend_direction, analysis.trend_strength = self._detect_trend(
            scores, analysis.season_average
        )
        
        # Calculate streak length
        analysis.streak_length = self._calculate_streak(
            scores, analysis.season_average
        )
        
        # Calculate consistency metrics
        analysis.consistency_score = self._calculate_consistency(scores)
        if analysis.ewma_score > 0:
            analysis.volatility_ratio = math.sqrt(analysis.ewmv_score) / analysis.ewma_score
        
        return analysis
    
    def _fallback_analysis(self,
                           player: Player,
                           valid_games: List[PlayerGameweek]) -> FormAnalysis:
        """Create fallback analysis when insufficient data"""
        analysis = FormAnalysis()
        analysis.games_analyzed = len(valid_games)
        
        if valid_games:
            scores = [gw.total_points for gw in valid_games]
            analysis.season_average = sum(scores) / len(scores)
            analysis.ewma_score = analysis.season_average
            analysis.recent_scores = scores[-5:]
        else:
            # Use player's official form stat
            analysis.ewma_score = player.form
            analysis.season_average = player.points_per_game
        
        analysis.trend_direction = "stable"
        analysis.consistency_score = 0.5  # Unknown
        
        return analysis
    
    def _calculate_adaptive_window(self, scores: List[float]) -> int:
        """
        Calculate adaptive window size based on player consistency.
        
        Consistent players benefit from larger windows (more data).
        Volatile players need smaller windows (recent data more relevant).
        """
        if len(scores) < 5:
            return len(scores)
        
        # Calculate coefficient of variation of last 10 games
        recent = scores[-10:] if len(scores) >= 10 else scores
        mean = sum(recent) / len(recent)
        
        if mean <= 0:
            return 5  # Default
        
        variance = sum((s - mean) ** 2 for s in recent) / len(recent)
        cv = math.sqrt(variance) / mean
        
        # High CV (volatile) -> smaller window
        # Low CV (consistent) -> larger window
        if cv > 1.0:  # Very volatile
            return 4
        elif cv > 0.7:  # Moderately volatile
            return 5
        elif cv > 0.5:  # Average consistency
            return 7
        elif cv > 0.3:  # Fairly consistent
            return 10
        else:  # Very consistent
            return min(self.max_window, len(scores))
    
    def _calculate_ewma_ewmv(self, scores: List[float]) -> Tuple[float, float]:
        """
        Calculate EWMA and EWMV for a series of scores.
        
        Uses the standard EWMA formula with configurable alpha.
        EWMV captures the variance in recent scores.
        """
        if not scores:
            return 0.0, 0.0
        
        # Initialize with first score
        ewma = scores[0]
        ewmv = 0.0
        
        # Process remaining scores (chronological order)
        for score in scores[1:]:
            # Update EWMA
            diff = score - ewma
            ewma = ewma + self.alpha * diff
            
            # Update EWMV (variance)
            ewmv = (1 - self.alpha) * (ewmv + self.alpha * diff * diff)
        
        return ewma, ewmv
    
    def _get_game_weights(self, n_games: int) -> List[float]:
        """Get weights for recent games (most recent first in output)"""
        if n_games <= len(self.DEFAULT_WEIGHTS):
            weights = self.DEFAULT_WEIGHTS[:n_games]
        else:
            # Extend with exponential decay
            weights = list(self.DEFAULT_WEIGHTS)
            for i in range(len(self.DEFAULT_WEIGHTS), n_games):
                weights.append(0.02 * (0.8 ** (i - len(self.DEFAULT_WEIGHTS))))
        
        # Normalize
        total = sum(weights)
        return [w / total for w in weights]
    
    def _detect_trend(self,
                      scores: List[float],
                      baseline: float) -> Tuple[str, float]:
        """
        Detect if player is trending hot, cold, or stable.
        
        Compares recent 3 games vs previous 5 games.
        """
        if len(scores) < 5:
            return "stable", 0.0
        
        recent_3 = scores[-3:]
        previous_5 = scores[-8:-3] if len(scores) >= 8 else scores[:-3]
        
        if not previous_5:
            return "stable", 0.0
        
        recent_avg = sum(recent_3) / len(recent_3)
        previous_avg = sum(previous_5) / len(previous_5)
        
        # Calculate percentage change
        if previous_avg > 0:
            pct_change = (recent_avg - previous_avg) / previous_avg
        else:
            pct_change = 0.0
        
        # Determine trend
        if pct_change > 0.25:
            return "hot", min(1.0, pct_change)
        elif pct_change < -0.25:
            return "cold", min(1.0, abs(pct_change))
        else:
            return "stable", 0.0
    
    def _calculate_streak(self, scores: List[float], baseline: float) -> int:
        """
        Calculate consecutive games above/below baseline.
        
        Positive = games above average, Negative = games below.
        """
        if not scores:
            return 0
        
        # Count from most recent
        streak = 0
        direction = None
        
        for score in reversed(scores):
            if direction is None:
                direction = score >= baseline
                streak = 1 if score >= baseline else -1
            elif (score >= baseline) == direction:
                streak += 1 if direction else -1
            else:
                break
        
        return streak
    
    def _calculate_consistency(self, scores: List[float]) -> float:
        """
        Calculate consistency score (0-1).
        
        Based on how often player scores within 1 std dev of mean.
        """
        if len(scores) < 3:
            return 0.5  # Unknown
        
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 1.0  # Perfect consistency
        
        # Count scores within 1 std dev
        within_range = sum(
            1 for s in scores 
            if abs(s - mean) <= std_dev
        )
        
        return within_range / len(scores)
    
    def calculate_form_adjusted_prediction(self,
                                           base_prediction: float,
                                           form_analysis: FormAnalysis,
                                           form_weight: float = 0.3) -> float:
        """
        Adjust a base prediction based on form analysis.
        
        Args:
            base_prediction: Original prediction
            form_analysis: Form analysis results
            form_weight: How much to weight form vs base (0-1)
            
        Returns:
            Adjusted prediction
        """
        if form_analysis.games_analyzed < self.min_games:
            return base_prediction
        
        # Calculate form multiplier
        if form_analysis.season_average > 0:
            form_ratio = form_analysis.ewma_score / form_analysis.season_average
        else:
            form_ratio = 1.0
        
        # Dampen extreme form ratios
        form_ratio = max(0.7, min(1.4, form_ratio))
        
        # Apply trend boost/penalty
        if form_analysis.trend_direction == "hot":
            form_ratio *= 1 + (form_analysis.trend_strength * 0.1)
        elif form_analysis.trend_direction == "cold":
            form_ratio *= 1 - (form_analysis.trend_strength * 0.1)
        
        # Blend with base prediction
        adjusted = base_prediction * (
            (1 - form_weight) + form_weight * form_ratio
        )
        
        return adjusted


class FormComparator:
    """
    Compares form between multiple players for ranking.
    """
    
    def __init__(self, analyzer: Optional[FormAnalyzer] = None):
        self.analyzer = analyzer or FormAnalyzer()
    
    def rank_by_form(self,
                     players: List[Player],
                     ascending: bool = False) -> List[Tuple[Player, FormAnalysis]]:
        """
        Rank players by current form.
        
        Args:
            players: List of players to compare
            ascending: If True, worst form first
            
        Returns:
            List of (player, form_analysis) tuples sorted by form
        """
        results = []
        
        for player in players:
            analysis = self.analyzer.analyze_form(player)
            results.append((player, analysis))
        
        # Sort by EWMA (recent form)
        results.sort(
            key=lambda x: x[1].ewma_score,
            reverse=not ascending
        )
        
        return results
    
    def get_hot_players(self,
                        players: List[Player],
                        min_trend_strength: float = 0.2) -> List[Tuple[Player, FormAnalysis]]:
        """Get players with hot form trend"""
        results = []
        
        for player in players:
            analysis = self.analyzer.analyze_form(player)
            if (analysis.trend_direction == "hot" and 
                analysis.trend_strength >= min_trend_strength):
                results.append((player, analysis))
        
        results.sort(key=lambda x: x[1].trend_strength, reverse=True)
        return results
    
    def get_cold_players(self,
                         players: List[Player],
                         min_trend_strength: float = 0.2) -> List[Tuple[Player, FormAnalysis]]:
        """Get players with cold form trend"""
        results = []
        
        for player in players:
            analysis = self.analyzer.analyze_form(player)
            if (analysis.trend_direction == "cold" and 
                analysis.trend_strength >= min_trend_strength):
                results.append((player, analysis))
        
        results.sort(key=lambda x: x[1].trend_strength, reverse=True)
        return results
