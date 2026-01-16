"""
Production-ready lineup scraper combining RotoWire (340+ predictions) 
with Premier Injuries data for enhanced accuracy.

This is the STABLE version designed for reliability over quantity.
Future: Extensible to add more sources without breaking existing functionality.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
from typing import List, Dict, Optional
from datetime import datetime
import re


class ProductionLineupScraper:
    """
    Production scraper: RotoWire (lineups) + Premier Injuries (injury data)
    
    Design Philosophy:
    - Reliability > Quantity
    - One good source > Multiple broken sources
    - Extensible for future additions
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
    
    def scrape_rotowire(self, gameweek: int) -> List[dict]:
        """
        Scrape RotoWire predicted lineups.
        
        Returns: List of player predictions with starting/bench status.
        Expected: 340+ predictions (11 starters + subs per team)
        """
        url = "https://www.rotowire.com/soccer/lineups.php"
        print(f"[RotoWire] Loading {url}")
        
        self.driver.get(url)
        
        # Wait for page to load
        print(f"[RotoWire] Waiting for page to load...")
        time.sleep(8)  # Increased from 3 to 8 seconds
        
        # Scroll to trigger lazy loading
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        predictions = []
        
        try:
            # Wait for lineup CONTAINERS to be present (the parent div.lineup)
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.lineup")))
            except TimeoutException:
                print("[RotoWire] Timeout waiting for lineup cards")
                # Save HTML for debugging
                with open('/tmp/rotowire_failed.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print("[RotoWire] Saved HTML to /tmp/rotowire_failed.html for debugging")
                return []
            
            # Find all lineup containers (each match has its own container)
            lineup_containers = self.driver.find_elements(By.CSS_SELECTOR, "div.lineup")
            print(f"[RotoWire] Found {len(lineup_containers)} matches")
            
            if not lineup_containers:
                print("[RotoWire] No lineup containers found")
                return []
            
            for idx, container in enumerate(lineup_containers):
                try:
                    # Get team abbreviations from container
                    team_abbr_elements = container.find_elements(By.CLASS_NAME, "lineup__abbr")
                    
                    if len(team_abbr_elements) < 2:
                        print(f"[RotoWire] Match {idx+1}: Less than 2 team names found, skipping")
                        continue
                    
                    home_team_abbr = team_abbr_elements[0].text.strip()
                    away_team_abbr = team_abbr_elements[1].text.strip()
                    
                    if not home_team_abbr or not away_team_abbr:
                        print(f"[RotoWire] Match {idx+1}: Empty team names, skipping")
                        continue
                    
                    print(f"[RotoWire] Processing match {idx+1}: {home_team_abbr} vs {away_team_abbr}")
                    
                    # Get the lineup__main section which contains players
                    lineup_main = container.find_element(By.CLASS_NAME, "lineup__main")
                    
                    # Get home and away team lineups
                    home_players = lineup_main.find_elements(By.CSS_SELECTOR, "ul.lineup__list.is-home li.lineup__player")
                    away_players = lineup_main.find_elements(By.CSS_SELECTOR, "ul.lineup__list.is-visit li.lineup__player")
                    
                    print(f"[RotoWire] {home_team_abbr}: {len(home_players)} players, {away_team_abbr}: {len(away_players)} players")
                    
                    # Process both teams
                    for team_abbr, player_list in [(home_team_abbr, home_players), (away_team_abbr, away_players)]:
                        for player_elem in player_list:
                            try:
                                # Get player name from link element (title attribute or text)
                                player_link = player_elem.find_element(By.TAG_NAME, "a")
                                player_name = player_link.get_attribute('title') or player_link.text.strip()
                                
                                if not player_name:
                                    continue
                                
                                # Check for injury indicators
                                injury_elem = player_elem.find_elements(By.CLASS_NAME, "lineup__inj")
                                injured = any('OUT' in elem.text.upper() for elem in injury_elem)
                                doubtful = any('DOUBT' in elem.text.upper() or 'QUES' in elem.text.upper() for elem in injury_elem)
                                
                                predictions.append({
                                    'player_name': player_name,
                                    'team_name': team_abbr,
                                    'gameweek': gameweek,
                                    'starting': True,  # All listed are predicted starters
                                    'bench': False,
                                    'injured': injured,
                                    'doubtful': doubtful,
                                    'suspended': False,
                                    'confidence': 'medium' if (injured or doubtful) else 'high',
                                    'status': 'predicted',
                                    'source': 'rotowire'
                                })
                            except Exception as e:
                                # Skip players that can't be extracted
                                continue
                
                except Exception as e:
                    print(f"[RotoWire] Error processing match {idx+1}: {e}")
                    continue
        
        except Exception as e:
            print(f"[RotoWire] Error: {e}")
        
        print(f"[RotoWire] ✅ Extracted {len(predictions)} predictions")
        return predictions
    
    def scrape_premier_injuries(self) -> Dict[str, List[dict]]:
        """
        Scrape Premier Injuries for comprehensive injury/suspension data.
        
        Returns: Dict of {team_name: [injury_records]}
        """
        url = "https://www.premierinjuries.com/injury-table.php"
        print(f"[Premier Injuries] Loading {url}")
        
        self.driver.get(url)
        
        print(f"[Premier Injuries] Waiting for page to load...")
        time.sleep(8)  # Increased from 4 to 8 seconds
        
        # Scroll to ensure content is loaded
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        injury_data = {}
        
        try:
            # Wait explicitly for table to be present
            try:
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                print("[Premier Injuries] Table element detected")
            except TimeoutException:
                print("[Premier Injuries] Timeout waiting for table")
                # Save HTML for debugging
                with open('/tmp/premierinjuries_failed.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print("[Premier Injuries] Saved HTML to /tmp/premierinjuries_failed.html for debugging")
                return injury_data
            
            # Find the main injury table
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            
            if not tables:
                print("[Premier Injuries] No tables found after wait")
                # Try alternative selectors
                print("[Premier Injuries] Trying alternative selectors...")
                tables = self.driver.find_elements(By.CSS_SELECTOR, "[class*='table'], [id*='table'], [class*='injury']")
            
            if not tables:
                print("[Premier Injuries] No tables found with any selector")
                return injury_data
            
            print(f"[Premier Injuries] Found {len(tables)} tables")
            
            # Use the first table (main injury table)
            table = tables[0]
            rows = table.find_elements(By.TAG_NAME, "tr")
            
            for row in rows[1:]:  # Skip header
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 4:
                        player_name = cells[0].text.strip()
                        team_name = cells[1].text.strip()
                        injury_type = cells[2].text.strip()
                        status = cells[3].text.strip()  # e.g., "Out", "Doubtful", "75%"
                        
                        if not team_name or not player_name:
                            continue
                        
                        if team_name not in injury_data:
                            injury_data[team_name] = []
                        
                        # Determine severity
                        is_ruled_out = 'out' in status.lower() or status == '0%'
                        is_doubtful = 'doubt' in status.lower() or any(p in status for p in ['25%', '50%'])
                        is_suspended = 'suspend' in injury_type.lower() or 'ban' in injury_type.lower()
                        
                        injury_data[team_name].append({
                            'player': player_name,
                            'injury_type': injury_type,
                            'status': status,
                            'ruled_out': is_ruled_out,
                            'doubtful': is_doubtful,
                            'suspended': is_suspended,
                            'return_date': cells[4].text.strip() if len(cells) > 4 else None
                        })
                
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"[Premier Injuries] Error: {e}")
        
        total_injuries = sum(len(injuries) for injuries in injury_data.values())
        print(f"[Premier Injuries] ✅ Found {total_injuries} injury records across {len(injury_data)} teams")
        
        return injury_data
    
    def merge_injury_data(self, predictions: List[dict], injury_data: Dict[str, List[dict]]) -> List[dict]:
        """
        Merge injury data into RotoWire predictions for enhanced accuracy.
        
        Logic:
        - If player is ruled out in injury data, override RotoWire prediction
        - If player is doubtful, lower confidence
        - Add injury details to prediction
        """
        print(f"[Merger] Merging injury data into {len(predictions)} predictions")
        
        # Normalize team names for matching
        team_name_map = self._build_team_name_map()
        
        enhanced_predictions = []
        
        for pred in predictions:
            # Try to find matching injury data
            pred_team = pred['team_name'].upper()
            
            # Find matching team in injury data
            matching_injuries = []
            for team_name, injuries in injury_data.items():
                team_normalized = team_name_map.get(team_name.lower(), team_name.upper())
                if team_normalized == pred_team or team_name.lower() in pred['team_name'].lower():
                    matching_injuries = injuries
                    break
            
            # Check if this player is in injury list
            player_name_normalized = self._normalize_player_name(pred['player_name'])
            
            injury_match = None
            for injury in matching_injuries:
                injury_player_normalized = self._normalize_player_name(injury['player'])
                if injury_player_normalized == player_name_normalized or \
                   injury_player_normalized in player_name_normalized or \
                   player_name_normalized in injury_player_normalized:
                    injury_match = injury
                    break
            
            # Apply injury data
            if injury_match:
                if injury_match['ruled_out']:
                    pred['starting'] = False
                    pred['injured'] = True
                    pred['confidence'] = 'low'
                    pred['injury_details'] = f"{injury_match['injury_type']} - {injury_match['status']}"
                elif injury_match['doubtful']:
                    pred['doubtful'] = True
                    pred['confidence'] = 'medium'
                    pred['injury_details'] = f"{injury_match['injury_type']} - {injury_match['status']}"
                elif injury_match['suspended']:
                    pred['starting'] = False
                    pred['suspended'] = True
                    pred['confidence'] = 'low'
                    pred['injury_details'] = injury_match['injury_type']
            
            enhanced_predictions.append(pred)
        
        # Count enhancements
        enhanced_count = len([p for p in enhanced_predictions if p.get('injury_details')])
        print(f"[Merger] ✅ Enhanced {enhanced_count} predictions with injury data")
        
        return enhanced_predictions
    
    def scrape_all(self, gameweek: int) -> Dict[str, any]:
        """
        Main method: Scrape all sources and merge data.
        
        Returns:
            {
                'predictions': List[dict],  # Enhanced predictions
                'injury_data': Dict,        # Raw injury data
                'metadata': Dict            # Scraping metadata
            }
        """
        print(f"\n{'='*80}")
        print(f"PRODUCTION SCRAPER - Gameweek {gameweek}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        # Step 1: Scrape RotoWire
        rotowire_predictions = self.scrape_rotowire(gameweek)
        
        time.sleep(2)
        
        # Step 2: Scrape Premier Injuries
        injury_data = self.scrape_premier_injuries()
        
        # Step 3: Merge data
        enhanced_predictions = self.merge_injury_data(rotowire_predictions, injury_data)
        
        elapsed_time = time.time() - start_time
        
        # Generate metadata
        metadata = {
            'gameweek': gameweek,
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': elapsed_time,
            'sources': ['rotowire', 'premier_injuries'],
            'total_predictions': len(enhanced_predictions),
            'starters': len([p for p in enhanced_predictions if p['starting']]),
            'bench': len([p for p in enhanced_predictions if p['bench']]),
            'injured': len([p for p in enhanced_predictions if p['injured']]),
            'doubtful': len([p for p in enhanced_predictions if p['doubtful']]),
            'suspended': len([p for p in enhanced_predictions if p['suspended']]),
            'enhanced_with_injury_data': len([p for p in enhanced_predictions if p.get('injury_details')])
        }
        
        print(f"\n{'='*80}")
        print(f"SCRAPING COMPLETE")
        print(f"{'='*80}")
        print(f"Total Predictions: {metadata['total_predictions']}")
        print(f"  Starters: {metadata['starters']}")
        print(f"  Bench: {metadata['bench']}")
        print(f"  Injured: {metadata['injured']}")
        print(f"  Doubtful: {metadata['doubtful']}")
        print(f"  Suspended: {metadata['suspended']}")
        print(f"Enhanced with injury data: {metadata['enhanced_with_injury_data']}")
        print(f"Time: {elapsed_time:.1f}s")
        print(f"{'='*80}\n")
        
        return {
            'predictions': enhanced_predictions,
            'injury_data': injury_data,
            'metadata': metadata
        }
    
    def _build_team_name_map(self) -> Dict[str, str]:
        """Build team name normalization map."""
        return {
            'arsenal': 'ARS', 'aston villa': 'AVL', 'bournemouth': 'BOU',
            'brentford': 'BRE', 'brighton': 'BHA', 'chelsea': 'CHE',
            'crystal palace': 'CRY', 'everton': 'EVE', 'fulham': 'FUL',
            'liverpool': 'LIV', 'manchester city': 'MCI', 'man city': 'MCI',
            'manchester united': 'MUN', 'man united': 'MUN', 'man utd': 'MUN',
            'newcastle': 'NEW', 'nottingham forest': 'NFO', "nott'm forest": 'NFO',
            'tottenham': 'TOT', 'west ham': 'WHU', 'wolves': 'WOL',
            'leicester': 'LEI', 'leeds': 'LEE', 'southampton': 'SOU',
            'burnley': 'BUR', 'mun': 'MUN', 'mci': 'MCI', 'tot': 'TOT',
            'whu': 'WHU', 'cry': 'CRY', 'liv': 'LIV', 'not': 'NFO',
            'ars': 'ARS', 'che': 'CHE', 'avl': 'AVL', 'new': 'NEW'
        }
    
    def _normalize_player_name(self, name: str) -> str:
        """Normalize player name for matching."""
        import re
        normalized = name.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return normalized
    
    def __del__(self):
        """Cleanup."""
        try:
            self.driver.quit()
        except:
            pass
