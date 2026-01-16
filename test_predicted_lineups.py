"""
Test script for Predicted Lineups feature.

Tests scraping, aggregation, database storage, and gameweek consistency.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fpl_predictor.scrapers.lineup_scraper import LineupScraper
from fpl_predictor.scrapers.aggregator import LineupAggregator
from fpl_predictor.data.database import get_connection
from fpl_predictor.data.repository import PredictedLineupRepository, PlayerRepository
import json


def test_scraper(gameweek=22, use_mock=False):
    """Test the lineup scraper for a specific gameweek."""
    print(f"\n{'='*80}")
    print(f"TEST 1: Scraping Predicted Lineups for GW{gameweek}")
    if use_mock:
        print("(Using MOCK DATA for testing)")
    print(f"{'='*80}\n")
    
    if use_mock:
        from fpl_predictor.scrapers.mock_scraper import MockLineupScraper
        scraper = MockLineupScraper()
        print(f"[Test] Generating mock predictions for GW{gameweek}...")
        raw_data = scraper.scrape_all_sources(gameweek)
    else:
        scraper = LineupScraper(headless=True)
        
        try:
            print(f"[Test] Starting scrape for GW{gameweek}...")
            raw_data = scraper.scrape_all_sources(gameweek)
        finally:
            scraper.driver.quit()
    
    print(f"\n[Test] Scraping Results:")
    print(f"{'Source':<20} {'Predictions':<15} {'Status'}")
    print("-" * 60)
    
    total_predictions = 0
    for source_name, predictions in raw_data.items():
        count = len(predictions)
        total_predictions += count
        status = "✓ Success" if count > 0 else "✗ Failed"
        print(f"{source_name:<20} {count:<15} {status}")
    
    print(f"\n[Test] Total predictions: {total_predictions}")
    
    # Check for gameweek consistency
    print(f"\n[Test] Checking gameweek consistency...")
    gw_mismatches = []
    for source_name, predictions in raw_data.items():
        for pred in predictions:
            if pred.get('gameweek') != gameweek:
                gw_mismatches.append({
                    'source': source_name,
                    'player': pred.get('player_name'),
                    'expected_gw': gameweek,
                    'actual_gw': pred.get('gameweek')
                })
    
    if gw_mismatches:
        print(f"⚠️  WARNING: Found {len(gw_mismatches)} gameweek mismatches:")
        for mm in gw_mismatches[:5]:
            print(f"   - {mm['source']}: {mm['player']} (expected GW{mm['expected_gw']}, got GW{mm['actual_gw']})")
    else:
        print("✓ All predictions have correct gameweek")
    
    # Sample some predictions
    print(f"\n[Test] Sample predictions from each source:")
    for source_name, predictions in raw_data.items():
        if predictions:
            sample = predictions[0]
            print(f"\n  {source_name}:")
            print(f"    Player: {sample.get('player_name')}")
            print(f"    Team: {sample.get('team_name')}")
            print(f"    GW: {sample.get('gameweek')}")
            print(f"    Starting: {sample.get('starting')}")
            print(f"    Injured: {sample.get('injured')}")
            print(f"    Doubtful: {sample.get('doubtful')}")
    
    return raw_data


def test_aggregator(raw_data, gameweek=22):
    """Test the aggregator."""
    print(f"\n{'='*80}")
    print(f"TEST 2: Aggregating Predictions")
    print(f"{'='*80}\n")
    
    aggregator = LineupAggregator()
    
    print(f"[Test] Aggregating predictions from {len(raw_data)} sources...")
    aggregated = aggregator.aggregate_predictions(raw_data, gameweek)
    
    print(f"\n[Test] Aggregation Results:")
    print(f"  Total players with predictions: {len(aggregated)}")
    
    # Analyze probability distribution
    high_confidence = [p for p in aggregated if p['start_probability'] >= 0.8]
    medium_confidence = [p for p in aggregated if 0.3 <= p['start_probability'] < 0.8]
    low_confidence = [p for p in aggregated if p['start_probability'] < 0.3]
    
    print(f"  High confidence (≥80%): {len(high_confidence)}")
    print(f"  Medium confidence (30-80%): {len(medium_confidence)}")
    print(f"  Low confidence (<30%): {len(low_confidence)}")
    
    # Check for injured/suspended players
    injured = [p for p in aggregated if p['injured']]
    suspended = [p for p in aggregated if p['suspended']]
    doubtful = [p for p in aggregated if p['doubtful']]
    
    print(f"\n[Test] Player Status:")
    print(f"  Injured: {len(injured)}")
    print(f"  Suspended: {len(suspended)}")
    print(f"  Doubtful: {len(doubtful)}")
    
    # Show top 10 most likely starters
    print(f"\n[Test] Top 10 Most Likely Starters:")
    print(f"{'Player':<25} {'Team':<10} {'Start Prob':<12} {'Sources'}")
    print("-" * 70)
    
    top_10 = sorted(aggregated, key=lambda x: x['start_probability'], reverse=True)[:10]
    for p in top_10:
        print(f"{p['player_name']:<25} {p['team_code']:<10} {p['start_probability']*100:>6.1f}% {p['sources_count']:>10}")
    
    # Show injured/doubtful players
    if injured or doubtful:
        print(f"\n[Test] Sample Injured/Doubtful Players:")
        for p in (injured + doubtful)[:5]:
            status = []
            if p['injured']:
                status.append('Injured')
            if p['doubtful']:
                status.append('Doubtful')
            print(f"  {p['player_name']} ({p['team_code']}): {', '.join(status)}")
            if p['injury_details']:
                print(f"    Details: {p['injury_details'][:100]}")
    
    return aggregated


def test_player_matching(aggregated):
    """Test matching aggregated predictions to FPL player IDs."""
    print(f"\n{'='*80}")
    print(f"TEST 3: Matching to FPL Player IDs")
    print(f"{'='*80}\n")
    
    conn = get_connection()
    player_repo = PlayerRepository(conn)
    
    print(f"[Test] Fetching FPL players from database...")
    fpl_players = player_repo.get_all(limit=1000)
    print(f"  Found {len(fpl_players)} FPL players in database")
    
    # Convert to format needed by aggregator
    fpl_players_formatted = []
    for p in fpl_players:
        fpl_players_formatted.append({
            'id': p['id'],
            'web_name': p['web_name'],
            'team_id': p['team_id'],
            'team_code': p.get('team_name', '')
        })
    
    aggregator = LineupAggregator()
    print(f"\n[Test] Matching {len(aggregated)} predictions to FPL players...")
    matched = aggregator.match_to_fpl_players(aggregated, fpl_players_formatted)
    
    # Analyze matching results
    matched_count = len([p for p in matched if p.get('matched')])
    unmatched_count = len([p for p in matched if not p.get('matched')])
    
    print(f"\n[Test] Matching Results:")
    if len(matched) > 0:
        print(f"  Matched: {matched_count} ({matched_count/len(matched)*100:.1f}%)")
        print(f"  Unmatched: {unmatched_count} ({unmatched_count/len(matched)*100:.1f}%)")
    else:
        print(f"  No predictions to match (scrapers returned 0 results)")
    
    # Show sample matched predictions
    print(f"\n[Test] Sample Matched Predictions:")
    print(f"{'Predicted Name':<25} {'FPL ID':<10} {'Team':<10} {'Start Prob'}")
    print("-" * 70)
    
    matched_samples = [p for p in matched if p.get('matched')][:5]
    for p in matched_samples:
        print(f"{p['player_name']:<25} {p['player_id']:<10} {p['team_code']:<10} {p['start_probability']*100:>6.1f}%")
    
    # Show sample unmatched (for debugging)
    unmatched_samples = [p for p in matched if not p.get('matched')][:5]
    if unmatched_samples:
        print(f"\n[Test] Sample Unmatched Predictions (need manual review):")
        for p in unmatched_samples:
            print(f"  {p['player_name']} ({p['team_code']}) - {p['start_probability']*100:.1f}%")
    
    return matched


def test_database_storage(matched_predictions, gameweek=22):
    """Test storing predictions in database."""
    print(f"\n{'='*80}")
    print(f"TEST 4: Database Storage")
    print(f"{'='*80}\n")
    
    conn = get_connection()
    lineup_repo = PredictedLineupRepository(conn)
    
    # Filter to only matched predictions
    valid_predictions = [p for p in matched_predictions if p.get('matched')]
    
    if not valid_predictions:
        print("⚠️  No valid predictions to store")
        return
    
    print(f"[Test] Storing {len(valid_predictions)} predictions in database...")
    count = lineup_repo.upsert_predictions(valid_predictions)
    print(f"✓ Stored {count} predictions")
    
    # Retrieve and verify
    print(f"\n[Test] Retrieving predictions from database...")
    retrieved = lineup_repo.get_predictions_for_gameweek(gameweek)
    print(f"✓ Retrieved {len(retrieved)} predictions")
    
    # Verify gameweek consistency
    print(f"\n[Test] Verifying gameweek consistency in database...")
    gw_errors = [p for p in retrieved if p.get('gameweek') != gameweek]
    if gw_errors:
        print(f"⚠️  Found {len(gw_errors)} records with wrong gameweek")
    else:
        print(f"✓ All {len(retrieved)} records have correct gameweek (GW{gameweek})")
    
    # Show sample stored data
    print(f"\n[Test] Sample Stored Predictions:")
    print(f"{'Player':<25} {'Team':<10} {'GW':<5} {'Start %':<10} {'Status'}")
    print("-" * 75)
    
    for p in retrieved[:10]:
        status = []
        if p.get('injured'):
            status.append('INJ')
        if p.get('suspended'):
            status.append('SUS')
        if p.get('doubtful'):
            status.append('DOUBT')
        status_str = ','.join(status) if status else 'OK'
        
        print(f"{p['web_name']:<25} {p.get('team_name', 'N/A'):<10} {p['gameweek']:<5} {p['start_probability']*100:>6.1f}% {status_str:<10}")
    
    # Test specific player lookup
    if retrieved:
        test_player = retrieved[0]
        player_id = test_player['player_id']
        
        print(f"\n[Test] Testing player-specific lookup (Player ID: {player_id})...")
        prob = lineup_repo.get_player_lineup_probability(player_id, gameweek)
        print(f"  {test_player['web_name']}: {prob*100:.1f}% start probability")
    
    # Test unavailable players lookup
    print(f"\n[Test] Testing unavailable players lookup...")
    unavailable = lineup_repo.get_unavailable_players(gameweek)
    print(f"  Found {len(unavailable)} unavailable players")
    
    if unavailable:
        print(f"\n  Sample Unavailable Players:")
        for p in unavailable[:5]:
            reasons = []
            if p.get('injured'):
                reasons.append('Injured')
            if p.get('suspended'):
                reasons.append('Suspended')
            if p.get('doubtful'):
                reasons.append('Doubtful')
            print(f"    {p['web_name']} ({p.get('team_name')}): {', '.join(reasons)}")


def test_api_endpoints(gameweek=22):
    """Test that API endpoints work."""
    print(f"\n{'='*80}")
    print(f"TEST 5: API Endpoints (Manual Test)")
    print(f"{'='*80}\n")
    
    print("[Test] API endpoints to test manually:")
    print(f"  1. GET /api/predicted-lineups/{gameweek}")
    print(f"  2. POST /api/predicted-lineups/refresh/{gameweek}")
    print(f"  3. GET /api/predicted-lineups/unavailable/{gameweek}")
    print("\n[Test] Start the server and test these endpoints:")
    print("  python run_server.py")
    print(f"  curl http://localhost:5000/api/predicted-lineups/{gameweek}")


def main():
    """Run all tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Predicted Lineups feature')
    parser.add_argument('--gameweek', '-g', type=int, default=22, help='Gameweek to test (default: 22)')
    parser.add_argument('--skip-scraping', action='store_true', help='Skip scraping test (use existing data)')
    parser.add_argument('--mock', action='store_true', help='Use mock data instead of real scraping')
    args = parser.parse_args()
    
    gameweek = args.gameweek
    
    print(f"\n{'#'*80}")
    print(f"# PREDICTED LINEUPS SYSTEM TEST - GW{gameweek}")
    print(f"{'#'*80}")
    
    try:
        # Test 1: Scraping
        if not args.skip_scraping:
            raw_data = test_scraper(gameweek, use_mock=args.mock)
            
            # Test 2: Aggregation
            aggregated = test_aggregator(raw_data, gameweek)
            
            # Test 3: Player Matching
            matched = test_player_matching(aggregated)
            
            # Test 4: Database Storage
            test_database_storage(matched, gameweek)
        else:
            print("\n[Test] Skipping scraping, loading from database...")
            conn = get_connection()
            lineup_repo = PredictedLineupRepository(conn)
            retrieved = lineup_repo.get_predictions_for_gameweek(gameweek)
            
            if retrieved:
                print(f"✓ Found {len(retrieved)} existing predictions for GW{gameweek}")
            else:
                print(f"⚠️  No predictions found in database for GW{gameweek}")
                print("   Run without --skip-scraping to fetch new data")
        
        # Test 5: API Info
        test_api_endpoints(gameweek)
        
        print(f"\n{'='*80}")
        print("✓ ALL TESTS COMPLETED")
        print(f"{'='*80}\n")
        
    except KeyboardInterrupt:
        print("\n\n[Test] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
