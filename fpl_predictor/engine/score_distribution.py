"""
Score Distribution Engine

Builds probability distributions for player scores using:
- Adaptive winsorization for outlier handling
- Median Absolute Deviation (MAD) for robust variance
- Kernel density estimation with variable bandwidth
"""

from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
import math
from collections import defaultdict

from ..models.player import Player, PlayerGameweek


@dataclass
class ScoreDistribution:
    """Represents a probability distribution over possible scores"""
    
    # Core statistics
    expected_value: float = 0.0
    median: float = 0.0
    mode: float = 0.0
    std_dev: float = 0.0
    mad: float = 0.0  # Median Absolute Deviation
    
    # Confidence intervals: (lower, upper)
    ci_50: Tuple[float, float] = (0.0, 0.0)
    ci_80: Tuple[float, float] = (0.0, 0.0)
    ci_95: Tuple[float, float] = (0.0, 0.0)
    
    # Discrete probability distribution: score -> probability
    probabilities: Dict[int, float] = field(default_factory=dict)
    
    # Metadata
    sample_size: int = 0
    outliers_detected: int = 0
    quality_score: float = 0.0
    
    def get_probability(self, score: int) -> float:
        """Get probability of a specific score"""
        return self.probabilities.get(score, 0.0)
    
    def get_range_probability(self, min_score: int, max_score: int) -> float:
        """Get probability of score falling in a range"""
        return sum(
            self.probabilities.get(s, 0.0) 
            for s in range(min_score, max_score + 1)
        )
    
    def get_upside(self, percentile: float = 0.9) -> float:
        """Get score at given percentile (e.g., 90th percentile upside)"""
        cumulative = 0.0
        for score in sorted(self.probabilities.keys()):
            cumulative += self.probabilities[score]
            if cumulative >= percentile:
                return float(score)
        return max(self.probabilities.keys()) if self.probabilities else 0.0
    
    def get_downside(self, percentile: float = 0.1) -> float:
        """Get score at given percentile (e.g., 10th percentile floor)"""
        return self.get_upside(percentile)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            'expected': round(self.expected_value, 2),
            'median': round(self.median, 1),
            'mode': round(self.mode, 1),
            'std_dev': round(self.std_dev, 2),
            'mad': round(self.mad, 2),
            'ci_50': [round(x, 1) for x in self.ci_50],
            'ci_80': [round(x, 1) for x in self.ci_80],
            'ci_95': [round(x, 1) for x in self.ci_95],
            'probabilities': {
                str(k): round(v, 4) 
                for k, v in sorted(self.probabilities.items())
                if v >= 0.001  # Only include meaningful probabilities
            },
            'sample_size': self.sample_size,
            'outliers_detected': self.outliers_detected,
            'quality': round(self.quality_score, 2)
        }


class OutlierAwareDistribution:
    """
    Builds score distributions with intelligent outlier handling.
    
    Uses adaptive winsorization - outliers aren't removed but their
    influence is dampened proportionally to how extreme they are.
    """
    
    def __init__(self,
                 outlier_threshold: float = 2.5,
                 kernel_bandwidth: float = 1.0,
                 min_samples: int = 3):
        """
        Args:
            outlier_threshold: MAD multipliers to consider outlier
            kernel_bandwidth: Base bandwidth for kernel smoothing
            min_samples: Minimum games needed for distribution
        """
        self.outlier_threshold = outlier_threshold
        self.kernel_bandwidth = kernel_bandwidth
        self.min_samples = min_samples
    
    def build_distribution(self,
                           scores: List[float],
                           weights: Optional[List[float]] = None,
                           context_shift: float = 0.0) -> ScoreDistribution:
        """
        Build a probability distribution from historical scores.
        
        Args:
            scores: List of historical point scores
            weights: Optional weights for each score (e.g., recency)
            context_shift: Shift to apply to distribution mean (fixture context)
            
        Returns:
            ScoreDistribution with all statistics
        """
        dist = ScoreDistribution()
        
        if not scores or len(scores) < self.min_samples:
            # Return uniform-ish fallback distribution
            return self._fallback_distribution(scores)
        
        dist.sample_size = len(scores)
        
        # Normalize weights
        if weights is None:
            weights = [1.0] * len(scores)
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]
        
        # Calculate robust statistics
        dist.median = self._weighted_median(scores, weights)
        dist.mad = self._calculate_mad(scores, dist.median)
        
        # Detect outliers using MAD
        outlier_mask = self._detect_outliers(scores, dist.median, dist.mad)
        dist.outliers_detected = sum(outlier_mask)
        
        # Apply adaptive winsorization
        adjusted_scores, adjusted_weights = self._adaptive_winsorize(
            scores, weights, outlier_mask, dist.median, dist.mad
        )
        
        # Build kernel density estimate
        dist.probabilities = self._build_kde(
            adjusted_scores, adjusted_weights, context_shift
        )
        
        # Calculate statistics from distribution
        dist.expected_value = self._calculate_expected_value(dist.probabilities)
        dist.std_dev = self._calculate_std_dev(dist.probabilities, dist.expected_value)
        dist.mode = self._calculate_mode(dist.probabilities)
        
        # Calculate confidence intervals
        dist.ci_50 = self._calculate_ci(dist.probabilities, 0.50)
        dist.ci_80 = self._calculate_ci(dist.probabilities, 0.80)
        dist.ci_95 = self._calculate_ci(dist.probabilities, 0.95)
        
        # Quality score based on sample size and consistency
        dist.quality_score = self._calculate_quality(dist)
        
        return dist
    
    def _fallback_distribution(self, scores: List[float]) -> ScoreDistribution:
        """Create a fallback distribution when insufficient data"""
        dist = ScoreDistribution()
        dist.sample_size = len(scores) if scores else 0
        
        if scores:
            avg = sum(scores) / len(scores)
            dist.expected_value = avg
            dist.median = avg
            dist.mode = round(avg)
        else:
            # Default fallback - assume 2-4 point player
            dist.expected_value = 3.0
            dist.median = 2.0
            dist.mode = 2.0
        
        # Wide uncertainty for low-data scenarios
        center = int(dist.expected_value)
        dist.probabilities = {
            max(0, center - 2): 0.10,
            max(0, center - 1): 0.20,
            center: 0.30,
            center + 1: 0.20,
            center + 2: 0.10,
            center + 3: 0.05,
            center + 4: 0.03,
            center + 5: 0.02,
        }
        
        dist.ci_50 = (max(0, center - 1), center + 1)
        dist.ci_80 = (max(0, center - 2), center + 3)
        dist.ci_95 = (max(0, center - 3), center + 5)
        dist.quality_score = 0.2
        
        return dist
    
    def _weighted_median(self, values: List[float], weights: List[float]) -> float:
        """Calculate weighted median"""
        sorted_pairs = sorted(zip(values, weights))
        cumulative = 0.0
        for val, weight in sorted_pairs:
            cumulative += weight
            if cumulative >= 0.5:
                return val
        return sorted_pairs[-1][0] if sorted_pairs else 0.0
    
    def _calculate_mad(self, values: List[float], median: float) -> float:
        """
        Calculate Median Absolute Deviation.
        
        MAD is more robust than standard deviation for outlier detection.
        """
        if not values:
            return 1.0
        
        deviations = [abs(v - median) for v in values]
        deviations.sort()
        n = len(deviations)
        
        if n % 2 == 0:
            mad = (deviations[n//2 - 1] + deviations[n//2]) / 2
        else:
            mad = deviations[n//2]
        
        # Scale factor to make MAD comparable to std dev for normal distributions
        return max(mad * 1.4826, 0.5)  # Min 0.5 to avoid division issues
    
    def _detect_outliers(self, 
                         values: List[float], 
                         median: float, 
                         mad: float) -> List[bool]:
        """Detect outliers using MAD-based criterion"""
        return [
            abs(v - median) > (self.outlier_threshold * mad)
            for v in values
        ]
    
    def _adaptive_winsorize(self,
                            scores: List[float],
                            weights: List[float],
                            outlier_mask: List[bool],
                            median: float,
                            mad: float) -> Tuple[List[float], List[float]]:
        """
        Apply adaptive winsorization.
        
        Instead of removing outliers, reduce their weight proportionally
        to how extreme they are. This preserves information about
        rare events while preventing them from dominating.
        """
        adjusted_scores = []
        adjusted_weights = []
        
        for score, weight, is_outlier in zip(scores, weights, outlier_mask):
            if is_outlier:
                # Calculate how extreme the outlier is
                distance = abs(score - median) / mad
                
                # Dampen weight exponentially with distance
                # At threshold: weight *= 0.5, at 2x threshold: weight *= 0.25
                dampen_factor = math.exp(-0.3 * (distance - self.outlier_threshold))
                dampen_factor = max(0.1, min(1.0, dampen_factor))
                
                adjusted_weights.append(weight * dampen_factor)
                
                # Also pull extreme scores toward the edge of "reasonable"
                # This creates a fat tail instead of a spike
                if score > median:
                    capped = median + self.outlier_threshold * mad
                    # Blend between capped and actual
                    adjusted_scores.append(capped * 0.7 + score * 0.3)
                else:
                    capped = median - self.outlier_threshold * mad
                    adjusted_scores.append(max(0, capped * 0.7 + score * 0.3))
            else:
                adjusted_scores.append(score)
                adjusted_weights.append(weight)
        
        # Renormalize weights
        total = sum(adjusted_weights)
        if total > 0:
            adjusted_weights = [w / total for w in adjusted_weights]
        
        return adjusted_scores, adjusted_weights
    
    def _build_kde(self,
                   scores: List[float],
                   weights: List[float],
                   context_shift: float) -> Dict[int, float]:
        """
        Build kernel density estimate over discrete score values.
        
        Uses Gaussian kernels with adaptive bandwidth.
        """
        # Score range to consider (0 to 20 covers almost all realistic scores)
        min_score = 0
        max_score = 20
        
        probabilities = defaultdict(float)
        
        for score, weight in zip(scores, weights):
            # Apply context shift
            shifted_score = score + context_shift
            
            # Adaptive bandwidth: wider for extreme scores
            bandwidth = self.kernel_bandwidth
            if shifted_score > 10:
                bandwidth *= 1.5  # Wider spread for high scores
            
            # Apply Gaussian kernel to nearby integer scores
            for target in range(min_score, max_score + 1):
                # Gaussian kernel
                distance = (target - shifted_score) / bandwidth
                kernel_value = math.exp(-0.5 * distance * distance)
                probabilities[target] += weight * kernel_value
        
        # Normalize to sum to 1
        total = sum(probabilities.values())
        if total > 0:
            probabilities = {k: v / total for k, v in probabilities.items()}
        
        # Remove near-zero probabilities
        probabilities = {
            k: v for k, v in probabilities.items() 
            if v >= 0.001
        }
        
        return dict(probabilities)
    
    def _calculate_expected_value(self, probs: Dict[int, float]) -> float:
        """Calculate expected value from distribution"""
        return sum(score * prob for score, prob in probs.items())
    
    def _calculate_std_dev(self, probs: Dict[int, float], mean: float) -> float:
        """Calculate standard deviation from distribution"""
        variance = sum(
            prob * (score - mean) ** 2 
            for score, prob in probs.items()
        )
        return math.sqrt(variance) if variance > 0 else 0.0
    
    def _calculate_mode(self, probs: Dict[int, float]) -> float:
        """Find the most likely score"""
        if not probs:
            return 0.0
        return max(probs.keys(), key=lambda k: probs[k])
    
    def _calculate_ci(self, 
                      probs: Dict[int, float], 
                      confidence: float) -> Tuple[float, float]:
        """
        Calculate confidence interval.
        
        Finds the narrowest range containing `confidence` probability mass.
        """
        if not probs:
            return (0.0, 0.0)
        
        sorted_scores = sorted(probs.keys())
        
        # Find percentiles
        lower_pct = (1 - confidence) / 2
        upper_pct = 1 - lower_pct
        
        cumulative = 0.0
        lower_bound = sorted_scores[0]
        upper_bound = sorted_scores[-1]
        
        for score in sorted_scores:
            cumulative += probs[score]
            if cumulative >= lower_pct and lower_bound == sorted_scores[0]:
                lower_bound = score
            if cumulative >= upper_pct:
                upper_bound = score
                break
        
        return (float(lower_bound), float(upper_bound))
    
    def _calculate_quality(self, dist: ScoreDistribution) -> float:
        """
        Calculate quality/reliability score for the distribution.
        
        Based on sample size, consistency, and outlier ratio.
        """
        # Sample size component (0-0.5)
        if dist.sample_size >= 15:
            size_score = 0.5
        elif dist.sample_size >= 10:
            size_score = 0.4
        elif dist.sample_size >= 5:
            size_score = 0.3
        else:
            size_score = dist.sample_size * 0.1
        
        # Consistency component (0-0.3) - lower std_dev relative to mean is better
        cv = dist.std_dev / dist.expected_value if dist.expected_value > 0 else 1.0
        consistency_score = max(0, 0.3 - cv * 0.15)
        
        # Outlier ratio component (0-0.2) - fewer outliers is better
        outlier_ratio = dist.outliers_detected / dist.sample_size if dist.sample_size > 0 else 0
        outlier_score = max(0, 0.2 - outlier_ratio * 0.5)
        
        return min(1.0, size_score + consistency_score + outlier_score)


class PlayerDistributionBuilder:
    """
    Builds score distributions for players with full context awareness.
    """
    
    def __init__(self):
        self.outlier_dist = OutlierAwareDistribution()
    
    def build_for_player(self,
                         player: Player,
                         opponent_batch: Optional[Tuple[int, int]] = None,
                         is_home: Optional[bool] = None,
                         form_weight: float = 0.4) -> ScoreDistribution:
        """
        Build distribution for a player considering fixture context.
        
        Args:
            player: Player with gameweek history
            opponent_batch: Opponent's batch for context matching
            is_home: Whether playing at home
            form_weight: Weight given to recent form vs overall
            
        Returns:
            ScoreDistribution for the player
        """
        games = [gw for gw in player.gameweeks if gw.minutes >= 10]
        
        if not games:
            return self.outlier_dist._fallback_distribution([])
        
        # Extract scores and calculate weights
        scores = []
        weights = []
        
        for i, gw in enumerate(games):
            scores.append(float(gw.total_points))
            
            # Base weight from recency (most recent = highest)
            recency = len(games) - i
            recency_weight = math.pow(0.9, recency - 1)  # Exponential decay
            
            # Context matching bonuses
            context_mult = 1.0
            
            # Home/away match
            if is_home is not None and gw.was_home == is_home:
                context_mult *= 1.3
            
            # Opponent batch match
            if opponent_batch and gw.opponent_batch == opponent_batch:
                context_mult *= 1.5
            
            # Full game bonus (60+ minutes)
            if gw.minutes >= 60:
                context_mult *= 1.2
            
            weights.append(recency_weight * context_mult)
        
        # Calculate context shift
        context_shift = self._calculate_context_shift(
            games, opponent_batch, is_home
        )
        
        return self.outlier_dist.build_distribution(
            scores, weights, context_shift
        )
    
    def _calculate_context_shift(self,
                                 games: List[PlayerGameweek],
                                 opponent_batch: Optional[Tuple[int, int]],
                                 is_home: Optional[bool]) -> float:
        """
        Calculate how much to shift distribution based on context.
        
        Compares player's average in matching contexts vs overall.
        """
        if not games:
            return 0.0
        
        overall_avg = sum(g.total_points for g in games) / len(games)
        
        # Find context-matching games
        matching = []
        for gw in games:
            matches = True
            if is_home is not None and gw.was_home != is_home:
                matches = False
            if opponent_batch and gw.opponent_batch != opponent_batch:
                matches = False
            if matches:
                matching.append(gw)
        
        if len(matching) < 2:
            # Not enough data for reliable shift
            # Apply small home/away adjustment as fallback
            if is_home is True:
                return 0.3  # Small home boost
            elif is_home is False:
                return -0.2  # Small away penalty
            return 0.0
        
        context_avg = sum(g.total_points for g in matching) / len(matching)
        
        # Shift is difference, dampened by confidence
        confidence = min(len(matching) / 5, 1.0)
        return (context_avg - overall_avg) * confidence
