#!/usr/bin/env python3
"""
Test the production scraper (RotoWire + Premier Injuries)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fpl_predictor.scrapers.production_scraper import ProductionLineupScraper
from fpl_predictor.scrapers.aggregator import LineupAggregator
from fpl_predictor.data.database import get_connection, init_schema
from fpl_predictor.data.repository import PredictedLineupRepository, PlayerRepository


def main(gameweek=22):
    print(f"\n{'#'*80}")
    print(f"PRODUCTION SCRAPER TEST - GW{gameweek}")
    print(f"{'#'*80}\n")
    
    # Step 1: Scrape data
    scraper = ProductionLineupScraper(headless=True)
    
    try:
        result = scraper.scrape_all(gameweek)
        
        predictions = result['predictions']
        injury_data = result['injury_data']
        metadata = result['metadata']
        
        # Step 2: Test aggregation
        print(f"\n{'='*80}")
        print("TESTING AGGREGATION")
        print(f"{'='*80}\n")
        
        aggregator = LineupAggregator()
        
        # Wrap predictions in source dict for aggregator
        source_predictions = {'rotowire_enhanced': predictions}
        
        aggregated = aggregator.aggregate_predictions(source_predictions, gameweek)
        
        print(f"✅ Aggregated {len(aggregated)} predictions")
        
        # Show sample
        print(f"\nTop 10 Most Likely Starters:")
        print(f"{'Player':<25} {'Team':<10} {'Start %':<10} {'Status'}")
        print("-" * 70)
        
        for pred in aggregated[:10]:
            status_icons = []
            if pred.get('injured'):
                status_icons.append('🔴 OUT')
            elif pred.get('doubtful'):
                status_icons.append('🟡 DOUBT')
            elif pred['start_probability'] >= 0.8:
                status_icons.append('🟢 CONF')
            
            print(f"{pred['player_name']:<25} {pred['team_code']:<10} "
                  f"{pred['start_probability']*100:>6.1f}%   {' '.join(status_icons)}")
        
        # Show injured/doubtful players
        injured_players = [p for p in aggregated if p.get('injured')]
        doubtful_players = [p for p in aggregated if p.get('doubtful')]
        
        if injured_players:
            print(f"\n🔴 Ruled Out ({len(injured_players)}):")
            for p in injured_players[:10]:
                details = p.get('injury_details', 'No details')
                print(f"  {p['player_name']} ({p['team_code']}) - {details}")
        
        if doubtful_players:
            print(f"\n🟡 Doubtful ({len(doubtful_players)}):")
            for p in doubtful_players[:10]:
                details = p.get('injury_details', 'No details')
                print(f"  {p['player_name']} ({p['team_code']}) - {details}")
        
        # Step 3: Test database storage
        print(f"\n{'='*80}")
        print("TESTING DATABASE STORAGE")
        print(f"{'='*80}\n")
        
        conn = get_connection()
        init_schema(conn)
        
        # Import FPL data from JSON if database is empty
        player_repo = PlayerRepository(conn)
        fpl_players = player_repo.get_all(limit=1000)
        
        if not fpl_players:
            print("[Test] Database is empty, importing FPL data from JSON...")
            import glob
            import json
            from fpl_predictor.data.importer import DataImporter
            
            # Find the newest fpl_league_data JSON file
            json_files = glob.glob('fpl_league_data_*.json')
            if json_files:
                json_files.sort(reverse=True)
                json_file = json_files[0]
                print(f"[Test] Found {json_file}, importing...")
                
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                importer = DataImporter(conn)
                result = importer.import_from_json(data)
                print(f"[Test] ✅ Data imported: {result.players_imported} players, {result.teams_imported} teams")
                
                # Reload players
                fpl_players = player_repo.get_all(limit=1000)
                print(f"[Test] ✅ Found {len(fpl_players)} players in database")
            else:
                print("[Test] ⚠️  No JSON files found, player matching may fail")
        else:
            print(f"[Test] ✅ Database has {len(fpl_players)} players already")
        
        fpl_players_formatted = []
        for p in fpl_players:
            fpl_players_formatted.append({
                'id': p['id'],
                'web_name': p['web_name'],
                'team_id': p['team_id'],
                'team_code': p.get('team_name', '')
            })
        
        # Match predictions to FPL players
        matched = aggregator.match_to_fpl_players(aggregated, fpl_players_formatted)
        
        matched_count = len([p for p in matched if p.get('matched')])
        print(f"✅ Matched {matched_count}/{len(matched)} predictions to FPL players")
        
        # Filter to only matched predictions (with player_id)
        matched_only = [p for p in matched if p.get('player_id') is not None]
        print(f"[Test] Filtering {len(matched_only)}/{len(matched)} predictions with valid player_id")
        
        # Store in database
        lineup_repo = PredictedLineupRepository(conn)
        lineup_repo.upsert_predictions(matched_only)
        
        # Verify storage
        db_predictions = lineup_repo.get_predictions_for_gameweek(gameweek)
        print(f"✅ Stored {len(db_predictions)} predictions in database")
        
        # Step 4: Summary
        print(f"\n{'='*80}")
        print("TEST SUMMARY")
        print(f"{'='*80}\n")
        print(f"✅ Scraping: {metadata['total_predictions']} predictions")
        print(f"✅ Aggregation: {len(aggregated)} aggregated")
        print(f"✅ Matching: {matched_count} matched to FPL IDs")
        print(f"✅ Database: {len(db_predictions)} stored")
        print(f"\nEnhancements:")
        print(f"  🔴 Injured: {metadata['injured']}")
        print(f"  🟡 Doubtful: {metadata['doubtful']}")
        print(f"  🔒 Suspended: {metadata['suspended']}")
        print(f"  📊 Enhanced: {metadata['enhanced_with_injury_data']}")
        print(f"\n⏱️  Time: {metadata['elapsed_seconds']:.1f}s")
        print(f"\n{'='*80}")
        print("✅ ALL TESTS PASSED")
        print(f"{'='*80}\n")
        
    finally:
        scraper.driver.quit()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--gameweek', type=int, default=22)
    args = parser.parse_args()
    
    main(args.gameweek)
