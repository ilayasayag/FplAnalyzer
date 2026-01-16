"""
Smart player name matching with fuzzy logic.

Handles name variations, typos, partial names, and prevents duplicate matches.
"""

from rapidfuzz import fuzz, process
from typing import List, Dict, Optional, Tuple
import re
import unicodedata


# Common player name variations
COMMON_VARIATIONS = {
    'de bruyne': 'kevin de bruyne',
    'son': 'son heung-min',
    'jota': 'diogo jota',
    'bruno': 'bruno fernandes',  # Context-dependent, but this is most common
    'gabriel': 'gabriel',  # Will be disambiguated by team
    'jesus': 'gabriel jesus',
    'martinelli': 'gabriel martinelli',
    'magalhaes': 'gabriel magalhaes',
    'martinez': 'emiliano martinez',  # Context-dependent
    'lisandro': 'lisandro martinez',
    'fernandes': 'bruno fernandes',
    'guimaraes': 'bruno guimaraes',
    'salah': 'mohamed salah',
    'mo salah': 'mohamed salah',
    'haaland': 'erling haaland',
    'kdb': 'kevin de bruyne',
    'trent': 'trent alexander-arnold',
    'taa': 'trent alexander-arnold',
    'van dijk': 'virgil van dijk',
    'vvd': 'virgil van dijk',
    'mane': 'sadio mane',
    'firmino': 'roberto firmino',
    'ederson': 'ederson moraes',
    'alisson': 'alisson becker',
    'jorginho': 'jorge luiz frello filho',
    'casemiro': 'casemiro',
    'fred': 'fred',
    'richarlison': 'richarlison',
    'raphinha': 'raphinha',
    'antony': 'antony',
}


class SmartPlayerMatcher:
    """
    Intelligent player name matching with fuzzy logic.
    
    Matching Stages:
    1. Exact match (case-insensitive, normalized)
    2. Fuzzy match (Levenshtein distance, handles typos)
    3. Token set match (handles word order and partial names)
    4. Partial match (substring with context)
    
    Features:
    - Team-based filtering to reduce false positives
    - Source tracking to prevent duplicate matches
    - Configurable thresholds
    - Detailed match metadata for debugging
    """
    
    def __init__(self):
        """Initialize the matcher with empty tracking set."""
        self.already_matched = set()  # Track (source, player_id) tuples
        self.match_stats = {
            'exact': 0,
            'fuzzy': 0,
            'token': 0,
            'partial': 0,
            'failed': 0
        }
    
    def match_player(
        self,
        pred_name: str,
        pred_team_code: str,
        fpl_players: List[dict],
        source_name: str = 'unknown',
        min_score: int = 60
    ) -> Optional[Dict]:
        """
        Find best FPL player match using multi-stage fuzzy matching.
        
        Args:
            pred_name: Predicted player name from scraper
            pred_team_code: Team code (e.g., 'MUN', 'MCI')
            fpl_players: List of FPL player dictionaries
            source_name: Source identifier for deduplication
            min_score: Minimum match score (0-100)
            
        Returns:
            dict with player_id, team_id, score, method if match found
            None if no good match found
        """
        if not pred_name or not pred_team_code:
            return None
        
        # Stage 0: Filter by team
        team_candidates = [
            p for p in fpl_players 
            if p.get('team_code') == pred_team_code
        ]
        
        if not team_candidates:
            return None
        
        # Stage 1: Exact match
        exact_match = self._exact_match(pred_name, team_candidates, source_name)
        if exact_match:
            self.match_stats['exact'] += 1
            return exact_match
        
        # Stage 2: Fuzzy ratio match (handles typos)
        fuzzy_match = self._fuzzy_match(pred_name, team_candidates, source_name, min_score=85)
        if fuzzy_match:
            self.match_stats['fuzzy'] += 1
            return fuzzy_match
        
        # Stage 3: Token set match (handles word order, partial names)
        token_match = self._token_match(pred_name, team_candidates, source_name, min_score=70)
        if token_match:
            self.match_stats['token'] += 1
            return token_match
        
        # Stage 4: Partial match (substring with penalty)
        partial_match = self._partial_match(pred_name, team_candidates, source_name, min_score=60)
        if partial_match:
            self.match_stats['partial'] += 1
            return partial_match
        
        self.match_stats['failed'] += 1
        return None
    
    def _exact_match(
        self, 
        pred_name: str, 
        candidates: List[dict], 
        source: str
    ) -> Optional[Dict]:
        """Stage 1: Exact match after normalization."""
        norm_pred = self._normalize(pred_name)
        
        for candidate in candidates:
            if self._is_already_matched(candidate['id'], source):
                continue
            
            norm_candidate = self._normalize(candidate['web_name'])
            
            if norm_pred == norm_candidate:
                self._mark_matched(candidate['id'], source)
                return self._create_result(candidate, 100, 'exact')
        
        return None
    
    def _fuzzy_match(
        self, 
        pred_name: str, 
        candidates: List[dict], 
        source: str,
        min_score: int = 85
    ) -> Optional[Dict]:
        """Stage 2: Fuzzy match using Levenshtein distance."""
        norm_pred = self._normalize(pred_name)
        
        # Build list of normalized candidate names with their original data
        candidate_names = []
        candidate_map = {}
        
        for candidate in candidates:
            if self._is_already_matched(candidate['id'], source):
                continue
            
            norm_name = self._normalize(candidate['web_name'])
            candidate_names.append(norm_name)
            candidate_map[norm_name] = candidate
        
        if not candidate_names:
            return None
        
        # Find best match
        result = process.extractOne(
            norm_pred,
            candidate_names,
            scorer=fuzz.ratio,
            score_cutoff=min_score
        )
        
        if result:
            matched_name, score, _ = result
            candidate = candidate_map[matched_name]
            self._mark_matched(candidate['id'], source)
            return self._create_result(candidate, score, 'fuzzy')
        
        return None
    
    def _token_match(
        self, 
        pred_name: str, 
        candidates: List[dict], 
        source: str,
        min_score: int = 70
    ) -> Optional[Dict]:
        """Stage 3: Token set match (handles word order and partial names)."""
        norm_pred = self._normalize(pred_name)
        
        # Build list of normalized candidate names
        candidate_names = []
        candidate_map = {}
        
        for candidate in candidates:
            if self._is_already_matched(candidate['id'], source):
                continue
            
            norm_name = self._normalize(candidate['web_name'])
            candidate_names.append(norm_name)
            candidate_map[norm_name] = candidate
        
        if not candidate_names:
            return None
        
        # Use token_set_ratio for better partial matching
        result = process.extractOne(
            norm_pred,
            candidate_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=min_score
        )
        
        if result:
            matched_name, score, _ = result
            candidate = candidate_map[matched_name]
            self._mark_matched(candidate['id'], source)
            return self._create_result(candidate, score, 'token')
        
        return None
    
    def _partial_match(
        self, 
        pred_name: str, 
        candidates: List[dict], 
        source: str,
        min_score: int = 60
    ) -> Optional[Dict]:
        """Stage 4: Partial match (last resort with lower threshold)."""
        norm_pred = self._normalize(pred_name)
        
        # Build list of normalized candidate names
        candidate_names = []
        candidate_map = {}
        
        for candidate in candidates:
            if self._is_already_matched(candidate['id'], source):
                continue
            
            norm_name = self._normalize(candidate['web_name'])
            candidate_names.append(norm_name)
            candidate_map[norm_name] = candidate
        
        if not candidate_names:
            return None
        
        # Use partial_ratio for substring matching
        result = process.extractOne(
            norm_pred,
            candidate_names,
            scorer=fuzz.partial_ratio,
            score_cutoff=min_score
        )
        
        if result:
            matched_name, score, _ = result
            candidate = candidate_map[matched_name]
            self._mark_matched(candidate['id'], source)
            return self._create_result(candidate, score, 'partial')
        
        return None
    
    def _normalize(self, name: str) -> str:
        """
        Normalize player name for matching.
        
        - Lowercase
        - Remove accents (é → e, ñ → n)
        - Remove punctuation
        - Trim whitespace
        - Handle common variations
        
        Args:
            name: Player name to normalize
            
        Returns:
            Normalized name string
        """
        if not name:
            return ''
        
        # Lowercase
        name = name.lower().strip()
        
        # Remove accents
        name = self._remove_accents(name)
        
        # Remove punctuation except spaces and hyphens (for names like "Son Heung-Min")
        name = re.sub(r'[^\w\s-]', '', name)
        
        # Normalize whitespace
        name = re.sub(r'\s+', ' ', name)
        
        # Apply common variations
        if name in COMMON_VARIATIONS:
            name = COMMON_VARIATIONS[name]
        
        return name.strip()
    
    @staticmethod
    def _remove_accents(text: str) -> str:
        """
        Remove accents from Unicode characters.
        
        Example: 'José' → 'Jose', 'Müller' → 'Muller'
        """
        # Normalize to NFD (decomposed form)
        nfd = unicodedata.normalize('NFD', text)
        # Filter out combining characters (accents)
        return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    
    def _is_already_matched(self, player_id: int, source_name: str) -> bool:
        """
        Check if player already matched from this source.
        
        Prevents duplicate matches within the same source.
        """
        return (source_name, player_id) in self.already_matched
    
    def _mark_matched(self, player_id: int, source_name: str):
        """Mark player as matched from this source."""
        self.already_matched.add((source_name, player_id))
    
    @staticmethod
    def _create_result(candidate: dict, score: float, method: str) -> Dict:
        """
        Create match result dictionary.
        
        Args:
            candidate: FPL player dictionary
            score: Match confidence score (0-100)
            method: Matching method used
            
        Returns:
            Dictionary with player_id, team_id, score, method
        """
        return {
            'player_id': candidate['id'],
            'team_id': candidate.get('team_id'),
            'score': score,
            'method': method,
            'web_name': candidate.get('web_name')  # For debugging
        }
    
    def get_stats(self) -> Dict:
        """Get matching statistics."""
        total = sum(self.match_stats.values())
        return {
            **self.match_stats,
            'total': total,
            'success_rate': (total - self.match_stats['failed']) / total * 100 if total > 0 else 0
        }
    
    def reset_stats(self):
        """Reset matching statistics."""
        self.match_stats = {
            'exact': 0,
            'fuzzy': 0,
            'token': 0,
            'partial': 0,
            'failed': 0
        }
    
    def reset_tracking(self):
        """Reset already_matched tracking (use between different sources aggregation)."""
        self.already_matched.clear()
