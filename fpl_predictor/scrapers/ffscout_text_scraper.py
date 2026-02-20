"""
Fantasy Football Scout scraper using text extraction (much simpler!)

Instead of parsing complex HTML/CSS, we get the rendered text content
(like Ctrl+C) and parse it. This is more robust against HTML changes.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from typing import List, Dict, Optional
from datetime import datetime


class FFScoutTextScraper:
    """
    Fantasy Football Scout scraper using text extraction.
    
    Gets the page's rendered text content (like Ctrl+C) and parses it.
    Much more robust than CSS selector approach!
    """
    
    def __init__(self, headless=True):
        """Initialize scraper with Chrome WebDriver."""
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)
    
    def scrape_team_news(self, gameweek: int) -> List[dict]:
        """
        Scrape FF Scout team news using text extraction.
        
        Returns: List of player predictions with starting/bench status.
        """
        url = "https://www.fantasyfootballscout.co.uk/team-news"
        print(f"[FF Scout Text] Loading {url}")
        
        self.driver.get(url)
        
        # Wait for page to load and JavaScript to execute
        print(f"[FF Scout Text] Waiting for content to render...")
        time.sleep(10)  # Longer wait for JS to finish
        
        # Scroll to load all content
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        # Get the page's text content (like Ctrl+C)
        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            page_text = body.text
            print(f"[FF Scout Text] Extracted {len(page_text)} characters of text")
            
            # Parse the text
            predictions = self._parse_text(page_text, gameweek)
            
            print(f"[FF Scout Text] ✅ Extracted {len(predictions)} predictions")
            return predictions
            
        except Exception as e:
            print(f"[FF Scout Text] Error: {e}")
            return []
    
    def _parse_text(self, text: str, gameweek: int) -> List[dict]:
        """Parse the page text to extract team news and predicted lineups."""
        predictions = []
        lines = text.split('\n')
        
        current_team = None
        in_team_section = False
        seen_out = False
        seen_doubts = False
        
        # Premier League teams (for matching)
        pl_teams = {
            'Arsenal', 'Aston Villa', 'Bournemouth', 'Brentford', 'Brighton and Hove Albion',
            'Burnley', 'Chelsea', 'Crystal Palace', 'Everton', 'Fulham',
            'Leeds United', 'Liverpool', 'Manchester City', 'Manchester United',
            'Newcastle United', 'Nottingham Forest', 'Sunderland', 'Tottenham Hotspur',
            'West Ham United', 'Wolverhampton Wanderers'
        }
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if this is a team name
            if line in pl_teams:
                current_team = line
                in_team_section = True
                seen_out = False
                seen_doubts = False
                print(f"[FF Scout Text] Found team: {current_team}")
                i += 1
                continue
            
            # If we're in a team section, look for player names
            if in_team_section and current_team:
                
                # Check for "Out:" line
                if line.startswith('Out:'):
                    seen_out = True
                    # Extract player names after "Out:"
                    out_players = line[4:].strip()  # Remove "Out:"
                    for player_name in self._split_player_names(out_players):
                        if player_name:
                            predictions.append({
                                'player_name': player_name,
                                'team_name': current_team,
                                'gameweek': gameweek,
                                'starting': False,
                                'bench': False,
                                'injured': True,
                                'doubtful': False,
                                'suspended': False,
                                'confidence': 'low',
                                'status': 'predicted',
                                'source': 'ffscout_text',
                                'start_probability_raw': 0.0
                            })
                    i += 1
                    continue
                
                # Check for "Doubts:" line
                if line.startswith('Doubts:'):
                    seen_doubts = True
                    # Extract player names with doubt percentages
                    doubts_text = line[7:].strip()  # Remove "Doubts:"
                    # Pattern: "Hincapie 75%"
                    doubt_matches = re.findall(r'(\w[\w\s\-\.\']+)\s+(\d+)%', doubts_text)
                    for player_name, doubt_pct in doubt_matches:
                        start_prob = (100 - int(doubt_pct)) / 100.0  # Invert doubt
                        predictions.append({
                            'player_name': player_name.strip(),
                            'team_name': current_team,
                            'gameweek': gameweek,
                            'starting': start_prob >= 0.5,
                            'bench': False,
                            'injured': False,
                            'doubtful': True,
                            'suspended': False,
                            'confidence': 'medium' if start_prob >= 0.4 else 'low',
                            'status': 'predicted',
                            'source': 'ffscout_text',
                            'raw_status': f'{doubt_pct}% doubt',
                            'start_probability_raw': start_prob
                        })
                    i += 1
                    continue
                
                # Check for "Banned:" line (end of team section)
                if line.startswith('Banned:'):
                    # Check if there are banned players
                    banned_text = line[7:].strip()
                    if banned_text:
                        for player_name in self._split_player_names(banned_text):
                            if player_name:
                                predictions.append({
                                    'player_name': player_name,
                                    'team_name': current_team,
                                    'gameweek': gameweek,
                                    'starting': False,
                                    'bench': False,
                                    'injured': False,
                                    'doubtful': False,
                                    'suspended': True,
                                    'confidence': 'low',
                                    'status': 'predicted',
                                    'source': 'ffscout_text',
                                    'start_probability_raw': 0.0
                                })
                    in_team_section = False
                    current_team = None
                    i += 1
                    continue
                
                # Check for "Latest News:" (also end of team section)
                if line.startswith('Latest News:'):
                    in_team_section = False
                    current_team = None
                    i += 1
                    continue
                
                # Extract starting players
                # After team name, before "Out:", we get player names
                # Skip lines that are obviously not player names
                skip_keywords = ['Next Match:', 'badge', 'Latest News:', 'All Teams', 'Avatar of']
                if any(keyword in line for keyword in skip_keywords):
                    i += 1
                    continue
                
                # If line looks like a player name (title case, reasonable length)
                # and we haven't hit Out/Doubts/Banned yet
                if (not seen_out and not seen_doubts and 
                    line and 
                    len(line) > 2 and 
                    len(line) < 50 and
                    line[0].isupper() and
                    not line.startswith('Out:') and
                    not line.startswith('Doubts:') and
                    not line.startswith('Banned:')):
                    
                    # This is likely a starting player
                    player_name = line.strip().title()  # Convert to Title Case
                    
                    predictions.append({
                        'player_name': player_name,
                        'team_name': current_team,
                        'gameweek': gameweek,
                        'starting': True,
                        'bench': False,
                        'injured': False,
                        'doubtful': False,
                        'suspended': False,
                        'confidence': 'high',
                        'status': 'predicted',
                        'source': 'ffscout_text',
                        'start_probability_raw': 1.0
                    })
            
            i += 1
        
        return predictions
    
    def _split_player_names(self, text: str) -> List[str]:
        """Split concatenated player names (e.g., 'CalafioriDowmanMosquera' -> ['Calafiori', 'Dowman', 'Mosquera'])."""
        # Simple heuristic: split on capital letters
        names = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
        return names
    
    def _deduplicate_name(self, name: str) -> str:
        """Deduplicate names like 'Raya MartinRaya Martin' -> 'Raya Martin'."""
        # Check if the name is repeated
        parts = name.split()
        if len(parts) % 2 == 0:
            mid = len(parts) // 2
            first_half = ' '.join(parts[:mid])
            second_half = ' '.join(parts[mid:])
            if first_half == second_half:
                return first_half
        return name
    
    def scrape_all(self, gameweek: int) -> Dict[str, any]:
        """
        Main method: Scrape FF Scout data using text extraction.
        
        Returns:
            {
                'predictions': List[dict],
                'metadata': Dict
            }
        """
        print(f"\n{'='*80}")
        print(f"FF SCOUT TEXT SCRAPER - Gameweek {gameweek}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        predictions = self.scrape_team_news(gameweek)
        
        elapsed_time = time.time() - start_time
        
        # Generate metadata
        metadata = {
            'gameweek': gameweek,
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': elapsed_time,
            'source': 'ffscout_text',
            'total_predictions': len(predictions),
            'starters': len([p for p in predictions if p['starting']]),
            'injured': len([p for p in predictions if p['injured']]),
            'doubtful': len([p for p in predictions if p['doubtful']]),
            'suspended': len([p for p in predictions if p['suspended']])
        }
        
        print(f"\n{'='*80}")
        print(f"FF SCOUT TEXT SCRAPING COMPLETE")
        print(f"{'='*80}")
        print(f"Total Predictions: {metadata['total_predictions']}")
        print(f"  Starters: {metadata['starters']}")
        print(f"  Injured: {metadata['injured']}")
        print(f"  Doubtful: {metadata['doubtful']}")
        print(f"  Suspended: {metadata['suspended']}")
        print(f"Time: {elapsed_time:.1f}s")
        print(f"{'='*80}\n")
        
        return {
            'predictions': predictions,
            'metadata': metadata
        }
    
    def __del__(self):
        """Cleanup."""
        try:
            self.driver.quit()
        except:
            pass
