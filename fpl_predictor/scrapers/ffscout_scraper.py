"""
Fantasy Football Scout scraper for predicted lineups and injury data.

Scrapes: https://www.fantasyfootballscout.co.uk/team-news
Provides: Team news with injury status percentages
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
from typing import List, Dict, Optional
from datetime import datetime


class FFScoutScraper:
    """
    Fantasy Football Scout scraper for team news and predicted lineups.
    
    Provides injury status with percentage-based doubt ratings that should be INVERTED:
    - "75% doubt" = 25% chance to start
    - "Out" = 0% chance to start
    - No status = 100% chance to start
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
    
    def _parse_doubt_percentage(self, status_text: str) -> Optional[float]:
        """
        Parse doubt percentage from status text.
        
        Args:
            status_text: Text like "75%", "Doubt", "Out", "Banned"
            
        Returns:
            Float between 0.0-1.0 representing START probability (inverted from doubt)
            - "75% doubt" → 0.25 (25% to start)
            - "Out" → 0.0
            - "Banned" → 0.0
            - No status → 1.0
        """
        if not status_text:
            return 1.0  # No status means expected to start
        
        status_lower = status_text.lower().strip()
        
        # Check for explicit "Out" or "Banned"
        if 'out' in status_lower or 'banned' in status_lower or 'suspend' in status_lower:
            return 0.0
        
        # Check for percentage
        percentage_match = re.search(r'(\d+)%', status_text)
        if percentage_match:
            doubt_pct = int(percentage_match.group(1))
            # INVERT: 75% doubt = 25% to start
            return (100 - doubt_pct) / 100.0
        
        # Generic "Doubt" without percentage - assume 50% doubt = 50% to start
        if 'doubt' in status_lower or 'question' in status_lower:
            return 0.5
        
        # Default: assume starting if no clear doubt
        return 1.0
    
    def scrape_team_news(self, gameweek: int) -> List[dict]:
        """
        Scrape Fantasy Football Scout team news page.
        
        Returns: List of player predictions with inverted doubt percentages.
        """
        url = "https://www.fantasyfootballscout.co.uk/team-news"
        print(f"[FF Scout] Loading {url}")
        
        self.driver.get(url)
        
        # Wait for page to load
        print(f"[FF Scout] Waiting for page to load...")
        time.sleep(8)
        
        # Scroll to trigger lazy loading
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Save HTML for debugging (always)
        import os
        debug_path = os.path.join(os.path.dirname(__file__), '..', '..', 'ffscout_debug.html')
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        print(f"[FF Scout] Saved HTML to {debug_path} for debugging")
        
        predictions = []
        
        try:
            # Try to find team sections - use multiple selector strategies
            selectors_to_try = [
                "div.team-section",
                "div[class*='team']",
                "section[class*='team']",
                "article[class*='team']",
                "div.team-card",
                "div.club-section"
            ]
            
            team_sections = []
            for selector in selectors_to_try:
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    team_sections = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if team_sections:
                        print(f"[FF Scout] Found {len(team_sections)} team sections using selector: {selector}")
                        break
                except TimeoutException:
                    continue
            
            if not team_sections:
                print("[FF Scout] No team sections found with any selector")
                # Save HTML for debugging
                import os
                debug_path = os.path.join(os.path.dirname(__file__), '..', '..', 'ffscout_debug.html')
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print(f"[FF Scout] Saved HTML to {debug_path} for debugging")
                return []
            
            # Process each team section
            for idx, section in enumerate(team_sections):
                try:
                    # Try to extract team name - multiple strategies
                    team_name = None
                    
                    # Strategy 1: Look for heading with team name
                    for heading_tag in ['h2', 'h3', 'h4']:
                        team_headings = section.find_elements(By.TAG_NAME, heading_tag)
                        if team_headings:
                            team_name = team_headings[0].text.strip()
                            break
                    
                    # Strategy 2: Look for class containing "team-name" or similar
                    if not team_name:
                        team_name_elems = section.find_elements(By.CSS_SELECTOR, "[class*='team-name'], [class*='club-name']")
                        if team_name_elems:
                            team_name = team_name_elems[0].text.strip()
                    
                    if not team_name:
                        print(f"[FF Scout] Team {idx+1}: Could not extract team name, skipping")
                        continue
                    
                    print(f"[FF Scout] Processing team {idx+1}: {team_name}")
                    
                    # Find all players in this team section
                    # Try multiple player container selectors
                    player_elements = []
                    player_selectors = [
                        "div.player",
                        "div[class*='player']",
                        "li.player",
                        "div.player-row",
                        "tr[class*='player']"
                    ]
                    
                    for player_selector in player_selectors:
                        player_elements = section.find_elements(By.CSS_SELECTOR, player_selector)
                        if player_elements:
                            break
                    
                    if not player_elements:
                        print(f"[FF Scout] {team_name}: No players found")
                        continue
                    
                    print(f"[FF Scout] {team_name}: Found {len(player_elements)} players")
                    
                    # Process each player
                    for player_elem in player_elements:
                        try:
                            # Extract player name - try multiple strategies
                            player_name = None
                            
                            # Try link text
                            player_links = player_elem.find_elements(By.TAG_NAME, "a")
                            if player_links:
                                player_name = player_links[0].text.strip()
                            
                            # Try span/div with player name class
                            if not player_name:
                                name_elems = player_elem.find_elements(By.CSS_SELECTOR, "[class*='name']")
                                if name_elems:
                                    player_name = name_elems[0].text.strip()
                            
                            if not player_name:
                                continue
                            
                            # Extract injury/doubt status
                            status_text = ""
                            status_elems = player_elem.find_elements(By.CSS_SELECTOR, 
                                "[class*='status'], [class*='injury'], [class*='doubt'], [class*='badge']")
                            
                            if status_elems:
                                status_text = status_elems[0].text.strip()
                            
                            # Parse status to get start probability
                            start_prob = self._parse_doubt_percentage(status_text)
                            
                            # Determine flags
                            status_lower = status_text.lower()
                            injured = 'out' in status_lower and 'doubt' not in status_lower
                            suspended = 'banned' in status_lower or 'suspend' in status_lower
                            doubtful = 'doubt' in status_lower or '%' in status_text
                            
                            predictions.append({
                                'player_name': player_name,
                                'team_name': team_name,
                                'gameweek': gameweek,
                                'starting': start_prob >= 0.5,  # Consider starting if >50%
                                'bench': False,
                                'injured': injured,
                                'doubtful': doubtful,
                                'suspended': suspended,
                                'confidence': 'high' if start_prob >= 0.8 else 'medium' if start_prob >= 0.4 else 'low',
                                'status': 'predicted',
                                'source': 'ffscout',
                                'raw_status': status_text,
                                'start_probability_raw': start_prob  # Store the calculated probability
                            })
                        
                        except Exception as e:
                            # Skip players that can't be extracted
                            continue
                
                except Exception as e:
                    print(f"[FF Scout] Error processing team {idx+1}: {e}")
                    continue
        
        except Exception as e:
            print(f"[FF Scout] Error: {e}")
        
        print(f"[FF Scout] ✅ Extracted {len(predictions)} predictions")
        return predictions
    
    def scrape_all(self, gameweek: int) -> Dict[str, any]:
        """
        Main method: Scrape FF Scout data.
        
        Returns:
            {
                'predictions': List[dict],
                'metadata': Dict
            }
        """
        print(f"\n{'='*80}")
        print(f"FF SCOUT SCRAPER - Gameweek {gameweek}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        predictions = self.scrape_team_news(gameweek)
        
        elapsed_time = time.time() - start_time
        
        # Generate metadata
        metadata = {
            'gameweek': gameweek,
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': elapsed_time,
            'source': 'ffscout',
            'total_predictions': len(predictions),
            'starters': len([p for p in predictions if p['starting']]),
            'injured': len([p for p in predictions if p['injured']]),
            'doubtful': len([p for p in predictions if p['doubtful']]),
            'suspended': len([p for p in predictions if p['suspended']])
        }
        
        print(f"\n{'='*80}")
        print(f"FF SCOUT SCRAPING COMPLETE")
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
