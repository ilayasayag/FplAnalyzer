# FPL Draft Analyzer

A comprehensive Fantasy Premier League (FPL) Draft analysis tool that provides squad optimization, fixture analysis, head-to-head comparisons, and trade suggestions.

## Features

### 🔄 FPL Draft API Integration
- Fetches data directly from the FPL Draft website using a bookmarklet
- Retrieves league details, player ownership, full player database
- Gets all team squads and detailed per-gameweek player statistics
- Tracks transaction history (trades, waivers, free agent pickups)

### 📊 Squad Analysis
- **N-K-D Score Analysis**: Evaluates squad strength based on:
  - N: Number of players with easy fixtures per gameweek
  - K: Minimum threshold for "good coverage"
  - D: Maximum team duplicates allowed
- Weighted scoring for "Always Start" players vs regular players
- Team distribution visualization
- Improvement suggestions

### 📅 Fixture Analysis
- Fixture difficulty ratings (easy/medium/hard)
- Team overlap detection
- Interactive fixture grid with manual override capabilities
- Dynamic adjustment based on current gameweek

### 🤝 Head-to-Head Comparison
- Squad comparison based on gameweek difficulty
- Predicted points per gameweek (using form, fixture difficulty, historical data)
- **Optimal 11 Selection**: Respects FPL formation rules (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD)
- Position strength comparison
- Team coverage analysis
- Key differentials identification

### 💱 Trade System
- Smart trade suggestions that benefit both parties
- **Interactive Trade Builder**: Select players and get return offer suggestions
- Fixture analysis for trade evaluation
- Value-based trade matching

### 📈 League Dashboard
- League standings and match history
- Recent transactions feed
- All-team N-K-D comparison
- Data persistence via localStorage

## How to Use

### Step 1: Generate the Bookmarklet
1. Open `fpl_fixture_analyzer.html` in your browser
2. Enter your FPL Draft League ID
3. Click "Generate Bookmarklet"
4. Drag the bookmarklet to your bookmarks bar (or right-click → Add to bookmarks)

### Step 2: Fetch Your League Data
1. Navigate to [FPL Draft](https://draft.premierleague.com)
2. Log in to your account
3. Click the bookmarklet from your bookmarks bar
4. Wait for data collection to complete
5. Copy the data to clipboard when prompted

### Step 3: Import Data
1. Return to the analyzer
2. Paste the data in the import section
3. Click "Import Combined Data"

### Step 4: Analyze!
- View league analysis with all team squads
- Run N-K-D analysis on any team
- Compare teams head-to-head
- Explore trade suggestions

## Files

- `fpl_fixture_analyzer.html` - Main application (single-file, self-contained)
- `unified_wishlist.json` - Combined player wishlist data
- `gk_wishlist.json` - Goalkeeper rankings
- `def_wishlist.json` - Defender rankings
- `mid_wishlist.json` - Midfielder rankings
- `fwd_wishlist.json` - Forward rankings

## Technical Details

- **Pure HTML/CSS/JavaScript** - No build process required
- **No external dependencies** - Runs entirely in the browser
- **LocalStorage persistence** - Data saved automatically
- **Bookmarklet approach** - Bypasses CORS restrictions

## Privacy

All data is processed locally in your browser. No data is sent to any external servers.

## License

MIT License - Feel free to use and modify for your FPL Draft leagues!

