"""
Lineup Validator - Ensures exactly 11 players per team with smart position conflict resolution.

Handles:
- Formation constraints (1 GK, 3-5 DEF, 3-5 MID, 1-3 FWD)
- Position conflicts when >11 players predicted
- Missing players when <11 players predicted
- Probability adjustments based on rotation risk
"""

from typing import List, Dict, Tuple
from collections import defaultdict


class LineupValidator:
    """Validates and adjusts predicted lineups to exactly 11 players per team."""
    
    # Formation rules: (min, max) for each position
    FORMATION_RULES = {
        1: (1, 1),   # GK: exactly 1
        2: (3, 5),   # DEF: 3-5
        3: (3, 5),   # MID: 3-5
        4: (1, 3)    # FWD: 1-3
    }
    
    # Common formations (most to least likely)
    COMMON_FORMATIONS = [
        (1, 4, 3, 3),  # 4-3-3
        (1, 4, 4, 2),  # 4-4-2
        (1, 3, 4, 3),  # 3-4-3
        (1, 4, 5, 1),  # 4-5-1
        (1, 5, 3, 2),  # 5-3-2
        (1, 3, 5, 2),  # 3-5-2
        (1, 5, 4, 1),  # 5-4-1
    ]
    
    def __init__(self):
        self.stats = {
            'teams_validated': 0,
            'lineups_adjusted': 0,
            'players_demoted': 0,
            'players_promoted': 0,
            'formations_applied': {}
        }
    
    def validate_team_lineup(self, team_players: List[dict]) -> List[dict]:
        """
        Validate and adjust a team's lineup to exactly 11 players.
        
        Args:
            team_players: List of player predictions for a team
            
        Returns:
            Adjusted list with exactly 11 starters (start_probability >= 0.7)
        """
        if not team_players:
            return []
        
        self.stats['teams_validated'] += 1
        
        # Group by position
        by_position = defaultdict(list)
        for player in team_players:
            pos = player.get('position', 0)
            if pos in [1, 2, 3, 4]:
                by_position[pos].append(player)
        
        # Sort each position by probability, then by other factors
        for pos in by_position:
            by_position[pos].sort(
                key=lambda p: (
                    p.get('start_probability', 0),
                    not p.get('injured', False),
                    not p.get('suspended', False),
                    not p.get('doubtful', False),
                    p.get('sources_count', 0)
                ),
                reverse=True
            )
        
        # Count current starters (prob >= 0.7)
        current_starters = [p for p in team_players if p.get('start_probability', 0) >= 0.7 
                           and not p.get('injured') and not p.get('suspended')]
        
        num_starters = len(current_starters)
        
        if num_starters == 11:
            # Perfect! No adjustment needed
            return team_players
        
        elif num_starters > 11:
            # Too many starters - need to demote some
            return self._reduce_to_11(by_position, team_players)
        
        else:
            # Not enough starters - need to promote some
            return self._expand_to_11(by_position, team_players)
    
    def _reduce_to_11(self, by_position: Dict[int, List[dict]], all_players: List[dict]) -> List[dict]:
        """Reduce lineup when >11 starters predicted."""
        self.stats['lineups_adjusted'] += 1
        
        # Try each common formation
        for formation in self.COMMON_FORMATIONS:
            gk_count, def_count, mid_count, fwd_count = formation
            
            # Check if we have enough players for this formation
            if (len(by_position[1]) >= gk_count and
                len(by_position[2]) >= def_count and
                len(by_position[3]) >= mid_count and
                len(by_position[4]) >= fwd_count):
                
                # Select players for this formation
                selected = []
                selected.extend(by_position[1][:gk_count])
                selected.extend(by_position[2][:def_count])
                selected.extend(by_position[3][:mid_count])
                selected.extend(by_position[4][:fwd_count])
                
                # Adjust probabilities
                adjusted = self._adjust_probabilities(selected, by_position, formation)
                
                formation_str = f"{def_count}-{mid_count}-{fwd_count}"
                self.stats['formations_applied'][formation_str] = \
                    self.stats['formations_applied'].get(formation_str, 0) + 1
                
                return adjusted
        
        # Fallback: pick top 11 by probability
        starters = [p for p in all_players if not p.get('injured') and not p.get('suspended')]
        starters.sort(key=lambda p: p.get('start_probability', 0), reverse=True)
        
        top_11 = starters[:11]
        for p in top_11:
            p['start_probability'] = 1.0
            p['validation_note'] = 'Top 11 by probability'
        
        # Demote others
        for p in starters[11:]:
            old_prob = p.get('start_probability', 0)
            if old_prob >= 0.7:
                p['start_probability'] = 0.6  # Rotation risk
                p['doubtful'] = True
                p['validation_note'] = 'Rotation risk (competing for spot)'
                self.stats['players_demoted'] += 1
        
        return all_players
    
    def _expand_to_11(self, by_position: Dict[int, List[dict]], all_players: List[dict]) -> List[dict]:
        """Expand lineup when <11 starters predicted."""
        self.stats['lineups_adjusted'] += 1
        
        # Find best formation with available players
        for formation in self.COMMON_FORMATIONS:
            gk_count, def_count, mid_count, fwd_count = formation
            
            if (len(by_position[1]) >= gk_count and
                len(by_position[2]) >= def_count and
                len(by_position[3]) >= mid_count and
                len(by_position[4]) >= fwd_count):
                
                # Promote players to reach formation
                for pos_idx, (pos_code, count) in enumerate([(1, gk_count), (2, def_count), 
                                                               (3, mid_count), (4, fwd_count)]):
                    for i, player in enumerate(by_position[pos_code]):
                        if i < count:
                            if player.get('start_probability', 0) < 0.7:
                                player['start_probability'] = 0.85  # Likely starter
                                player['validation_note'] = 'Promoted to complete formation'
                                self.stats['players_promoted'] += 1
                        else:
                            # Set as backup
                            if player.get('start_probability', 0) >= 0.7:
                                player['start_probability'] = 0.5
                                player['doubtful'] = True
                
                formation_str = f"{def_count}-{mid_count}-{fwd_count}"
                self.stats['formations_applied'][formation_str] = \
                    self.stats['formations_applied'].get(formation_str, 0) + 1
                
                return all_players
        
        # If no formation fits, mark missing players
        print(f"[Validator] ⚠️ Cannot form valid 11 - missing players")
        return all_players
    
    def _adjust_probabilities(self, selected: List[dict], by_position: Dict[int, List[dict]], 
                              formation: Tuple[int, int, int, int]) -> List[dict]:
        """Adjust probabilities based on position competition."""
        gk_count, def_count, mid_count, fwd_count = formation
        
        # Set selected players to high probability
        for player in selected:
            player['start_probability'] = 1.0
            player['validation_note'] = 'Validated starter'
        
        # Adjust non-selected players
        formation_map = {1: gk_count, 2: def_count, 3: mid_count, 4: fwd_count}
        
        for pos_code, max_count in formation_map.items():
            position_players = by_position.get(pos_code, [])
            
            for i, player in enumerate(position_players):
                if i < max_count:
                    # Already selected
                    continue
                elif i == max_count:
                    # First backup - 60% chance
                    player['start_probability'] = 0.6
                    player['doubtful'] = True
                    player['validation_note'] = 'Primary rotation option'
                    self.stats['players_demoted'] += 1
                elif i == max_count + 1:
                    # Second backup - 40% chance
                    player['start_probability'] = 0.4
                    player['doubtful'] = True
                    player['validation_note'] = 'Secondary rotation option'
                    self.stats['players_demoted'] += 1
                else:
                    # Unlikely to start
                    if player.get('start_probability', 0) >= 0.7:
                        player['start_probability'] = 0.2
                        player['validation_note'] = 'Unlikely (position filled)'
                        self.stats['players_demoted'] += 1
        
        return position_players
    
    def get_stats(self) -> Dict:
        """Get validation statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            'teams_validated': 0,
            'lineups_adjusted': 0,
            'players_demoted': 0,
            'players_promoted': 0,
            'formations_applied': {}
        }


def validate_all_predictions(predictions: List[dict]) -> List[dict]:
    """
    Validate all predictions, ensuring each team has exactly 11 starters.
    
    Args:
        predictions: List of all player predictions
        
    Returns:
        Validated predictions with adjusted probabilities
    """
    validator = LineupValidator()
    
    # Group by team
    by_team = defaultdict(list)
    for pred in predictions:
        team_id = pred.get('team_id')
        if team_id:
            by_team[team_id].append(pred)
    
    # Validate each team
    validated = []
    for team_id, team_players in by_team.items():
        validated_team = validator.validate_team_lineup(team_players)
        validated.extend(validated_team)
    
    stats = validator.get_stats()
    print(f"[Validator] ✅ Validated {stats['teams_validated']} teams")
    print(f"[Validator] Adjusted {stats['lineups_adjusted']} lineups")
    print(f"[Validator] Demoted {stats['players_demoted']} players, Promoted {stats['players_promoted']} players")
    if stats['formations_applied']:
        print(f"[Validator] Formations applied: {stats['formations_applied']}")
    
    return validated
