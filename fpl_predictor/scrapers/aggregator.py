"""
Lineup aggregator module for combining predictions from multiple sources.

Takes raw predictions from multiple scraper sources and creates consensus predictions
with probability scores.
"""

from collections import defaultdict
from typing import Dict, List, Optional
import json
import re

from fpl_predictor.utils.name_matcher import SmartPlayerMatcher


# Player name mapping to handle variations
PLAYER_NAME_ALIASES = {
    'gabriel jesus': 'jesus',
    'gabriel martinelli': 'martinelli',
    'gabriel magalhaes': 'gabriel',
    'emiliano martinez': 'martinez',
    'lisandro martinez': 'lisandro',
    'bruno fernandes': 'fernandes',
}


class LineupAggregator:
    """Aggregates predicted lineups from multiple sources into consensus predictions."""
    
    def __init__(self):
        """Initialize the aggregator."""
        self.team_name_map = self._build_team_name_map()
        self.matcher = SmartPlayerMatcher()
    
    def _build_team_name_map(self) -> Dict[str, str]:
        """
        Build a mapping of team name variations to canonical names.
        
        Returns:
            Dictionary mapping various team names to standard 3-letter codes
        """
        return {
            # Full names
            'arsenal': 'ARS',
            'aston villa': 'AVL',
            'villa': 'AVL',
            'bournemouth': 'BOU',
            'brentford': 'BRE',
            'brighton': 'BHA',
            'brighton & hove albion': 'BHA',
            'brighton and hove albion': 'BHA',
            'chelsea': 'CHE',
            'crystal palace': 'CRY',
            'palace': 'CRY',
            'everton': 'EVE',
            'fulham': 'FUL',
            'liverpool': 'LIV',
            'manchester city': 'MCI',
            'man city': 'MCI',
            'city': 'MCI',
            'manchester united': 'MUN',
            'man united': 'MUN',
            'man utd': 'MUN',
            'united': 'MUN',
            'newcastle': 'NEW',
            'newcastle united': 'NEW',
            'nottingham forest': 'NFO',
            'nott\'m forest': 'NFO',
            'forest': 'NFO',
            'nottm forest': 'NFO',
            'tottenham': 'TOT',
            'tottenham hotspur': 'TOT',
            'spurs': 'TOT',
            'west ham': 'WHU',
            'west ham united': 'WHU',
            'wolverhampton': 'WOL',
            'wolverhampton wanderers': 'WOL',
            'wolves': 'WOL',
            'leicester': 'LEI',
            'leicester city': 'LEI',
            'leeds': 'LEE',
            'leeds united': 'LEE',
            'southampton': 'SOU',
            'burnley': 'BUR',
            'sunderland': 'SUN',
            # Lowercase abbreviations (for sources that use them)
            'ars': 'ARS',
            'avl': 'AVL',
            'bou': 'BOU',
            'bre': 'BRE',
            'bha': 'BHA',
            'che': 'CHE',
            'cry': 'CRY',
            'eve': 'EVE',
            'ful': 'FUL',
            'liv': 'LIV',
            'mci': 'MCI',
            'mun': 'MUN',
            'new': 'NEW',
            'nfo': 'NFO',
            'not': 'NFO',  # RotoWire uses "NOT" for Nottingham Forest
            'tot': 'TOT',
            'whu': 'WHU',
            'wol': 'WOL',
            'lei': 'LEI',
            'lee': 'LEE',
            'sou': 'SOU',
            'bur': 'BUR',
            'sun': 'SUN',
            'brn': 'BUR',  # Some sources use BRN for Burnley
        }
    
    def _normalize_team_name(self, team_name: str) -> Optional[str]:
        """
        Normalize team name to 3-letter code.
        
        Args:
            team_name: Team name from source (can be full name or abbreviation)
            
        Returns:
            3-letter team code or None if not found
        """
        team_stripped = team_name.strip()
        team_lower = team_stripped.lower()
        
        # Check if it's already a 3-letter code (e.g., "MUN", "ARS")
        if len(team_stripped) == 3 and team_stripped.isupper():
            return team_stripped
        
        # Try to map from full name
        return self.team_name_map.get(team_lower)
    
    def _normalize_player_name(self, player_name: str) -> str:
        """
        Normalize player name for matching.
        
        Args:
            player_name: Raw player name from source
            
        Returns:
            Normalized player name (lowercase, no punctuation)
        """
        normalized = player_name.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Check for known aliases
        if normalized in PLAYER_NAME_ALIASES:
            return PLAYER_NAME_ALIASES[normalized]
        
        return normalized
    
    def aggregate_weighted(self, source_predictions: Dict[str, List[dict]], 
                          source_weights: Dict[str, float], gameweek: int) -> List[dict]:
        """
        Aggregate predictions from multiple sources using weighted averaging.
        
        This method combines predictions from different sources, giving each source
        a different weight. For example:
        - RotoWire (60% weight): Player at 100% → contributes 60%
        - FF Scout (40% weight): Player at 50% → contributes 20%
        - Final: 80% start probability
        
        Args:
            source_predictions: Dict mapping source name to list of predictions
            source_weights: Dict mapping source name to weight (0.0-1.0)
            gameweek: Gameweek number
            
        Returns:
            List of aggregated predictions with weighted probabilities
        """
        # Group predictions by (player_name, team)
        player_predictions = defaultdict(lambda: {
            'source_probabilities': {},  # {source_name: probability}
            'sources': [],
            'injured': False,
            'injury_details': [],
            'suspended': False,
            'doubtful': False,
            'team_code': None,
            'raw_team_name': None
        })
        
        # Normalize total weight (in case weights don't sum to 1.0)
        total_weight = sum(source_weights.values())
        
        if total_weight == 0:
            print("[Aggregator] Warning: Total source weight is 0")
            return []
        
        print(f"[Aggregator] Weighted aggregation from {len(source_predictions)} sources for GW{gameweek}")
        print(f"[Aggregator] Source weights: {source_weights}")
        
        # Process predictions from each source
        for source_name, predictions in source_predictions.items():
            if not predictions:
                print(f"[Aggregator] Source '{source_name}' returned no predictions")
                continue
            
            source_weight = source_weights.get(source_name, 0.0)
            
            print(f"[Aggregator] Processing {len(predictions)} predictions from '{source_name}' (weight: {source_weight})")
            
            for pred in predictions:
                # Normalize names
                player_name = self._normalize_player_name(pred.get('player_name', ''))
                team_name = pred.get('team_name', '')
                team_code = self._normalize_team_name(team_name)
                
                if not player_name or not team_code:
                    continue  # Skip if can't identify player/team
                
                # Create key for this player
                key = (player_name, team_code)
                
                # Extract or calculate start probability for this source
                # Check if source already calculated a probability
                if 'start_probability_raw' in pred:
                    source_start_prob = pred['start_probability_raw']
                elif pred.get('starting'):
                    source_start_prob = 1.0
                elif pred.get('bench'):
                    source_start_prob = 0.0
                else:
                    source_start_prob = 0.0
                
                # Store this source's probability
                player_predictions[key]['source_probabilities'][source_name] = source_start_prob
                
                # Store team info
                if not player_predictions[key]['team_code']:
                    player_predictions[key]['team_code'] = team_code
                    player_predictions[key]['raw_team_name'] = team_name
                
                # Record source details
                player_predictions[key]['sources'].append({
                    'name': source_name,
                    'weight': source_weight,
                    'probability': source_start_prob,
                    'status': pred.get('status'),
                    'confidence': pred.get('confidence')
                })
                
                # Aggregate injury/suspension data
                if pred.get('injured'):
                    player_predictions[key]['injured'] = True
                    injury_detail = pred.get('injury_details') or pred.get('raw_status') or 'Injured'
                    if injury_detail:
                        player_predictions[key]['injury_details'].append(f"[{source_name}] {injury_detail}")
                
                if pred.get('suspended'):
                    player_predictions[key]['suspended'] = True
                
                if pred.get('doubtful'):
                    player_predictions[key]['doubtful'] = True
        
        # Calculate weighted probabilities and build final output
        aggregated = []
        
        for (player_name, team_code), data in player_predictions.items():
            # Calculate weighted average start probability
            weighted_sum = 0.0
            total_applicable_weight = 0.0
            
            for source_name, prob in data['source_probabilities'].items():
                weight = source_weights.get(source_name, 0.0)
                weighted_sum += prob * weight
                total_applicable_weight += weight
            
            # Normalize by actual weights used
            if total_applicable_weight > 0:
                start_prob = weighted_sum / total_applicable_weight
            else:
                start_prob = 0.0
            
            # Apply injury/suspension penalties
            if data['injured'] or data['suspended']:
                start_prob = 0.0  # Override to 0% for injured/suspended
            elif data['doubtful'] and start_prob > 0.5:
                # Only reduce doubtful players if they have >50% probability
                start_prob *= 0.7  # Moderate reduction for doubtful
            
            aggregated.append({
                'player_name': player_name,
                'team_code': team_code,
                'team_name': data['raw_team_name'],
                'gameweek': gameweek,
                'start_probability': start_prob,
                'bench_probability': 0.0,  # Not tracking bench in weighted mode
                'sources_count': len(data['source_probabilities']),
                'sources_data': json.dumps(data['sources']),
                'injured': data['injured'],
                'injury_details': ' | '.join(data['injury_details']) if data['injury_details'] else None,
                'suspended': data['suspended'],
                'doubtful': data['doubtful']
            })
        
        # Sort by start probability (highest first)
        aggregated.sort(key=lambda x: x['start_probability'], reverse=True)
        
        print(f"[Aggregator] Created {len(aggregated)} weighted predictions")
        print(f"[Aggregator] High confidence starters (≥80%): {len([p for p in aggregated if p['start_probability'] >= 0.8])}")
        print(f"[Aggregator] Moderate confidence (50-80%): {len([p for p in aggregated if 0.5 <= p['start_probability'] < 0.8])}")
        print(f"[Aggregator] Doubtful (<50%): {len([p for p in aggregated if p['start_probability'] < 0.5])}")
        
        return aggregated
    
    def aggregate_predictions(self, raw_data: Dict[str, List[dict]], gameweek: int) -> List[dict]:
        """
        Combine predictions from multiple sources into consensus.
        
        Args:
            raw_data: Dictionary mapping source name to list of predictions
            gameweek: Gameweek number
            
        Returns:
            List of aggregated predictions with probabilities
        """
        # Group predictions by (player_name, team)
        player_predictions = defaultdict(lambda: {
            'starts': 0,
            'benches': 0,
            'not_playing': 0,
            'sources': [],
            'injured': False,
            'injury_details': [],
            'suspended': False,
            'doubtful': False,
            'team_code': None,
            'raw_team_name': None
        })
        
        # Count active sources (those that returned data)
        total_sources = len([s for s in raw_data.values() if s])
        
        if total_sources == 0:
            print("[Aggregator] No sources returned data")
            return []
        
        print(f"[Aggregator] Aggregating from {total_sources} sources for GW{gameweek}")
        
        # Process predictions from each source
        for source_name, predictions in raw_data.items():
            if not predictions:
                continue
            
            for pred in predictions:
                # Normalize names
                player_name = self._normalize_player_name(pred.get('player_name', ''))
                team_name = pred.get('team_name', '')
                team_code = self._normalize_team_name(team_name)
                
                if not player_name or not team_code:
                    continue  # Skip if can't identify player/team
                
                # Create key for this player
                key = (player_name, team_code)
                
                # Count predictions
                if pred.get('starting'):
                    player_predictions[key]['starts'] += 1
                elif pred.get('bench'):
                    player_predictions[key]['benches'] += 1
                else:
                    player_predictions[key]['not_playing'] += 1
                
                # Store team info
                if not player_predictions[key]['team_code']:
                    player_predictions[key]['team_code'] = team_code
                    player_predictions[key]['raw_team_name'] = team_name
                
                # Record source
                player_predictions[key]['sources'].append({
                    'name': source_name,
                    'status': pred.get('status'),
                    'confidence': pred.get('confidence'),
                    'starting': pred.get('starting', False),
                    'bench': pred.get('bench', False)
                })
                
                # Aggregate injury/suspension data
                if pred.get('injured'):
                    player_predictions[key]['injured'] = True
                    injury_detail = pred.get('injury_details') or pred.get('news', 'Injured')
                    if injury_detail:
                        player_predictions[key]['injury_details'].append(f"[{source_name}] {injury_detail}")
                
                if pred.get('suspended'):
                    player_predictions[key]['suspended'] = True
                
                if pred.get('doubtful'):
                    player_predictions[key]['doubtful'] = True
        
        # Calculate probabilities and build final output
        aggregated = []
        
        for (player_name, team_code), data in player_predictions.items():
            # Count UNIQUE sources that predicted this player (avoid counting duplicates)
            unique_sources_for_player = len(set(s['name'] for s in data['sources']))
            
            # Calculate start probability based on consensus
            # If multiple sources predict start, average them; if one source, use binary (0 or 1)
            if unique_sources_for_player > 0:
                # Count how many unique sources said "starting"
                sources_saying_start = len(set(s['name'] for s in data['sources'] if s['starting']))
                start_prob = sources_saying_start / unique_sources_for_player
                
                sources_saying_bench = len(set(s['name'] for s in data['sources'] if s['bench']))
                bench_prob = sources_saying_bench / unique_sources_for_player
            else:
                start_prob = 0
                bench_prob = 0
            
            # Reduce probability if injured/suspended
            if data['injured'] or data['suspended']:
                start_prob = 0.0  # Assume 0% unless more specific data available
            elif data['doubtful']:
                start_prob *= 0.6  # Moderately reduce if doubtful
            
            aggregated.append({
                'player_name': player_name,
                'team_code': team_code,
                'team_name': data['raw_team_name'],
                'gameweek': gameweek,
                'start_probability': start_prob,
                'bench_probability': bench_prob,
                'sources_count': len(data['sources']),
                'sources_data': json.dumps(data['sources']),
                'injured': data['injured'],
                'injury_details': ' | '.join(data['injury_details']) if data['injury_details'] else None,
                'suspended': data['suspended'],
                'doubtful': data['doubtful']
            })
        
        # Sort by start probability (highest first)
        aggregated.sort(key=lambda x: x['start_probability'], reverse=True)
        
        print(f"[Aggregator] Created {len(aggregated)} aggregated predictions")
        print(f"[Aggregator] High confidence starters (>80%): {len([p for p in aggregated if p['start_probability'] >= 0.8])}")
        print(f"[Aggregator] Doubtful players (30-80%): {len([p for p in aggregated if 0.3 <= p['start_probability'] < 0.8])}")
        print(f"[Aggregator] Unlikely/injured (<30%): {len([p for p in aggregated if p['start_probability'] < 0.3])}")
        
        return aggregated
    
    def match_to_fpl_players(self, aggregated_predictions: List[dict], fpl_players: List[dict]) -> List[dict]:
        """
        Match aggregated predictions to actual FPL player IDs using smart fuzzy matching.
        
        Args:
            aggregated_predictions: List of aggregated predictions
            fpl_players: List of FPL player data with IDs
            
        Returns:
            Matched predictions with player_id, team_id, match_score, and match_method fields
        """
        # Reset matcher tracking for this batch
        self.matcher.reset_tracking()
        self.matcher.reset_stats()
        
        matched = []
        unmatched_details = []
        
        for pred in aggregated_predictions:
            # Use smart matcher
            result = self.matcher.match_player(
                pred_name=pred['player_name'],
                pred_team_code=pred['team_code'],
                fpl_players=fpl_players,
                source_name=pred.get('sources_data', 'aggregated'),
                min_score=60
            )
            
            if result:
                pred['player_id'] = result['player_id']
                pred['team_id'] = result['team_id']
                pred['matched'] = True
                pred['match_score'] = result['score']
                pred['match_method'] = result['method']
                matched.append(pred)
            else:
                # Keep unmatched for logging
                pred['player_id'] = None
                pred['team_id'] = None
                pred['matched'] = False
                pred['match_score'] = 0
                pred['match_method'] = 'none'
                unmatched_details.append({
                    'name': pred['player_name'],
                    'team': pred['team_code'],
                    'prob': pred['start_probability']
                })
                matched.append(pred)
        
        # Enhanced logging with statistics
        matched_count = len([p for p in matched if p['matched']])
        total_count = len(matched)
        match_rate = (matched_count / total_count * 100) if total_count > 0 else 0
        
        print(f"[Aggregator] Matched {matched_count}/{total_count} ({match_rate:.1f}%) predictions to FPL players")
        
        # Show matching method breakdown
        stats = self.matcher.get_stats()
        print(f"[Aggregator] Match methods: Exact={stats['exact']}, Fuzzy={stats['fuzzy']}, Token={stats['token']}, Partial={stats['partial']}, Failed={stats['failed']}")
        
        # Show unmatched players (limit to top 10 by probability)
        if unmatched_details:
            unmatched_details.sort(key=lambda x: x['prob'], reverse=True)
            print(f"[Aggregator] Top unmatched players ({len(unmatched_details)} total):")
            for u in unmatched_details[:10]:
                print(f"  - {u['name']} ({u['team']}) - {u['prob']*100:.0f}% start prob")
            
            # Save unmatched players for future matching attempts
            try:
                from fpl_predictor.data.repository import PredictedLineupRepository
                repo = PredictedLineupRepository()
                for u in unmatched_details:
                    repo.upsert_unmatched_player(
                        scraped_name=u['name'],
                        team_code=u['team'],
                        source='lineup_scraper'
                    )
                print(f"[Aggregator] Saved {len(unmatched_details)} unmatched players for future matching")
            except Exception as e:
                print(f"[Aggregator] Warning: Could not save unmatched players: {e}")
        
        return matched
    
    def deduplicate_by_player_id(self, matched_predictions: List[dict], 
                                 source_weights: Dict[str, float]) -> List[dict]:
        """
        Merge duplicate predictions for the same player_id from different sources.
        
        This handles cases where the same player was matched from multiple sources
        but with different names (e.g., "Luke Shaw" vs "Shaw"), so they weren't
        combined during initial aggregation.
        
        Args:
            matched_predictions: Predictions that have been matched to player_id
            source_weights: Weight for each source
            
        Returns:
            Deduplicated list with one entry per player_id
        """
        # Group by player_id
        by_player_id = defaultdict(list)
        for pred in matched_predictions:
            player_id = pred.get('player_id')
            if player_id:
                by_player_id[player_id].append(pred)
        
        # Merge duplicates
        merged = []
        duplicates_found = 0
        
        for player_id, preds in by_player_id.items():
            if len(preds) == 1:
                # No duplicates, keep as is
                merged.append(preds[0])
            else:
                # Merge multiple predictions for same player
                duplicates_found += 1
                
                # Collect all sources
                all_sources = []
                total_weighted_prob = 0.0
                total_weight = 0.0
                
                for pred in preds:
                    # Parse sources from sources_data
                    sources_data = json.loads(pred.get('sources_data', '[]'))
                    for src in sources_data:
                        all_sources.append(src)
                        weight = src.get('weight', 0.0)
                        prob = src.get('probability', 0.0)
                        total_weighted_prob += weight * prob
                        total_weight += weight
                
                # Calculate weighted average probability
                if total_weight > 0:
                    final_prob = total_weighted_prob / total_weight
                else:
                    final_prob = max(p['start_probability'] for p in preds)
                
                # Use the prediction with the most complete data as base
                base_pred = max(preds, key=lambda p: len(p.get('player_name', '')))
                
                # Update with merged data
                base_pred['start_probability'] = final_prob
                base_pred['sources_count'] = len(all_sources)
                base_pred['sources_data'] = json.dumps(all_sources)
                
                # Merge injury/doubtful flags (OR logic)
                base_pred['injured'] = any(p.get('injured', False) for p in preds)
                base_pred['doubtful'] = any(p.get('doubtful', False) for p in preds)
                base_pred['suspended'] = any(p.get('suspended', False) for p in preds)
                
                # Merge injury details
                injury_details = [p.get('injury_details') for p in preds if p.get('injury_details')]
                if injury_details:
                    base_pred['injury_details'] = '; '.join(injury_details)
                
                merged.append(base_pred)
        
        if duplicates_found > 0:
            print(f"[Aggregator] Merged {duplicates_found} duplicate player_ids into single entries")
        
        return merged
