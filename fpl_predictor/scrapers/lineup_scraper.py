"""
Lineup scraper module for gathering predicted lineups from multiple sources.

Scrapes 6 major FPL lineup prediction websites and returns structured data.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
import time


class LineupScraper:
    """Scrapes predicted lineups from multiple FPL prediction websites."""
    
    def __init__(self, headless=True):
        """
        Initialize the scraper with Selenium WebDriver.
        
        Args:
            headless: Run browser in headless mode (no GUI)
        """
        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)
        self.gw_validation_warnings = []
    
    def scrape_all_sources(self, gameweek: int) -> Dict[str, List[dict]]:
        """
        Scrape all sources and return raw predictions.
        
        Args:
            gameweek: The gameweek number to scrape
            
        Returns:
            Dictionary mapping source name to list of player predictions
        """
        results = {}
        
        scrapers = [
            ('ffscout', self.scrape_ffscout),
            ('rotowire', self.scrape_rotowire),
            ('fpl_pundit', self.scrape_fpl_pundit),
            ('fpl_edits', self.scrape_fpl_edits),
            ('fpl_hub', self.scrape_fpl_hub),
            ('sports_gambler', self.scrape_sports_gambler)
        ]
        
        for source_name, scraper_func in scrapers:
            try:
                print(f"[Scraper] Starting {source_name} for GW{gameweek}...")
                predictions = scraper_func(gameweek)
                results[source_name] = predictions
                print(f"[Scraper] ✓ {source_name}: {len(predictions)} predictions")
                time.sleep(2)  # Polite delay between requests
            except Exception as e:
                print(f"[Scraper] ✗ Failed to scrape {source_name}: {e}")
                results[source_name] = []
        
        return results
    
    def _validate_gameweek(self, page_text: str, expected_gw: int, source: str) -> bool:
        """
        Validate that the page contains the expected gameweek number.
        
        Args:
            page_text: Text content of the page
            expected_gw: Expected gameweek number
            source: Name of the source being scraped
            
        Returns:
            True if GW matches or can't be determined
        """
        # Look for GW patterns
        gw_patterns = [
            rf'GW\s*{expected_gw}\b',
            rf'Gameweek\s*{expected_gw}\b',
            rf'Week\s*{expected_gw}\b',
            rf'Round\s*{expected_gw}\b'
        ]
        
        for pattern in gw_patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                return True
        
        # Warn if we couldn't validate
        warning = f"[{source}] Could not validate GW{expected_gw} on page"
        self.gw_validation_warnings.append(warning)
        print(warning)
        return True  # Continue anyway but log warning
    
    def scrape_ffscout(self, gameweek: int) -> List[dict]:
        """
        Scrape Fantasy Football Scout predicted lineups.
        
        URL: https://www.fantasyfootballscout.co.uk/team-news
        """
        url = "https://www.fantasyfootballscout.co.uk/team-news"
        self.driver.get(url)
        
        time.sleep(3)  # Wait for dynamic content
        
        predictions = []
        
        try:
            # Save HTML for debugging
            print(f"[FFScout] Page loaded, saving HTML for debugging...")
            with open('/tmp/ffscout_page.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            print(f"[FFScout] Page source saved to /tmp/ffscout_page.html")
            
            # Find team sections
            team_sections = self.driver.find_elements(By.CLASS_NAME, "team-news-section")
            print(f"[FFScout] Found {len(team_sections)} elements with class 'team-news-section'")
            
            if not team_sections:
                # Try alternative selectors
                print(f"[FFScout] Trying alternative selectors...")
                team_sections = self.driver.find_elements(By.CSS_SELECTOR, "[class*='team']")
                print(f"[FFScout] Found {len(team_sections)} elements with 'team' in class")
            
            for team_section in team_sections[:5]:  # Limit for testing
                try:
                    # Get team name
                    team_name_elem = team_section.find_element(By.TAG_NAME, "h2")
                    team_name = team_name_elem.text.strip()
                    print(f"[FFScout] Processing team: {team_name}")
                    
                    # Get players in predicted lineup
                    player_elements = team_section.find_elements(By.CLASS_NAME, "player-card")
                    print(f"[FFScout] Found {len(player_elements)} player cards")
                    
                    for player_elem in player_elements:
                        player_name = player_elem.text.strip()
                        
                        # Check for injury/doubt indicators
                        injured = 'injured' in player_elem.get_attribute('class').lower()
                        doubtful = 'doubtful' in player_elem.get_attribute('class').lower()
                        
                        predictions.append({
                            'player_name': player_name,
                            'team_name': team_name,
                            'gameweek': gameweek,
                            'starting': True,
                            'bench': False,
                            'injured': injured,
                            'doubtful': doubtful,
                            'suspended': False,
                            'confidence': 'high' if not (injured or doubtful) else 'medium',
                            'status': 'predicted'
                        })
                except Exception as e:
                    print(f"[FFScout] Error processing team section: {e}")
                    continue
        
        except Exception as e:
            print(f"[FFScout] Error parsing page: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[FFScout] Total predictions extracted: {len(predictions)}")
        return predictions
    
    def scrape_rotowire(self, gameweek: int) -> List[dict]:
        """
        Scrape RotoWire soccer lineups.
        
        URL: https://www.rotowire.com/soccer/lineups.php
        """
        url = "https://www.rotowire.com/soccer/lineups.php"
        self.driver.get(url)
        
        time.sleep(3)
        
        predictions = []
        
        try:
            # Save HTML for debugging
            print(f"[RotoWire] Page loaded, saving HTML for debugging...")
            with open('/tmp/rotowire_page.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            print(f"[RotoWire] Page source saved to /tmp/rotowire_page.html")
            
            # Find all lineup containers (each match has its own container)
            lineup_containers = self.driver.find_elements(By.CSS_SELECTOR, "div.lineup")
            print(f"[RotoWire] Found {len(lineup_containers)} matches")
            
            for container in lineup_containers:
                try:
                    # Get team names from lineup__teams section
                    team_elements = container.find_elements(By.CLASS_NAME, "lineup__abbr")
                    
                    if len(team_elements) < 2:
                        continue
                    
                    home_team = team_elements[0].text.strip()
                    away_team = team_elements[1].text.strip()
                    print(f"[RotoWire] Processing match: {home_team} vs {away_team}")
                    
                    # Get the lineup__main section which contains players
                    lineup_main = container.find_element(By.CLASS_NAME, "lineup__main")
                    
                    # Get home and away team lineups (separate ul elements)
                    home_lineup = lineup_main.find_elements(By.CSS_SELECTOR, "ul.lineup__list.is-home li.lineup__player")
                    away_lineup = lineup_main.find_elements(By.CSS_SELECTOR, "ul.lineup__list.is-visit li.lineup__player")
                    
                    print(f"[RotoWire] {home_team}: {len(home_lineup)} players, {away_team}: {len(away_lineup)} players")
                    
                    # Process home team
                    for idx, player_elem in enumerate(home_lineup):
                        try:
                            player_link = player_elem.find_element(By.TAG_NAME, "a")
                            player_name = player_link.get_attribute('title') or player_link.text.strip()
                            
                            # Check for injury indicators
                            injury_elem = player_elem.find_elements(By.CLASS_NAME, "lineup__inj")
                            injured = any('OUT' in elem.text.upper() for elem in injury_elem)
                            doubtful = any('DOUBT' in elem.text.upper() or 'QUES' in elem.text.upper() for elem in injury_elem)
                            
                            predictions.append({
                                'player_name': player_name,
                                'team_name': home_team,
                                'gameweek': gameweek,
                                'starting': True,  # All listed are predicted starters
                                'bench': False,
                                'injured': injured,
                                'doubtful': doubtful,
                                'suspended': False,
                                'confidence': 'medium' if (injured or doubtful) else 'high',
                                'status': 'predicted'
                            })
                        except Exception as e:
                            continue
                    
                    # Process away team
                    for idx, player_elem in enumerate(away_lineup):
                        try:
                            player_link = player_elem.find_element(By.TAG_NAME, "a")
                            player_name = player_link.get_attribute('title') or player_link.text.strip()
                            
                            # Check for injury indicators
                            injury_elem = player_elem.find_elements(By.CLASS_NAME, "lineup__inj")
                            injured = any('OUT' in elem.text.upper() for elem in injury_elem)
                            doubtful = any('DOUBT' in elem.text.upper() or 'QUES' in elem.text.upper() for elem in injury_elem)
                            
                            predictions.append({
                                'player_name': player_name,
                                'team_name': away_team,
                                'gameweek': gameweek,
                                'starting': True,
                                'bench': False,
                                'injured': injured,
                                'doubtful': doubtful,
                                'suspended': False,
                                'confidence': 'medium' if (injured or doubtful) else 'high',
                                'status': 'predicted'
                            })
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    print(f"[RotoWire] Error processing match: {e}")
                    continue
        
        except Exception as e:
            print(f"[RotoWire] Error parsing page: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[RotoWire] Total predictions extracted: {len(predictions)}")
        return predictions
    
    def scrape_fpl_pundit(self, gameweek: int) -> List[dict]:
        """
        Scrape FPL Pundit team news and predicted lineups.
        
        URL: https://www.fantasyfootballpundit.com/fantasy-premier-league-team-news/
        """
        url = "https://www.fantasyfootballpundit.com/fantasy-premier-league-team-news/"
        self.driver.get(url)
        
        time.sleep(3)
        
        predictions = []
        
        try:
            # Parse article content for team news
            article = self.driver.find_element(By.TAG_NAME, "article")
            content = article.text
            
            # Look for team sections (teams are usually in headings)
            headings = article.find_elements(By.TAG_NAME, "h3")
            
            for heading in headings:
                team_name = heading.text.strip()
                
                # Get the paragraph(s) after the heading
                try:
                    next_elem = heading.find_element(By.XPATH, "following-sibling::p")
                    team_news = next_elem.text
                    
                    # Extract player names (usually capitalized or in bold)
                    player_mentions = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', team_news)
                    
                    for player_name in player_mentions:
                        # Determine status from context
                        injured = 'injured' in team_news.lower() or 'out' in team_news.lower()
                        doubtful = 'doubt' in team_news.lower() or 'fitness' in team_news.lower()
                        suspended = 'suspended' in team_news.lower() or 'banned' in team_news.lower()
                        
                        predictions.append({
                            'player_name': player_name,
                            'team_name': team_name,
                            'gameweek': gameweek,
                            'starting': not (injured or suspended),
                            'bench': False,
                            'injured': injured,
                            'doubtful': doubtful,
                            'suspended': suspended,
                            'confidence': 'medium',
                            'status': 'predicted'
                        })
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"[FPL Pundit] Error parsing page: {e}")
        
        return predictions
    
    def scrape_fpl_edits(self, gameweek: int) -> List[dict]:
        """
        Scrape FPL Edits predicted lineups.
        
        URL: https://fpledits.com/predicted-lineups-pl
        """
        url = "https://fpledits.com/predicted-lineups-pl"
        self.driver.get(url)
        
        time.sleep(4)  # More time for this site
        
        predictions = []
        
        try:
            # Look for lineup cards or sections
            lineup_containers = self.driver.find_elements(By.CLASS_NAME, "lineup-container")
            
            if not lineup_containers:
                lineup_containers = self.driver.find_elements(By.CSS_SELECTOR, "[class*='lineup']")
            
            for container in lineup_containers:
                try:
                    team_name_elem = container.find_element(By.CSS_SELECTOR, "[class*='team-name']")
                    team_name = team_name_elem.text.strip()
                    
                    players = container.find_elements(By.CSS_SELECTOR, "[class*='player']")
                    
                    for player_elem in players:
                        player_name = player_elem.text.strip()
                        
                        # Check badges/indicators
                        classes = player_elem.get_attribute('class')
                        injured = 'injury' in classes.lower()
                        doubtful = 'doubt' in classes.lower()
                        
                        predictions.append({
                            'player_name': player_name,
                            'team_name': team_name,
                            'gameweek': gameweek,
                            'starting': True,
                            'bench': False,
                            'injured': injured,
                            'doubtful': doubtful,
                            'suspended': False,
                            'confidence': 'high',
                            'status': 'predicted'
                        })
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"[FPL Edits] Error parsing page: {e}")
        
        return predictions
    
    def scrape_fpl_hub(self, gameweek: int) -> List[dict]:
        """
        Scrape Fantasy Football Hub predicted lineups.
        
        URL: https://www.fantasyfootballhub.co.uk/premier-league-predicted-lineups
        """
        url = "https://www.fantasyfootballhub.co.uk/premier-league-predicted-lineups"
        self.driver.get(url)
        
        time.sleep(3)
        
        predictions = []
        
        try:
            # Find team lineup sections
            team_sections = self.driver.find_elements(By.CSS_SELECTOR, "[class*='team-lineup']")
            
            for section in team_sections:
                try:
                    team_name = section.find_element(By.TAG_NAME, "h3").text.strip()
                    
                    player_elements = section.find_elements(By.CSS_SELECTOR, "[class*='player']")
                    
                    for player_elem in player_elements:
                        player_name = player_elem.text.strip()
                        
                        # Look for status indicators
                        status_badge = player_elem.find_elements(By.CSS_SELECTOR, "[class*='status']")
                        injured = any('injured' in badge.text.lower() for badge in status_badge)
                        doubtful = any('doubt' in badge.text.lower() for badge in status_badge)
                        
                        predictions.append({
                            'player_name': player_name,
                            'team_name': team_name,
                            'gameweek': gameweek,
                            'starting': True,
                            'bench': False,
                            'injured': injured,
                            'doubtful': doubtful,
                            'suspended': False,
                            'confidence': 'high',
                            'status': 'predicted'
                        })
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"[FPL Hub] Error parsing page: {e}")
        
        return predictions
    
    def scrape_sports_gambler(self, gameweek: int) -> List[dict]:
        """
        Scrape Sports Gambler lineups.
        
        URL: https://www.sportsgambler.com/lineups/football/
        """
        url = "https://www.sportsgambler.com/lineups/football/"
        self.driver.get(url)
        
        time.sleep(3)
        
        predictions = []
        
        try:
            # Filter to Premier League
            league_links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Premier League")
            if league_links:
                league_links[0].click()
                time.sleep(2)
            
            # Find match cards
            match_cards = self.driver.find_elements(By.CLASS_NAME, "match-card")
            
            for card in match_cards:
                try:
                    # Get both teams
                    team_elements = card.find_elements(By.CLASS_NAME, "team-name")
                    
                    if len(team_elements) >= 2:
                        home_team = team_elements[0].text.strip()
                        away_team = team_elements[1].text.strip()
                        
                        # Get lineups for both teams
                        lineup_sections = card.find_elements(By.CLASS_NAME, "lineup")
                        
                        for idx, lineup in enumerate(lineup_sections):
                            team_name = home_team if idx == 0 else away_team
                            
                            players = lineup.find_elements(By.CLASS_NAME, "player-name")
                            
                            for player_elem in players:
                                player_name = player_elem.text.strip()
                                
                                predictions.append({
                                    'player_name': player_name,
                                    'team_name': team_name,
                                    'gameweek': gameweek,
                                    'starting': True,
                                    'bench': False,
                                    'injured': False,
                                    'doubtful': False,
                                    'suspended': False,
                                    'confidence': 'high',
                                    'status': 'predicted'
                                })
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"[Sports Gambler] Error parsing page: {e}")
        
        return predictions
    
    def __del__(self):
        """Cleanup: close the browser."""
        try:
            self.driver.quit()
        except:
            pass
