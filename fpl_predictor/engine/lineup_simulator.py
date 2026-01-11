"""
Monte Carlo Lineup Simulator

Simulates thousands of gameweeks to find optimal lineups using
player score distributions and weighted sampling.
"""

from typing import List, Dict, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict
import random
import math

from ..models.player import Player, PlayerGameweek
from ..config import Position
from .score_distribution import ScoreDistribution, PlayerDistributionBuilder
from .form_analyzer import FormAnalyzer, FormAnalysis


@dataclass
class SimulatedScore:
    """A single simulated score for a player"""
    player_id: int
    player_name: str
    position: int
    team_id: int
    score: int
    
    
@dataclass
class SimulationResult:
    """Results from a single simulation run"""
    selected_lineup: List[SimulatedScore]
    bench: List[SimulatedScore]
    total_points: int
    captain_id: int
    captain_points: int


@dataclass
class LineupRecommendation:
    """Final lineup recommendation from Monte Carlo simulation"""
    
    # Player recommendations with selection frequency
    players: List[Dict[str, Any]] = field(default_factory=list)
    
    # Recommended starting XI
    starting_xi: List[int] = field(default_factory=list)  # Player IDs
    
    # Recommended captain and vice-captain
    captain_id: int = 0
    vice_captain_id: int = 0
    
    # Aggregate statistics
    expected_points: float = 0.0
    points_std_dev: float = 0.0
    points_ci_80: Tuple[float, float] = (0.0, 0.0)
    
    # Simulation metadata
    simulations_run: int = 0
    squad_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            'players': self.players,
            'starting_xi': self.starting_xi,
            'captain': self.captain_id,
            'vice_captain': self.vice_captain_id,
            'expected_points': round(self.expected_points, 1),
            'std_dev': round(self.points_std_dev, 1),
            'ci_80': [round(x, 1) for x in self.points_ci_80],
            'simulations': self.simulations_run,
            'squad_size': self.squad_size,
        }


@dataclass
class FreeAgentRecommendation:
    """Recommendation for a free agent pickup"""
    
    player_id: int
    player_name: str
    team_name: str
    position: str
    
    # Prediction metrics
    expected_points: float = 0.0
    upside_90: float = 0.0  # 90th percentile score
    floor_10: float = 0.0  # 10th percentile score
    
    # Form metrics
    form_trend: str = "stable"
    ewma_score: float = 0.0
    
    # Distribution info
    ci_80: Tuple[float, float] = (0.0, 0.0)
    
    # Ranking info
    position_rank: int = 0
    overall_rank: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'player_id': self.player_id,
            'name': self.player_name,
            'team': self.team_name,
            'position': self.position,
            'expected': round(self.expected_points, 2),
            'upside': round(self.upside_90, 1),
            'floor': round(self.floor_10, 1),
            'form_trend': self.form_trend,
            'form_ewma': round(self.ewma_score, 2),
            'ci_80': [round(x, 1) for x in self.ci_80],
            'pos_rank': self.position_rank,
            'overall_rank': self.overall_rank,
        }


class MonteCarloSimulator:
    """
    Simulates gameweeks to find optimal lineups.
    
    Uses player score distributions to sample possible outcomes
    and identifies which players appear most often in optimal lineups.
    """
    
    # Formation constraints: (min_def, max_def, min_mid, max_mid, min_fwd, max_fwd)
    VALID_FORMATIONS = [
        (3, 3, 4, 4, 3, 3),  # 3-4-3
        (3, 3, 5, 5, 2, 2),  # 3-5-2
        (4, 4, 3, 3, 3, 3),  # 4-3-3
        (4, 4, 4, 4, 2, 2),  # 4-4-2
        (4, 4, 5, 5, 1, 1),  # 4-5-1
        (5, 5, 3, 3, 2, 2),  # 5-3-2
        (5, 5, 4, 4, 1, 1),  # 5-4-1
    ]
    
    def __init__(self,
                 distribution_builder: Optional[PlayerDistributionBuilder] = None,
                 form_analyzer: Optional[FormAnalyzer] = None):
        self.dist_builder = distribution_builder or PlayerDistributionBuilder()
        self.form_analyzer = form_analyzer or FormAnalyzer()
        
        # Cache distributions to avoid recomputation
        self._dist_cache: Dict[int, ScoreDistribution] = {}
        self._form_cache: Dict[int, FormAnalysis] = {}
    
    def simulate_lineup(self,
                        squad: List[Player],
                        opponent_batches: Dict[int, Tuple[int, int]],
                        is_home: Dict[int, bool],
                        n_simulations: int = 1000,
                        formation_constraint: Optional[str] = None) -> LineupRecommendation:
        """
        Run Monte Carlo simulation to find optimal lineup.
        
        Args:
            squad: List of players in the squad
            opponent_batches: Map of player_id -> opponent's batch
            is_home: Map of player_id -> is playing at home
            n_simulations: Number of simulations to run
            formation_constraint: Optional specific formation (e.g., "4-4-2")
            
        Returns:
            LineupRecommendation with optimal lineup
        """
        if not squad:
            return LineupRecommendation()
        
        # Build distributions for all players
        player_dists: Dict[int, ScoreDistribution] = {}
        player_forms: Dict[int, FormAnalysis] = {}
        
        for player in squad:
            opp_batch = opponent_batches.get(player.id)
            home = is_home.get(player.id)
            
            # Use cache if available
            cache_key = (player.id, opp_batch, home)
            if player.id in self._dist_cache:
                player_dists[player.id] = self._dist_cache[player.id]
            else:
                dist = self.dist_builder.build_for_player(player, opp_batch, home)
                player_dists[player.id] = dist
                self._dist_cache[player.id] = dist
            
            if player.id in self._form_cache:
                player_forms[player.id] = self._form_cache[player.id]
            else:
                form = self.form_analyzer.analyze_form(player)
                player_forms[player.id] = form
                self._form_cache[player.id] = form
        
        # Run simulations
        selection_counts: Dict[int, int] = defaultdict(int)
        captain_counts: Dict[int, int] = defaultdict(int)
        total_points_list: List[int] = []
        
        for _ in range(n_simulations):
            result = self._run_single_simulation(
                squad, player_dists, formation_constraint
            )
            
            # Track selections
            for player_score in result.selected_lineup:
                selection_counts[player_score.player_id] += 1
            
            captain_counts[result.captain_id] += 1
            total_points_list.append(result.total_points)
        
        # Build recommendation
        recommendation = LineupRecommendation()
        recommendation.simulations_run = n_simulations
        recommendation.squad_size = len(squad)
        
        # Calculate player selection rates
        player_info = []
        for player in squad:
            dist = player_dists[player.id]
            form = player_forms[player.id]
            
            selection_rate = selection_counts[player.id] / n_simulations
            captain_rate = captain_counts[player.id] / n_simulations
            
            player_info.append({
                'player_id': player.id,
                'name': player.web_name,
                'position': player.position_name,
                'team': player.team_name,
                'selection_rate': round(selection_rate, 3),
                'captain_rate': round(captain_rate, 3),
                'expected': round(dist.expected_value, 2),
                'ci_80': [round(x, 1) for x in dist.ci_80],
                'form_trend': form.trend_direction,
                'form_ewma': round(form.ewma_score, 2),
            })
        
        # Sort by selection rate
        player_info.sort(key=lambda x: x['selection_rate'], reverse=True)
        recommendation.players = player_info
        
        # Get starting XI (top 11 by selection rate, respecting positions)
        recommendation.starting_xi = self._select_starting_xi(
            player_info, squad, formation_constraint
        )
        
        # Get captain (highest captain rate)
        if captain_counts:
            recommendation.captain_id = max(captain_counts, key=captain_counts.get)
            # Vice captain is second highest
            sorted_captains = sorted(
                captain_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            if len(sorted_captains) > 1:
                recommendation.vice_captain_id = sorted_captains[1][0]
        
        # Calculate aggregate stats
        if total_points_list:
            recommendation.expected_points = sum(total_points_list) / len(total_points_list)
            variance = sum(
                (p - recommendation.expected_points) ** 2 
                for p in total_points_list
            ) / len(total_points_list)
            recommendation.points_std_dev = math.sqrt(variance)
            
            # 80% CI from simulation results
            sorted_points = sorted(total_points_list)
            lower_idx = int(0.1 * len(sorted_points))
            upper_idx = int(0.9 * len(sorted_points))
            recommendation.points_ci_80 = (
                float(sorted_points[lower_idx]),
                float(sorted_points[upper_idx])
            )
        
        return recommendation
    
    def _run_single_simulation(self,
                               squad: List[Player],
                               distributions: Dict[int, ScoreDistribution],
                               formation_constraint: Optional[str]) -> SimulationResult:
        """Run a single simulation iteration"""
        
        # Sample scores for all players
        sampled_scores: List[SimulatedScore] = []
        
        for player in squad:
            dist = distributions.get(player.id)
            if dist:
                score = self._sample_from_distribution(dist)
            else:
                score = 2  # Fallback
            
            sampled_scores.append(SimulatedScore(
                player_id=player.id,
                player_name=player.web_name,
                position=player.position,
                team_id=player.team_id,
                score=score
            ))
        
        # Select best valid lineup
        lineup, bench = self._select_best_lineup(sampled_scores, formation_constraint)
        
        # Select captain (highest scorer)
        captain = max(lineup, key=lambda x: x.score)
        
        # Calculate total (captain gets double)
        total = sum(p.score for p in lineup) + captain.score
        
        return SimulationResult(
            selected_lineup=lineup,
            bench=bench,
            total_points=total,
            captain_id=captain.player_id,
            captain_points=captain.score * 2
        )
    
    def _sample_from_distribution(self, dist: ScoreDistribution) -> int:
        """Sample a score from the distribution"""
        if not dist.probabilities:
            return int(dist.expected_value)
        
        # Weighted random selection
        rand = random.random()
        cumulative = 0.0
        
        for score in sorted(dist.probabilities.keys()):
            cumulative += dist.probabilities[score]
            if rand <= cumulative:
                return score
        
        return int(dist.expected_value)
    
    def _select_best_lineup(self,
                            scores: List[SimulatedScore],
                            formation_constraint: Optional[str]) -> Tuple[List[SimulatedScore], List[SimulatedScore]]:
        """Select the best valid 11 from sampled scores"""
        
        # Group by position
        by_position: Dict[int, List[SimulatedScore]] = defaultdict(list)
        for score in scores:
            by_position[score.position].append(score)
        
        # Sort each position by score
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x.score, reverse=True)
        
        # Find best valid formation
        best_lineup: List[SimulatedScore] = []
        best_total = -1
        
        formations = self.VALID_FORMATIONS
        if formation_constraint:
            formations = [self._parse_formation(formation_constraint)]
        
        for min_def, max_def, min_mid, max_mid, min_fwd, max_fwd in formations:
            lineup = self._build_lineup_for_formation(
                by_position, min_def, max_def, min_mid, max_mid, min_fwd, max_fwd
            )
            
            if lineup:
                total = sum(p.score for p in lineup)
                if total > best_total:
                    best_total = total
                    best_lineup = lineup
        
        # Bench is everyone not selected
        selected_ids = {p.player_id for p in best_lineup}
        bench = [s for s in scores if s.player_id not in selected_ids]
        bench.sort(key=lambda x: x.score, reverse=True)
        
        return best_lineup, bench
    
    def _build_lineup_for_formation(self,
                                    by_position: Dict[int, List[SimulatedScore]],
                                    min_def: int, max_def: int,
                                    min_mid: int, max_mid: int,
                                    min_fwd: int, max_fwd: int) -> List[SimulatedScore]:
        """Build lineup for a specific formation"""
        
        gks = by_position.get(Position.GK, [])
        defs = by_position.get(Position.DEF, [])
        mids = by_position.get(Position.MID, [])
        fwds = by_position.get(Position.FWD, [])
        
        # Check if formation is possible
        if len(gks) < 1:
            return []
        if len(defs) < min_def:
            return []
        if len(mids) < min_mid:
            return []
        if len(fwds) < min_fwd:
            return []
        
        lineup = []
        
        # 1 GK
        lineup.append(gks[0])
        
        # Required defenders, mids, forwards
        lineup.extend(defs[:min_def])
        lineup.extend(mids[:min_mid])
        lineup.extend(fwds[:min_fwd])
        
        # Fill remaining slots with best available
        remaining_slots = 11 - len(lineup)
        
        # Pool of additional players (excluding already selected)
        selected = {p.player_id for p in lineup}
        pool = []
        pool.extend(defs[min_def:max_def])
        pool.extend(mids[min_mid:max_mid])
        pool.extend(fwds[min_fwd:max_fwd])
        pool = [p for p in pool if p.player_id not in selected]
        pool.sort(key=lambda x: x.score, reverse=True)
        
        lineup.extend(pool[:remaining_slots])
        
        return lineup if len(lineup) == 11 else []
    
    def _parse_formation(self, formation: str) -> Tuple[int, int, int, int, int, int]:
        """Parse formation string like '4-4-2' into constraints"""
        parts = formation.split('-')
        if len(parts) == 3:
            d, m, f = int(parts[0]), int(parts[1]), int(parts[2])
            return (d, d, m, m, f, f)
        return self.VALID_FORMATIONS[0]  # Default
    
    def _select_starting_xi(self,
                            player_info: List[Dict[str, Any]],
                            squad: List[Player],
                            formation_constraint: Optional[str]) -> List[int]:
        """Select starting XI based on selection rates"""
        
        # Create player lookup
        player_map = {p.id: p for p in squad}
        
        # Sort by selection rate
        sorted_players = sorted(
            player_info, 
            key=lambda x: x['selection_rate'], 
            reverse=True
        )
        
        # Group by position
        by_pos: Dict[str, List[Dict]] = defaultdict(list)
        for p in sorted_players:
            by_pos[p['position']].append(p)
        
        # Build XI with formation constraints
        xi = []
        
        # 1 GK
        if by_pos['GK']:
            xi.append(by_pos['GK'][0]['player_id'])
        
        # 3-5 DEF
        for p in by_pos['DEF'][:5]:
            if len(xi) < 11:
                xi.append(p['player_id'])
        
        # 2-5 MID
        for p in by_pos['MID'][:5]:
            if len(xi) < 11:
                xi.append(p['player_id'])
        
        # 1-3 FWD
        for p in by_pos['FWD'][:3]:
            if len(xi) < 11:
                xi.append(p['player_id'])
        
        return xi[:11]
    
    def clear_cache(self):
        """Clear distribution cache"""
        self._dist_cache.clear()
        self._form_cache.clear()


class FreeAgentAnalyzer:
    """
    Analyzes free agents (unowned players) to find best pickups.
    """
    
    def __init__(self,
                 distribution_builder: Optional[PlayerDistributionBuilder] = None,
                 form_analyzer: Optional[FormAnalyzer] = None):
        self.dist_builder = distribution_builder or PlayerDistributionBuilder()
        self.form_analyzer = form_analyzer or FormAnalyzer()
    
    def analyze_free_agents(self,
                            all_players: List[Player],
                            owned_player_ids: Set[int],
                            opponent_batches: Dict[int, Tuple[int, int]],
                            is_home: Dict[int, bool],
                            position_filter: Optional[str] = None,
                            top_n: int = 20) -> List[FreeAgentRecommendation]:
        """
        Analyze free agents and return ranked recommendations.
        
        Args:
            all_players: All available players
            owned_player_ids: Set of player IDs already owned in league
            opponent_batches: Map of player_id -> opponent batch
            is_home: Map of player_id -> is playing at home
            position_filter: Optional filter by position (GK/DEF/MID/FWD)
            top_n: Number of recommendations to return
            
        Returns:
            List of FreeAgentRecommendation sorted by expected points
        """
        recommendations = []
        
        # Filter to free agents
        free_agents = [p for p in all_players if p.id not in owned_player_ids]
        
        # Filter by position if specified
        if position_filter:
            pos_map = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
            target_pos = pos_map.get(position_filter.upper())
            if target_pos:
                free_agents = [p for p in free_agents if p.position == target_pos]
        
        # Analyze each free agent
        for player in free_agents:
            opp_batch = opponent_batches.get(player.id)
            home = is_home.get(player.id)
            
            # Build distribution
            dist = self.dist_builder.build_for_player(player, opp_batch, home)
            
            # Analyze form
            form = self.form_analyzer.analyze_form(player)
            
            rec = FreeAgentRecommendation(
                player_id=player.id,
                player_name=player.web_name,
                team_name=player.team_name,
                position=player.position_name,
                expected_points=dist.expected_value,
                upside_90=dist.get_upside(0.9),
                floor_10=dist.get_downside(0.1),
                form_trend=form.trend_direction,
                ewma_score=form.ewma_score,
                ci_80=dist.ci_80,
            )
            
            recommendations.append(rec)
        
        # Sort by expected points
        recommendations.sort(key=lambda x: x.expected_points, reverse=True)
        
        # Add ranking info
        for i, rec in enumerate(recommendations):
            rec.overall_rank = i + 1
        
        # Add position ranks
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            pos_recs = [r for r in recommendations if r.position == pos]
            for i, rec in enumerate(pos_recs):
                rec.position_rank = i + 1
        
        return recommendations[:top_n]
    
    def get_best_by_position(self,
                             all_players: List[Player],
                             owned_player_ids: Set[int],
                             opponent_batches: Dict[int, Tuple[int, int]],
                             is_home: Dict[int, bool],
                             per_position: int = 5) -> Dict[str, List[FreeAgentRecommendation]]:
        """
        Get best free agents for each position.
        
        Returns:
            Dict mapping position -> list of recommendations
        """
        result = {}
        
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            result[pos] = self.analyze_free_agents(
                all_players,
                owned_player_ids,
                opponent_batches,
                is_home,
                position_filter=pos,
                top_n=per_position
            )
        
        return result
    
    def find_differentials(self,
                           all_players: List[Player],
                           owned_player_ids: Set[int],
                           opponent_batches: Dict[int, Tuple[int, int]],
                           is_home: Dict[int, bool],
                           top_n: int = 10) -> List[FreeAgentRecommendation]:
        """
        Find high-upside differentials (players with high 90th percentile).
        
        These are players who might not have the highest expected points
        but have potential for big hauls.
        """
        # Get all free agents
        recs = self.analyze_free_agents(
            all_players,
            owned_player_ids,
            opponent_batches,
            is_home,
            top_n=100  # Get more for filtering
        )
        
        # Sort by upside instead of expected
        recs.sort(key=lambda x: x.upside_90, reverse=True)
        
        return recs[:top_n]
