#!/bin/bash
echo "=========================================="
echo "Reset Database & Run Full Pipeline Test"
echo "=========================================="
echo ""

cd /Users/ilay/RiderProjects/fpl_analyzer

# Delete old database file
echo "1. Deleting old database file..."
rm -f fpl_data.duckdb
rm -f fpl_data.duckdb.wal
echo "   ✅ Database deleted"
echo ""

# Activate venv
source .venv/bin/activate

# Run test (will auto-import FPL data from JSON if database is empty)
echo "2. Running test with fresh database..."
echo "   (Test will auto-import FPL data from JSON)"
echo ""
python test_production_scraper.py --gameweek 22

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
echo "If successful, you should see:"
echo "  ✅ 339 predictions scraped"
echo "  ✅ 336 aggregated"
echo "  ✅ 250+ matched to FPL players"
echo "  ✅ 250+ stored in database"
