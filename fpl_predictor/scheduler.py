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
from fpl_predictor.scrapers.aggregator import LineupAggregator
from fpl_predictor.data.database import get_connection
from fpl_predictor.data.repository import PredictedLineupRepository, PlayerRepository


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
    Scheduled job to update predicted lineups.
    
    Args:
        gameweek: Specific gameweek to scrape, or None to auto-detect next GW
    """
    if gameweek is None:
        gameweek = get_next_gameweek()
    
    print(f"[{datetime.now()}] Starting predicted lineups update for GW{gameweek}")
    
    scraper = None
    try:
        # Scrape all sources (RotoWire + Premier Injuries)
        scraper = ProductionLineupScraper(headless=True)
        result = scraper.scrape_all(gameweek)
        
        predictions_raw = result['predictions']
        metadata = result['metadata']
        
        # Aggregate predictions
        aggregator = LineupAggregator()
        source_predictions = {'rotowire_enhanced': predictions_raw}
        predictions = aggregator.aggregate_predictions(source_predictions, gameweek)
        
        if not predictions:
            print(f"[Scheduler] No predictions generated for GW{gameweek}")
            return
        
        # Match to FPL player IDs
        conn = get_connection()
        player_repo = PlayerRepository(conn)
        fpl_players = player_repo.get_all(limit=1000)
        
        # Convert to format needed by aggregator
        fpl_players_formatted = []
        for p in fpl_players:
            fpl_players_formatted.append({
                'id': p['id'],
                'web_name': p['web_name'],
                'team_id': p['team_id'],
                'team_code': p.get('team_name', '')
            })
        
        matched_predictions = aggregator.match_to_fpl_players(predictions, fpl_players_formatted)
        
        # Filter to only matched predictions
        valid_predictions = [p for p in matched_predictions if p.get('matched')]
        
        if not valid_predictions:
            print(f"[Scheduler] No predictions could be matched to FPL players")
            return
        
        # Validate lineups - ensure exactly 11 players per team with smart position handling
        try:
            from fpl_predictor.engine.lineup_validator import validate_all_predictions
            print(f"[Scheduler] Validating lineups...")
            validated_predictions = validate_all_predictions(valid_predictions)
            print(f"[Scheduler] ✓ Lineup validation complete")
        except Exception as val_err:
            print(f"[Scheduler] ⚠️ Validation failed: {val_err}")
            import traceback
            traceback.print_exc()
            validated_predictions = valid_predictions  # Use unvalidated if validation fails
        
        # Store in database
        lineup_repo = PredictedLineupRepository(conn)
        count = lineup_repo.upsert_predictions(validated_predictions)
        
        print(f"[Scheduler] ✓ Updated {count} player lineup predictions for GW{gameweek}")
        print(f"[Scheduler] Matched: {len(valid_predictions)}, Unmatched: {len(predictions) - len(valid_predictions)}")
        print(f"[Scheduler] Injured: {metadata['injured']}, Doubtful: {metadata['doubtful']}, Suspended: {metadata['suspended']}")
        print(f"[Scheduler] Enhanced with injury data: {metadata['enhanced_with_injury_data']}")
        
    except Exception as e:
        print(f"[Scheduler] ✗ Failed to update predicted lineups: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if scraper:
            try:
                scraper.driver.quit()
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
