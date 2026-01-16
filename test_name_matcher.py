"""
Unit tests for SmartPlayerMatcher.

Tests name matching logic, fuzzy matching, deduplication, and edge cases.
"""

import unittest
from fpl_predictor.utils.name_matcher import SmartPlayerMatcher


class TestSmartPlayerMatcher(unittest.TestCase):
    """Test cases for SmartPlayerMatcher class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.matcher = SmartPlayerMatcher()
        
        # Mock FPL players database
        self.fpl_players = [
            # Manchester United
            {'id': 1, 'web_name': 'Bruno Fernandes', 'team_id': 1, 'team_code': 'MUN'},
            {'id': 2, 'web_name': 'Casemiro', 'team_id': 1, 'team_code': 'MUN'},
            {'id': 3, 'web_name': 'Rashford', 'team_id': 1, 'team_code': 'MUN'},
            {'id': 4, 'web_name': 'Martínez', 'team_id': 1, 'team_code': 'MUN'},  # Lisandro
            
            # Newcastle
            {'id': 5, 'web_name': 'Bruno Guimarães', 'team_id': 2, 'team_code': 'NEW'},
            {'id': 6, 'web_name': 'Alexander Isak', 'team_id': 2, 'team_code': 'NEW'},
            
            # Liverpool
            {'id': 7, 'web_name': 'Mohamed Salah', 'team_id': 3, 'team_code': 'LIV'},
            {'id': 8, 'web_name': 'Diogo Jota', 'team_id': 3, 'team_code': 'LIV'},
            {'id': 9, 'web_name': 'Virgil van Dijk', 'team_id': 3, 'team_code': 'LIV'},
            
            # Tottenham
            {'id': 10, 'web_name': 'Son Heung-Min', 'team_id': 4, 'team_code': 'TOT'},
            
            # Arsenal (multiple Gabriels)
            {'id': 11, 'web_name': 'Gabriel Jesus', 'team_id': 5, 'team_code': 'ARS'},
            {'id': 12, 'web_name': 'Gabriel Martinelli', 'team_id': 5, 'team_code': 'ARS'},
            {'id': 13, 'web_name': 'Gabriel', 'team_id': 5, 'team_code': 'ARS'},  # Magalhães
            
            # Aston Villa
            {'id': 14, 'web_name': 'Emiliano Martínez', 'team_id': 6, 'team_code': 'AVL'},
        ]
    
    def test_exact_match(self):
        """Test exact name matching."""
        result = self.matcher.match_player(
            pred_name='Bruno Fernandes',
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 1)
        self.assertEqual(result['method'], 'exact')
        self.assertEqual(result['score'], 100)
    
    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        result = self.matcher.match_player(
            pred_name='bruno fernandes',  # lowercase
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 1)
        self.assertEqual(result['method'], 'exact')
    
    def test_accent_removal(self):
        """Test accent handling (Martínez → Martinez)."""
        result = self.matcher.match_player(
            pred_name='Martinez',  # No accent
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 4)  # Lisandro Martinez
    
    def test_fuzzy_match_typo(self):
        """Test fuzzy matching with typo."""
        result = self.matcher.match_player(
            pred_name='Cazemiro',  # Typo: should match Casemiro
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 2)
        self.assertIn(result['method'], ['fuzzy', 'token'])  # Could be either
        self.assertGreaterEqual(result['score'], 60)
    
    def test_partial_name_match(self):
        """Test partial name matching (first name only)."""
        result = self.matcher.match_player(
            pred_name='Rashford',
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 3)
    
    def test_nickname_match(self):
        """Test nickname/short name matching."""
        result = self.matcher.match_player(
            pred_name='Son',  # Short for Son Heung-Min
            pred_team_code='TOT',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 10)
    
    def test_multiple_bruno_different_teams(self):
        """Test disambiguation of same name on different teams."""
        # Bruno Fernandes (MUN)
        result1 = self.matcher.match_player(
            pred_name='Bruno',
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1['player_id'], 1)
        
        # Bruno Guimarães (NEW)
        result2 = self.matcher.match_player(
            pred_name='Bruno',
            pred_team_code='NEW',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result2)
        self.assertEqual(result2['player_id'], 5)
    
    def test_multiple_martinez_different_teams(self):
        """Test disambiguation of Martinez on different teams."""
        # Lisandro Martinez (MUN)
        result1 = self.matcher.match_player(
            pred_name='Martinez',
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1['player_id'], 4)
        
        # Emiliano Martinez (AVL)
        result2 = self.matcher.match_player(
            pred_name='Martinez',
            pred_team_code='AVL',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result2)
        self.assertEqual(result2['player_id'], 14)
    
    def test_multiple_gabriels_with_context(self):
        """Test disambiguating multiple Gabriels by full name."""
        # Gabriel Jesus
        result1 = self.matcher.match_player(
            pred_name='Gabriel Jesus',
            pred_team_code='ARS',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1['player_id'], 11)
        
        # Gabriel Martinelli
        result2 = self.matcher.match_player(
            pred_name='Martinelli',
            pred_team_code='ARS',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result2)
        self.assertEqual(result2['player_id'], 12)
        
        # Gabriel (Magalhães)
        result3 = self.matcher.match_player(
            pred_name='Gabriel',
            pred_team_code='ARS',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result3)
        # Should match one of them - exact "Gabriel" should match the player named just "Gabriel"
        self.assertEqual(result3['player_id'], 13)
    
    def test_no_match_wrong_team(self):
        """Test no match when team doesn't match."""
        result = self.matcher.match_player(
            pred_name='Salah',
            pred_team_code='MUN',  # Wrong team (Salah is LIV)
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNone(result)
    
    def test_no_match_nonexistent_player(self):
        """Test no match for player not in database."""
        result = self.matcher.match_player(
            pred_name='Lionel Messi',
            pred_team_code='MUN',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNone(result)
    
    def test_prevents_duplicate_from_same_source(self):
        """Test that same player can't be matched twice from same source."""
        # First match
        result1 = self.matcher.match_player(
            pred_name='Salah',
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='rotowire'
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1['player_id'], 7)
        
        # Try to match same player again from same source
        result2 = self.matcher.match_player(
            pred_name='Mohamed Salah',
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='rotowire'  # Same source
        )
        
        # Should not match because already matched from this source
        self.assertIsNone(result2)
    
    def test_allows_duplicate_from_different_source(self):
        """Test that same player CAN be matched from different sources."""
        # Match from source 1
        result1 = self.matcher.match_player(
            pred_name='Salah',
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='rotowire'
        )
        self.assertIsNotNone(result1)
        self.assertEqual(result1['player_id'], 7)
        
        # Match same player from different source
        result2 = self.matcher.match_player(
            pred_name='Salah',
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='ffscout'  # Different source
        )
        
        # Should match because different source
        self.assertIsNotNone(result2)
        self.assertEqual(result2['player_id'], 7)
    
    def test_token_match_word_order(self):
        """Test token matching handles different word orders."""
        result = self.matcher.match_player(
            pred_name='van Dijk Virgil',  # Reversed order
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 9)
    
    def test_stats_tracking(self):
        """Test that matching statistics are tracked."""
        self.matcher.reset_stats()
        
        # Exact match
        self.matcher.match_player('Salah', 'LIV', self.fpl_players, 'test1')
        
        # Fuzzy match
        self.matcher.match_player('Cazemiro', 'MUN', self.fpl_players, 'test2')
        
        # Failed match
        self.matcher.match_player('Messi', 'MUN', self.fpl_players, 'test3')
        
        stats = self.matcher.get_stats()
        self.assertGreaterEqual(stats['exact'] + stats['fuzzy'] + stats['token'] + stats['partial'], 2)
        self.assertGreaterEqual(stats['failed'], 1)
        self.assertEqual(stats['total'], 3)
    
    def test_reset_tracking(self):
        """Test reset tracking clears already_matched set."""
        # Match a player
        self.matcher.match_player('Salah', 'LIV', self.fpl_players, 'source1')
        
        # Try to match again (should fail)
        result1 = self.matcher.match_player('Salah', 'LIV', self.fpl_players, 'source1')
        self.assertIsNone(result1)
        
        # Reset tracking
        self.matcher.reset_tracking()
        
        # Should be able to match again
        result2 = self.matcher.match_player('Salah', 'LIV', self.fpl_players, 'source1')
        self.assertIsNotNone(result2)
        self.assertEqual(result2['player_id'], 7)
    
    def test_normalization(self):
        """Test name normalization function."""
        # Test via matching
        test_cases = [
            ('BRUNO FERNANDES', 'MUN', 1),  # Uppercase
            ('  Bruno Fernandes  ', 'MUN', 1),  # Extra spaces
            ('Bruno  Fernandes', 'MUN', 1),  # Multiple spaces
            ('Bruno-Fernandes', 'MUN', 1),  # Hyphen
        ]
        
        for name, team, expected_id in test_cases:
            self.matcher.reset_tracking()
            result = self.matcher.match_player(name, team, self.fpl_players, f'test_{name}')
            self.assertIsNotNone(result, f"Failed to match: {name}")
            self.assertEqual(result['player_id'], expected_id)
    
    def test_common_variations(self):
        """Test common name variations from COMMON_VARIATIONS dict."""
        # Jota → Diogo Jota
        result = self.matcher.match_player(
            pred_name='Jota',
            pred_team_code='LIV',
            fpl_players=self.fpl_players,
            source_name='test'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['player_id'], 8)


def run_tests():
    """Run all tests and print results."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestSmartPlayerMatcher)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
