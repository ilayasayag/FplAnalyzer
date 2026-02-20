# 🎯 Predicted Lineups System - Production Ready

## ✅ Status: WORKING

The predicted lineups scraper is now fully functional and integrated.

---

## 🚀 Quick Start

### Test the System:
```bash
cd /Users/ilay/RiderProjects/fpl_analyzer
source .venv/bin/activate
python test_production_scraper.py --gameweek 22
```

### Start the Server:
```bash
python run_server.py --debug
```

### Manual Refresh (via API):
```bash
curl -X POST http://localhost:5000/api/predicted-lineups/refresh/22
```

---

## 📊 What's Working

### 1. **Data Scraping** ✅
- **RotoWire**: 339 predictions per gameweek
- **Premier Injuries**: Injury/suspension data for all teams
- **Smart Merging**: Overrides predictions with injury data

### 2. **Database** ✅
- `predicted_lineups` table with all data
- Gameweek isolation
- Source tracking
- Probability storage

### 3. **API Endpoints** ✅
- `GET /api/predicted-lineups/<gameweek>` - Get all predictions
- `POST /api/predicted-lineups/refresh/<gameweek>` - Manual refresh
- `GET /api/predicted-lineups/player/<player_id>/<gameweek>` - Player-specific

### 4. **Scheduler** ✅
- Runs every 6 hours
- Daily at 6:00 AM
- Automatic updates

---

## 🗂️ Key Files

| File | Purpose |
|------|---------|
| `fpl_predictor/scrapers/production_scraper.py` | Main scraper (RotoWire + injuries) |
| `fpl_predictor/scrapers/lineup_scraper.py` | Original RotoWire scraper |
| `fpl_predictor/scrapers/aggregator.py` | Data aggregation & normalization |
| `fpl_predictor/data/repository.py` | Database access (`PredictedLineupRepository`) |
| `fpl_predictor/scheduler.py` | Background task scheduler |
| `test_production_scraper.py` | Full pipeline test |
| `test_predicted_lineups.py` | Original comprehensive test |

---

## 📈 Data Flow

```
RotoWire (339 predictions)
    ↓
Premier Injuries (injury data)
    ↓
Smart Merger (override injured players)
    ↓
Aggregator (normalize names & teams)
    ↓
FPL Player Matching (match to your DB)
    ↓
Database Storage (predicted_lineups table)
    ↓
API Endpoints (frontend ready)
```

---

## 🎨 Next Steps (TODO)

### 1. **Frontend UI** (2-3 hours)
- [ ] Create "Predicted Lineups" tab in `fpl_fixture_analyzer.html`
- [ ] Show team-by-team lineups
- [ ] Display injury status icons (🔴 OUT, 🟡 DOUBT, 🟢 CONFIRMED)
- [ ] Add lineup probability bars

### 2. **Prediction Integration** (1 hour)
- [ ] Add lineup probability multipliers to prediction engine
- [ ] Reduce expected points for doubtful players
- [ ] Show warning icons on player cards

### 3. **Visual Enhancements** (30 min)
- [ ] Add lineup status badges to all player cards
- [ ] Color-code players by injury status
- [ ] Show "% chance to start" in player details

---

## 🔧 Technical Details

### Scraper Structure:
- **Parent Container**: `div.lineup` (each match)
- **Team Names**: `.lineup__abbr` (2 per match)
- **Players**: `.lineup__main > ul.lineup__list.is-home/is-visit > li.lineup__player`
- **Injury Data**: `.lineup__inj` within player elements

### Database Schema:
```sql
CREATE TABLE predicted_lineups (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    fixture_id INTEGER,
    start_probability FLOAT NOT NULL,  -- 0.0 to 1.0
    bench_probability FLOAT,
    injured BOOLEAN DEFAULT FALSE,
    injury_details TEXT,
    suspended BOOLEAN DEFAULT FALSE,
    doubtful BOOLEAN DEFAULT FALSE,
    sources_count INTEGER,
    sources_data TEXT,  -- JSON
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, gameweek, fixture_id)
);
```

---

## 🐛 Troubleshooting

### Scraper Returns 0 Predictions:
1. Check if RotoWire changed their HTML structure
2. Run with `headless=False` to see what's happening
3. Check `/tmp/rotowire_failed.html` for debugging

### Database Errors:
```bash
# Re-initialize schema
python -c "from fpl_predictor.data.database import get_connection, init_schema; init_schema(get_connection())"
```

### API Not Working:
1. Ensure server is running
2. Check if data is in database
3. Verify gameweek number is correct

---

## 📊 Expected Results

### After Running Test:
```
✅ RotoWire: 339 predictions
✅ Premier Injuries: 40+ injury records
✅ Merger: 40+ enhanced predictions
✅ Aggregation: 339 processed
✅ Matching: 300+ matched to FPL IDs
✅ Database: All stored successfully

Time: ~20 seconds
```

---

## 🎯 Production Deployment

1. **Automatic Updates**: Already configured (6-hour + daily 6 AM)
2. **Manual Refresh**: `POST /api/predicted-lineups/refresh/<gw>`
3. **Frontend Access**: API ready for JavaScript client
4. **Monitoring**: Check logs for scraper errors

---

## 📚 Resources

- **RotoWire**: https://www.rotowire.com/soccer/lineups.php
- **Premier Injuries**: https://www.premierinjuries.com/injury-table.php
- **Documentation**: See `SCRAPER_FIX_EXPLAINED.md` for technical details

---

**Status**: ✅ Production Ready - Frontend Integration Pending
