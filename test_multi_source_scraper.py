"""
Test scraper for multiple predicted lineup sources.
Tests which websites we can successfully scrape from.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time


def test_fantasy_football_scout():
    """Test https://www.fantasyfootballscout.co.uk/team-news"""
    print("\n" + "="*80)
    print("TESTING: Fantasy Football Scout")
    print("="*80)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get('https://www.fantasyfootballscout.co.uk/team-news')
        time.sleep(3)
        
        # Check for team sections
        teams = driver.find_elements(By.CSS_SELECTOR, '[class*="team"]')
        print(f"✓ Found {len(teams)} potential team sections")
        
        # Look for player names
        players = driver.find_elements(By.CSS_SELECTOR, '[class*="player"], [class*="avatar"]')
        print(f"✓ Found {len(players)} potential players")
        
        # Check for injury/status info
        injuries = driver.find_elements(By.CSS_SELECTOR, '[class*="injury"], [class*="doubt"], [class*="out"]')
        print(f"✓ Found {len(injuries)} injury/status elements")
        
        # Sample structure
        page_source = driver.page_source[:2000]
        print(f"\n📋 Page structure preview:")
        print(f"   - Contains 'predicted': {'predicted' in page_source.lower()}")
        print(f"   - Contains 'lineup': {'lineup' in page_source.lower()}")
        print(f"   - Contains team badges: {'badge' in page_source.lower()}")
        
        return {'success': True, 'scrapable': True}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'success': False, 'scrapable': False, 'error': str(e)}
    finally:
        driver.quit()


def test_fantasy_football_pundit():
    """Test https://www.fantasyfootballpundit.com/fantasy-premier-league-team-news/"""
    print("\n" + "="*80)
    print("TESTING: Fantasy Football Pundit")
    print("="*80)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get('https://www.fantasyfootballpundit.com/fantasy-premier-league-team-news/')
        time.sleep(3)
        
        # Look for content structure
        articles = driver.find_elements(By.TAG_NAME, 'article')
        print(f"✓ Found {len(articles)} articles")
        
        # Look for team names
        headings = driver.find_elements(By.CSS_SELECTOR, 'h2, h3, h4')
        team_count = len([h for h in headings if h.text and len(h.text.split()) <= 3])
        print(f"✓ Found {team_count} potential team headings")
        
        # Check page structure
        page_source = driver.page_source[:2000]
        print(f"\n📋 Page structure preview:")
        print(f"   - Contains 'lineup': {'lineup' in page_source.lower()}")
        print(f"   - Contains 'predicted': {'predicted' in page_source.lower()}")
        print(f"   - Contains 'formation': {'formation' in page_source.lower()}")
        
        return {'success': True, 'scrapable': len(articles) > 0}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'success': False, 'scrapable': False, 'error': str(e)}
    finally:
        driver.quit()


def test_ingenuity_fantasy():
    """Test https://ingenuityfantasy.com/game-week-tips/premier-league-predicted-lineups/"""
    print("\n" + "="*80)
    print("TESTING: Ingenuity Fantasy")
    print("="*80)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get('https://ingenuityfantasy.com/game-week-tips/premier-league-predicted-lineups/')
        time.sleep(3)
        
        # Look for lineup elements
        lineups = driver.find_elements(By.CSS_SELECTOR, '[class*="lineup"], [class*="formation"]')
        print(f"✓ Found {len(lineups)} lineup elements")
        
        # Look for team sections
        teams = driver.find_elements(By.CSS_SELECTOR, 'h2, h3, [class*="team"]')
        print(f"✓ Found {len(teams)} potential team sections")
        
        page_source = driver.page_source[:2000]
        print(f"\n📋 Page structure preview:")
        print(f"   - Contains 'predicted': {'predicted' in page_source.lower()}")
        print(f"   - Contains 'lineup': {'lineup' in page_source.lower()}")
        
        return {'success': True, 'scrapable': len(lineups) > 0 or len(teams) > 0}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'success': False, 'scrapable': False, 'error': str(e)}
    finally:
        driver.quit()


def test_whoscored():
    """Test https://www.whoscored.com/articles/..."""
    print("\n" + "="*80)
    print("TESTING: WhoScored")
    print("="*80)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    
    try:
        url = 'https://www.whoscored.com/articles/_F34d_IBoUmqP3ZkgcovCw/show/fpl-gw22-premier-league-predicted-lineups-team-news'
        driver.get(url)
        time.sleep(5)  # WhoScored might need more time
        
        # Look for article content
        content = driver.find_elements(By.CSS_SELECTOR, '[class*="article"], [class*="content"]')
        print(f"✓ Found {len(content)} content sections")
        
        # Look for team/player info
        text_elements = driver.find_elements(By.CSS_SELECTOR, 'p, div')
        has_lineup_text = any('lineup' in elem.text.lower() for elem in text_elements[:50] if elem.text)
        print(f"✓ Contains lineup text: {has_lineup_text}")
        
        page_source = driver.page_source[:2000]
        print(f"\n📋 Page structure preview:")
        print(f"   - Contains 'predicted': {'predicted' in page_source.lower()}")
        print(f"   - Contains 'formation': {'formation' in page_source.lower()}")
        
        return {'success': True, 'scrapable': has_lineup_text}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'success': False, 'scrapable': False, 'error': str(e)}
    finally:
        driver.quit()


def test_fpledits():
    """Test https://fpledits.com/predicted-lineups-pl"""
    print("\n" + "="*80)
    print("TESTING: FPL Edits")
    print("="*80)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get('https://fpledits.com/predicted-lineups-pl')
        time.sleep(4)
        
        # Look for lineup cards/sections
        lineups = driver.find_elements(By.CSS_SELECTOR, '[class*="lineup"], [class*="match"], [class*="fixture"]')
        print(f"✓ Found {len(lineups)} lineup/match elements")
        
        # Look for team badges/names
        teams = driver.find_elements(By.CSS_SELECTOR, '[class*="team"], [class*="badge"]')
        print(f"✓ Found {len(teams)} team elements")
        
        # Look for player elements
        players = driver.find_elements(By.CSS_SELECTOR, '[class*="player"]')
        print(f"✓ Found {len(players)} player elements")
        
        page_source = driver.page_source[:2000]
        print(f"\n📋 Page structure preview:")
        print(f"   - Contains 'predicted': {'predicted' in page_source.lower()}")
        print(f"   - Contains 'lineup': {'lineup' in page_source.lower()}")
        
        return {'success': True, 'scrapable': len(lineups) > 0 or len(players) > 0}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'success': False, 'scrapable': False, 'error': str(e)}
    finally:
        driver.quit()


if __name__ == '__main__':
    print("🔍 TESTING MULTIPLE PREDICTED LINEUP SOURCES")
    print("="*80)
    
    results = {}
    
    # Test each source
    sources = [
        ('Fantasy Football Scout', test_fantasy_football_scout),
        ('Fantasy Football Pundit', test_fantasy_football_pundit),
        ('Ingenuity Fantasy', test_ingenuity_fantasy),
        ('WhoScored', test_whoscored),
        ('FPL Edits', test_fpledits)
    ]
    
    for name, test_func in sources:
        try:
            result = test_func()
            results[name] = result
        except Exception as e:
            print(f"\n❌ {name} test failed completely: {e}")
            results[name] = {'success': False, 'scrapable': False}
        
        time.sleep(2)  # Be nice to servers
    
    # Summary
    print("\n" + "="*80)
    print("📊 SUMMARY OF RESULTS")
    print("="*80)
    
    for name, result in results.items():
        status = "✅ SCRAPABLE" if result.get('scrapable') else "❌ NOT SCRAPABLE"
        print(f"{name:30} {status}")
    
    print("\n" + "="*80)
    print("RECOMMENDATIONS:")
    print("="*80)
    
    scrapable = [name for name, r in results.items() if r.get('scrapable')]
    
    if scrapable:
        print(f"\n✅ {len(scrapable)} sources ready to implement:")
        for i, name in enumerate(scrapable, 1):
            print(f"   {i}. {name}")
        print("\n💡 Recommended priority order (based on reliability):")
        priority = [s for s in ['Fantasy Football Scout', 'FPL Edits', 'Ingenuity Fantasy'] if s in scrapable]
        for i, name in enumerate(priority, 1):
            print(f"   {i}. {name}")
    else:
        print("⚠️ No easily scrapable sources found. May need different approach.")
    
    print("\n" + "="*80)
