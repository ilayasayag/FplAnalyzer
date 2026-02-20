"""
Squad Fixture Analysis Engine

Analyzes FPL squad fixture strength by position across gameweeks.
Calculates weighted scores (star players = 1.5x, regular = 1.0x) and
generates transfer recommendations to improve fixture coverage.
"""

from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json

from fpl_predictor.data.database import get_connection
from fpl_predictor.data.repository import SquadAnalysisRepository


class SquadFixtureAnalyzer:
    """Analyzes squad fixture strength per position across gameweeks."""
    
    # Position-specific scoring matrices: [position_id][is_star][difficulty_tier] -> score
    # difficulty_tier: 'easy' (FDR <= 2.5), 'medium' (2.5 < FDR <= 3.5), 'hard' (FDR > 3.5)
    POSITION_SCORING = {
        1: {  # GK
            False: {'easy': 1.5, 'medium': 1.0, 'hard': 0.0},  # Regular GK
            True:  {'easy': 1.5, 'medium': 1.0, 'hard': 0.0}   # Star GK (same as regular)
        },
        2: {  # DEF
            False: {'easy': 1.5, 'medium': 1.0, 'hard': 0.0},  # Regular DEF
            True:  {'easy': 2.0, 'medium': 1.5, 'hard': 0.5}   # Star DEF
        },
        3: {  # MID
            False: {'easy': 1.5, 'medium': 1.0, 'hard': 0.5},  # Regular MID
            True:  {'easy': 2.0, 'medium': 1.5, 'hard': 1.0}   # Star MID
        },
        4: {  # FWD
            False: {'easy': 2.0, 'medium': 1.5, 'hard': 1.0},  # Regular FWD (all FWDs score well)
            True:  {'easy': 2.0, 'medium': 1.5, 'hard': 1.0}   # Star FWD (same as regular)
        }
    }
    
    # Tier thresholds for each position: (hard_max, medium_max, easy_min)
    # Score categories: <hard_max = HARD, hard_max to medium_max = MEDIUM, >medium_max = EASY
    POSITION_TIERS = {
        1: {'hard': 1.0, 'medium': 1.5, 'easy': 2.0},       # GK: <1 hard, 1-1.5 mid, 2+ easy
        2: {'hard': 4.0, 'medium': 5.0, 'easy': 5.0},       # DEF: <4 hard, 4-5 mid, 5+ easy
        3: {'hard': 4.5, 'medium': 6.0, 'easy': 6.0},       # MID: <4.5 hard, 4.5-6 mid, 6+ easy
        4: {'hard': 2.0, 'medium': 3.0, 'easy': 3.0}        # FWD: <2 hard, 2-3 mid, 3+ easy
    }
    
    POSITION_NAMES = {
        1: 'GK',
        2: 'DEF',
        3: 'MID',
        4: 'FWD'
    }
    
    # FDR difficulty tiers (matching fixture grid colors)
    EASY_FDR_THRESHOLD = 2.5    # Green: FDR <= 2.5
    MEDIUM_FDR_THRESHOLD = 3.5  # Orange: 2.5 < FDR <= 3.5
    # Red: FDR > 3.5 (hard fixtures)
    
    # Formation constraints for FPL Draft: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD (total = 11)
    FORMATION_CONSTRAINTS = {
        1: (1, 1),   # GK: exactly 1
        2: (3, 5),   # DEF: 3-5
        3: (2, 5),   # MID: 2-5
        4: (1, 3)    # FWD: 1-3
    }
    
    def __init__(self, gw_start: int, gw_end: int):
        """
        Initialize analyzer for a specific gameweek range.
        
        Args:
            gw_start: Starting gameweek for analysis
            gw_end: Ending gameweek for analysis
        """
        self.gw_start = gw_start
        self.gw_end = gw_end
        self.con = get_connection()
        self.repo = SquadAnalysisRepository(self.con)
        
        # Cache FDR data for the range
        self.fdr_cache = self._build_fdr_cache()
    
    def _build_fdr_cache(self) -> Dict[Tuple[int, int], float]:
        """
        Build a lookup cache for FDR: (team_id, gameweek) -> fdr.
        
        Returns:
            Dictionary mapping (team_id, gameweek) to FDR value
        """
        fdr_data = self.repo.get_fixture_difficulty_range(self.gw_start, self.gw_end)
        cache = {}
        
        for row in fdr_data:
            key = (row['team_id'], row['gameweek'])
            cache[key] = row['fdr']
        
        return cache
    
    def get_fdr(self, team_id: int, gameweek: int) -> Optional[float]:
        """
        Get FDR for a team in a specific gameweek.
        
        Args:
            team_id: Premier League team ID
            gameweek: Gameweek number
            
        Returns:
            FDR value or None if not found
        """
        return self.fdr_cache.get((team_id, gameweek))
    
    def analyze_squad(self, entry_id: int, current_gw: int, 
                     excluded_player_ids: Optional[List[int]] = None) -> Dict:
        """
        Analyze squad fixture strength across positions and gameweeks.
        
        Args:
            entry_id: FPL entry ID
            current_gw: Current gameweek (for fetching squad data)
            excluded_player_ids: Players to exclude from analysis (for "what-if")
            
        Returns:
            Dictionary containing full analysis results with squad details and optimal lineups
        """
        excluded_player_ids = excluded_player_ids or []
        
        # Fetch squad with team info
        full_squad = self.repo.get_squad_with_teams(entry_id, current_gw)
        
        # Calculate per-player scores for each gameweek
        squad_with_scores = self._calculate_player_scores(full_squad)
        
        # Filter out excluded players for analysis
        squad = [p for p in squad_with_scores if p['player_id'] not in excluded_player_ids]
        
        # Group players by position
        players_by_position = defaultdict(list)
        for player in squad:
            players_by_position[player['position']].append(player)
        
        # Analyze each gameweek
        by_gameweek = []
        total_score = 0.0
        success_count = 0
        position_failure_counts = defaultdict(int)
        
        for gw in range(self.gw_start, self.gw_end + 1):
            gw_analysis = {'gw': gw}
            gw_success = True
            
            for pos_id, pos_name in self.POSITION_NAMES.items():
                score, contributing_players = self.calculate_position_score(
                    players_by_position[pos_id], gw, pos_id  # Pass position_id
                )
                
                # Determine tier for this position's score
                tier = self.get_position_tier(score, pos_id)
                
                # Count non-easy tiers as failures for summary stats
                if tier != 'easy':
                    gw_success = False
                    position_failure_counts[pos_name] += 1
                
                gw_analysis[pos_name] = {
                    'score': round(score, 2),
                    'tier': tier,  # New: tier classification
                    'thresholds': self.POSITION_TIERS[pos_id],  # Show all thresholds
                    'players': contributing_players
                }
                
                total_score += score
            
            if gw_success:
                success_count += 1
            
            by_gameweek.append(gw_analysis)
        
        # Calculate summary statistics
        total_gws = self.gw_end - self.gw_start + 1
        success_rate = (success_count / total_gws * 100) if total_gws > 0 else 0
        
        # Find weakest position (most failures)
        weakest_position = max(position_failure_counts.items(), 
                              key=lambda x: x[1])[0] if position_failure_counts else None
        
        # Generate recommendations
        recommendations = self.generate_recommendations(
            by_gameweek, 
            squad,
            current_gw,
            excluded_player_ids
        )
        
        # Calculate optimal lineups for each gameweek
        optimal_lineups = self._calculate_optimal_lineups(squad_with_scores)
        
        return {
            'entry_id': entry_id,
            'gw_range': {'start': self.gw_start, 'end': self.gw_end},
            'total_score': round(total_score, 2),
            'success_rate': round(success_rate, 1),
            'success_count': success_count,
            'total_gameweeks': total_gws,
            'by_gameweek': by_gameweek,
            'weakest_position': weakest_position,
            'position_failures': dict(position_failure_counts),
            'squad_size': len(full_squad),
            'excluded_count': len(excluded_player_ids),
            'full_squad': squad_with_scores,  # NEW: All 15 players with scores
            'optimal_lineups': optimal_lineups,  # NEW: Best 11 for each GW
            'recommendations': recommendations
        }
    
    def calculate_position_score(self, players: List[Dict], gameweek: int, position_id: int) -> Tuple[float, List[Dict]]:
        """
        Calculate fixture score for a position in a specific gameweek using position-specific scoring.
        
        Args:
            players: List of players in the position
            gameweek: Gameweek to analyze
            position_id: Position ID (1=GK, 2=DEF, 3=MID, 4=FWD)
            
        Returns:
            Tuple of (score, contributing_players_details)
        """
        score = 0.0
        contributing_players = []
        
        for player in players:
            team_id = player['team_id']
            fdr = self.get_fdr(team_id, gameweek)
            
            if fdr is None:
                continue
            
            # Determine difficulty tier based on FDR
            if fdr <= self.EASY_FDR_THRESHOLD:
                difficulty_tier = 'easy'
            elif fdr <= self.MEDIUM_FDR_THRESHOLD:
                difficulty_tier = 'medium'
            else:
                difficulty_tier = 'hard'
            
            # Get position-specific score using new matrix
            is_star = player.get('is_star_player', False)
            player_score = self.POSITION_SCORING[position_id][is_star][difficulty_tier]
            score += player_score
            
            contributing_players.append({
                'player_id': player['player_id'],
                'name': player['web_name'],
                'team': player['pl_team'],
                'fdr': round(fdr, 1),
                'score': round(player_score, 2),
                'difficulty_tier': difficulty_tier,
                'is_star': is_star,
                'total_points': player['total_points']
            })
        
        # Sort by score (highest contribution first) then by FDR (easier fixtures first)
        contributing_players.sort(key=lambda x: (-x['score'], x['fdr']))
        
        return score, contributing_players
    
    def get_position_tier(self, score: float, position_id: int) -> str:
        """
        Determine the tier (hard/medium/easy) for a position's total score.
        
        Args:
            score: Total position score
            position_id: Position ID (1=GK, 2=DEF, 3=MID, 4=FWD)
            
        Returns:
            Tier string: 'hard', 'medium', or 'easy'
        """
        tiers = self.POSITION_TIERS[position_id]
        
        if score < tiers['hard']:
            return 'hard'
        elif score < tiers['medium']:
            return 'medium'
        else:
            return 'easy'
    
    def _calculate_player_scores(self, squad: List[Dict]) -> List[Dict]:
        """
        Calculate each player's fixture score for each gameweek.
        
        Args:
            squad: List of players with team info
            
        Returns:
            Squad with added 'gw_scores' field for each player
        """
        for player in squad:
            player['gw_scores'] = {}
            position_id = player['position']
            is_star = player.get('is_star_player', False)
            
            for gw in range(self.gw_start, self.gw_end + 1):
                fdr = self.get_fdr(player['team_id'], gw)
                
                if fdr is None:
                    player['gw_scores'][gw] = 0.0
                    continue
                
                # Determine difficulty tier
                if fdr <= self.EASY_FDR_THRESHOLD:
                    difficulty_tier = 'easy'
                elif fdr <= self.MEDIUM_FDR_THRESHOLD:
                    difficulty_tier = 'medium'
                else:
                    difficulty_tier = 'hard'
                
                # Get score from position-specific matrix
                score = self.POSITION_SCORING[position_id][is_star][difficulty_tier]
                player['gw_scores'][gw] = score
        
        return squad
    
    def _calculate_optimal_lineups(self, squad: List[Dict]) -> List[Dict]:
        """
        Calculate the optimal 11-player lineup for each gameweek.
        Formation constraints: 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD (total = 11)
        
        Args:
            squad: Squad with gw_scores calculated
            
        Returns:
            List of optimal lineups per gameweek
        """
        optimal_lineups = []
        
        for gw in range(self.gw_start, self.gw_end + 1):
            # Group players by position with their scores
            players_by_pos = defaultdict(list)
            for player in squad:
                pos_id = player['position']
                score = player['gw_scores'].get(gw, 0.0)
                players_by_pos[pos_id].append({
                    'player_id': player['player_id'],
                    'name': player['web_name'],
                    'position': pos_id,
                    'score': score,
                    'team': player['pl_team'],
                    'is_star': player.get('is_star_player', False)
                })
            
            # Sort each position by score (descending)
            for pos_id in players_by_pos:
                players_by_pos[pos_id].sort(key=lambda x: x['score'], reverse=True)
            
            # Find best formation that maximizes score
            best_lineup = self._find_best_formation(players_by_pos)
            
            optimal_lineups.append({
                'gw': gw,
                'lineup': best_lineup['players'],
                'formation': best_lineup['formation'],
                'total_score': best_lineup['score']
            })
        
        return optimal_lineups
    
    def _find_best_formation(self, players_by_pos: Dict[int, List[Dict]]) -> Dict:
        """
        Find the best 11-player formation from available players.
        
        Args:
            players_by_pos: Dict mapping position_id to sorted list of players
            
        Returns:
            Dict with 'players', 'formation', and 'score'
        """
        # Valid formations: (GK, DEF, MID, FWD)
        valid_formations = [
            (1, 3, 5, 2),  # 3-5-2
            (1, 3, 4, 3),  # 3-4-3
            (1, 4, 5, 1),  # 4-5-1
            (1, 4, 4, 2),  # 4-4-2
            (1, 4, 3, 3),  # 4-3-3
            (1, 5, 4, 1),  # 5-4-1
            (1, 5, 3, 2),  # 5-3-2
            (1, 5, 2, 3),  # 5-2-3
        ]
        
        best_lineup = None
        best_score = -1
        
        for formation in valid_formations:
            gk_count, def_count, mid_count, fwd_count = formation
            
            # Check if we have enough players for this formation
            if (len(players_by_pos.get(1, [])) < gk_count or
                len(players_by_pos.get(2, [])) < def_count or
                len(players_by_pos.get(3, [])) < mid_count or
                len(players_by_pos.get(4, [])) < fwd_count):
                continue
            
            # Select top players for this formation
            lineup = []
            total_score = 0.0
            
            lineup.extend(players_by_pos[1][:gk_count])
            lineup.extend(players_by_pos[2][:def_count])
            lineup.extend(players_by_pos[3][:mid_count])
            lineup.extend(players_by_pos[4][:fwd_count])
            
            total_score = sum(p['score'] for p in lineup)
            
            if total_score > best_score:
                best_score = total_score
                best_lineup = {
                    'players': lineup,
                    'formation': f'{def_count}-{mid_count}-{fwd_count}',
                    'score': round(total_score, 2)
                }
        
        # If no valid formation found, return empty
        if best_lineup is None:
            return {'players': [], 'formation': 'N/A', 'score': 0.0}
        
        return best_lineup
    
    def generate_recommendations(
        self, 
        by_gameweek: List[Dict], 
        current_squad: List[Dict],
        current_gw: int,
        excluded_player_ids: List[int],
        max_results: int = 50
    ) -> List[Dict]:
        """
        Generate transfer recommendations to fix weak gameweeks.
        
        Args:
            by_gameweek: Analysis results by gameweek
            current_squad: Current squad composition
            current_gw: Current gameweek
            excluded_player_ids: Players user wants to replace
            max_results: Maximum number of recommendations
            
        Returns:
            List of recommended players with scores
        """
        # Identify weak gameweeks by position (not 'easy' tier)
        weak_gws_by_position = defaultdict(list)
        
        for gw_data in by_gameweek:
            gw = gw_data['gw']
            for pos_name in ['GK', 'DEF', 'MID', 'FWD']:
                if gw_data[pos_name]['tier'] != 'easy':
                    weak_gws_by_position[pos_name].append(gw)
        
        # Get current squad's PL teams to encourage diversity
        squad_team_counts = defaultdict(int)
        for player in current_squad:
            if player['player_id'] not in excluded_player_ids:
                squad_team_counts[player['team_id']] += 1
        
        # Fetch free agents with fixture info
        all_candidates = self.repo.get_free_agents_with_fixtures(
            current_gw,
            self.gw_start,
            self.gw_end,
            limit=200
        )
        
        # Score each candidate
        scored_candidates = []
        
        for player in all_candidates:
            # Calculate fixture improvement score
            position_id = player['position']
            pos_name = self.POSITION_NAMES[position_id]
            weak_gws = weak_gws_by_position.get(pos_name, [])
            
            if not weak_gws:
                # No weak GWs for this position, skip
                continue
            
            # Count how many weak GWs this player helps fix (gradient scoring)
            fixture_improvement_score = 0.0
            for gw in weak_gws:
                fdr = self.get_fdr(player['team_id'], gw)
                if fdr is None:
                    continue
                
                # Use gradient scoring: easy fixtures contribute more
                if fdr <= self.EASY_FDR_THRESHOLD:
                    fixture_improvement_score += 1.0  # Full credit
                elif fdr <= self.MEDIUM_FDR_THRESHOLD:
                    fixture_improvement_score += 0.5  # Half credit
                else:
                    fixture_improvement_score += 0.2  # Minimal credit
            
            if fixture_improvement_score == 0:
                continue
            
            # Fixture improvement as percentage of weak GWs fixed (normalized 0-100)
            fixture_improvement = (fixture_improvement_score / len(weak_gws)) * 100 if weak_gws else 0
            
            # FPL performance score (normalized to 0-100)
            max_points = 150  # Reasonable max for normalization
            fpl_performance = min((player['total_points'] / max_points) * 100, 100)
            
            # Team diversity bonus (negative if team is already well-represented)
            team_count = squad_team_counts.get(player['team_id'], 0)
            diversity_bonus = max(0, 10 - (team_count * 5))  # -5 points per existing player
            
            # Combined score: 60% fixture improvement + 40% FPL performance + diversity
            combined_score = (
                fixture_improvement * 0.6 +
                fpl_performance * 0.4 +
                diversity_bonus
            )
            
            scored_candidates.append({
                'player_id': player['id'],
                'name': player['web_name'],
                'team': player['team_name'],
                'position': pos_name,
                'position_id': position_id,
                'total_points': player['total_points'],
                'recent_form': player.get('recent_form', 0),
                'easy_fixtures': player.get('easy_fixtures', 0),
                'avg_fdr': player.get('avg_fdr', 0),
                'fixture_improvement_score': round(fixture_improvement_score, 2),
                'weak_gws_count': len(weak_gws),
                'fixture_improvement': round(fixture_improvement, 1),
                'fpl_performance': round(fpl_performance, 1),
                'diversity_bonus': round(diversity_bonus, 1),
                'combined_score': round(combined_score, 1),
                'team_count_in_squad': team_count
            })
        
        # Sort by combined score (descending)
        scored_candidates.sort(key=lambda x: -x['combined_score'])
        
        # Return top N
        return scored_candidates[:max_results]
    
    def analyze_all_managers(self, current_gw: int) -> List[Dict]:
        """
        Analyze all FPL managers and rank by fixture strength.
        
        Args:
            current_gw: Current gameweek for squad data
            
        Returns:
            List of manager analyses sorted by total score
        """
        entries = self.repo.get_all_entries()
        results = []
        
        for entry in entries:
            try:
                analysis = self.analyze_squad(entry['entry_id'], current_gw)
                results.append({
                    'entry_id': entry['entry_id'],
                    'entry_name': entry['entry_name'],
                    'short_name': entry.get('short_name', ''),
                    'total_score': analysis['total_score'],
                    'success_rate': analysis['success_rate'],
                    'weakest_position': analysis['weakest_position'],
                    'squad_size': analysis['squad_size']
                })
            except Exception as e:
                print(f"[SquadFixtureAnalyzer] Error analyzing entry {entry['entry_id']}: {e}")
                continue
        
        # Sort by total score (descending)
        results.sort(key=lambda x: -x['total_score'])
        
        # Add rank
        for i, result in enumerate(results, 1):
            result['rank'] = i
        
        return results
