"""
Background scheduler for periodic tasks.

Handles scheduled updates of predicted lineups and other periodic tasks.
"""

import schedule
import time
import threading
from datetime import datetime
from typing import Optional

from fpl_predictor.scrapers.production_scraper import ProductionLineupScraper
from fpl_predictor.scrapers.ffscout_text_scraper import FFScoutTextScraper
from fpl_predictor.scrapers.aggregator import LineupAggregator
from fpl_predictor.data.database import get_connection
from fpl_predictor.data.repository import PredictedLineupRepository, PlayerRepository
from fpl_predictor.config import get_enabled_sources, get_source_weights


def get_next_gameweek() -> int:
    """
    Determine the next gameweek to scrape lineups for.
    
    Returns:
        Next gameweek number
    """
    # TODO: Implement logic to detect current/next GW from fixtures
    # For now, default to GW 22 (can be overridden)
    return 22


def update_predicted_lineups(gameweek: Optional[int] = None):
    """
    Scheduled job to update predicted lineups from multiple sources.
    
    Args:
        gameweek: Specific gameweek to scrape, or None to auto-detect next GW
    """
    if gameweek is None:
        gameweek = get_next_gameweek()
    
    print(f"[{datetime.now()}] Starting predicted lineups update for GW{gameweek}")
    
    rotowire_scraper = None
    ffscout_scraper = None
    
    try:
        # Get enabled sources and their weights
        enabled_sources = get_enabled_sources()
        source_weights = get_source_weights()
        
        print(f"[Scheduler] Enabled sources: {[s[0] for s in enabled_sources]}")
        print(f"[Scheduler] Weights: {source_weights}")
        
        # Dictionary to hold all source predictions
        all_source_predictions = {}
        all_metadata = {}
        
        # Scrape RotoWire (if enabled)
        if 'rotowire_enhanced' in source_weights:
            print(f"\n[Scheduler] === Scraping RotoWire + Premier Injuries ===")
            rotowire_scraper = ProductionLineupScraper(headless=True)
            roto_result = rotowire_scraper.scrape_all(gameweek)
            
            roto_predictions = roto_result['predictions']
            all_metadata['rotowire_enhanced'] = roto_result['metadata']
            
            # Skip per-source validation for raw scraper data
            # Validation will happen after matching to FPL players
            print(f"[Scheduler] RotoWire: {len(roto_predictions)} raw predictions")
            
            all_source_predictions['rotowire_enhanced'] = roto_predictions
        
        # Scrape FF Scout (if enabled)
        if 'ffscout' in source_weights:
            print(f"\n[Scheduler] === Scraping Fantasy Football Scout (Text Extraction) ===")
            ffscout_scraper = FFScoutTextScraper(headless=True)
            ff_result = ffscout_scraper.scrape_all(gameweek)
            
            ff_predictions = ff_result['predictions']
            all_metadata['ffscout'] = ff_result['metadata']
            
            # Skip per-source validation for raw scraper data
            # Validation will happen after matching to FPL players
            print(f"[Scheduler] FF Scout: {len(ff_predictions)} raw predictions")
            
            all_source_predictions['ffscout'] = ff_predictions
        
        # Check if we got any predictions
        if not all_source_predictions:
            print(f"[Scheduler] No predictions from any source for GW{gameweek}")
            return
        
        # Aggregate predictions using weighted averaging
        print(f"\n[Scheduler] === Aggregating Predictions with Weights ===")
        aggregator = LineupAggregator()
        predictions = aggregator.aggregate_weighted(all_source_predictions, source_weights, gameweek)
        
        if not predictions:
            print(f"[Scheduler] No predictions generated after aggregation for GW{gameweek}")
            return
        
        # Match to FPL player IDs
        print(f"\n[Scheduler] === Matching to FPL Players ===")
        conn = get_connection()
        player_repo = PlayerRepository(conn)
        fpl_players = player_repo.get_all(limit=1000)
        
        # Convert to format needed by aggregator
        fpl_players_formatted = []
        for p in fpl_players:
            fpl_players_formatted.append({
                'id': p['id'],
                'web_name': p['web_name'],
                'first_name': p.get('first_name', ''),
                'second_name': p.get('second_name', ''),
                'team_id': p['team_id'],
                'team_code': p.get('team_name', '')
            })
        
        matched_predictions = aggregator.match_to_fpl_players(predictions, fpl_players_formatted)
        
        # Deduplicate predictions that have the same player_id but came from different sources
        print(f"\n[Scheduler] === Deduplicating by Player ID ===")
        matched_predictions = aggregator.deduplicate_by_player_id(matched_predictions, source_weights)
        
        # Separate matched and unmatched
        matched_only = [p for p in matched_predictions if p.get('matched')]
        unmatched = [p for p in matched_predictions if not p.get('matched')]
        
        if not matched_only:
            print(f"[Scheduler] No predictions could be matched to FPL players")
            return
        
        # Final validation after aggregation
        print(f"\n[Scheduler] === Final Lineup Validation ===")
        try:
            from fpl_predictor.engine.lineup_validator import validate_all_predictions
            validated_predictions = validate_all_predictions(matched_only)
            print(f"[Scheduler] ✓ Validation complete: {len(validated_predictions)} predictions")
        except Exception as val_err:
            print(f"[Scheduler] ⚠️ Validation failed: {val_err}")
            import traceback
            traceback.print_exc()
            validated_predictions = matched_only
        validation_notes = {}
        
        # Store in database
        print(f"\n[Scheduler] === Saving to Database ===")
        lineup_repo = PredictedLineupRepository(conn)
        
        # Save matched predictions
        count = lineup_repo.upsert_predictions(validated_predictions)
        print(f"[Scheduler] ✓ Saved {count} matched predictions")
        
        # Save unmatched predictions to cache
        if unmatched:
            # Track individual unmatched players for statistics
            for u in unmatched:
                try:
                    lineup_repo.upsert_unmatched_player(
                        scraped_name=u['player_name'],
                        team_code=u['team_code'],
                        position_code=u.get('position_code'),
                        source='multi_source'
                    )
                except Exception as e:
                    pass  # Silently ignore errors in tracking
            
            # Save full unmatched predictions for this gameweek
            lineup_repo.save_unmatched_predictions(gameweek, unmatched)
            print(f"[Scheduler] ✓ Saved {len(unmatched)} unmatched predictions")
        
        # Save validation notes (skip - not needed)
        # validation_notes is empty anyway
        
        # Explicitly commit all changes
        conn.commit()
        print(f"[Scheduler] ✓ Database transaction committed")
        
        # Print summary
        print(f"\n{'='*80}")
        print(f"PREDICTION UPDATE COMPLETE - GW{gameweek}")
        print(f"{'='*80}")
        print(f"Sources: {len(all_source_predictions)}")
        for source_name, meta in all_metadata.items():
            weight = source_weights.get(source_name, 0)
            print(f"  - {source_name} (weight: {weight*100:.0f}%): {meta.get('total_predictions', 0)} raw predictions")
        print(f"Aggregated: {len(predictions)} unique players")
        print(f"Matched: {len(matched_only)} ({len(matched_only)/len(predictions)*100:.1f}%)")
        print(f"Unmatched: {len(unmatched)}")
        print(f"Saved to DB: {count} predictions")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"[Scheduler] ✗ Failed to update predicted lineups: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Close database connection and reset global connection
        try:
            if 'conn' in locals() and conn:
                conn.close()
                print("[Scheduler] Database connection closed")
                # Reset global connection so next access gets fresh connection
                from fpl_predictor.data.database import reset_connection
                reset_connection()
                print("[Scheduler] Global connection reset")
        except Exception as e:
            print(f"[Scheduler] Warning: Error closing connection: {e}")
        
        # Cleanup scrapers
        if rotowire_scraper:
            try:
                rotowire_scraper.driver.quit()
            except:
                pass
        if ffscout_scraper:
            try:
                ffscout_scraper.driver.quit()
            except:
                pass


def start_scheduler():
    """
    Start the background scheduler.
    
    Runs scheduled tasks in a daemon thread.
    """
    # Schedule lineup updates every 6 hours
    schedule.every(6).hours.do(lambda: update_predicted_lineups())
    
    # Also run once at 6 AM daily (before most gameweeks)
    schedule.every().day.at("06:00").do(lambda: update_predicted_lineups())
    
    def run_scheduler():
        """Background thread that runs scheduled tasks."""
        print("[Scheduler] Background scheduler started")
        print("[Scheduler] - Lineup updates: Every 6 hours + Daily at 6:00 AM")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    # Start scheduler in daemon thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("[Scheduler] Predicted lineups scheduler is running")
    
    return scheduler_thread


def run_immediate_update(gameweek: int):
    """
    Run an immediate lineup update (for testing or manual refresh).
    
    Args:
        gameweek: Gameweek to update
    """
    print(f"[Scheduler] Running immediate update for GW{gameweek}")
    update_predicted_lineups(gameweek)


# For use in production server
_scheduler_thread = None

def initialize_scheduler():
    """Initialize the global scheduler (call once at startup)."""
    global _scheduler_thread
    if _scheduler_thread is None:
        _scheduler_thread = start_scheduler()
    return _scheduler_thread
