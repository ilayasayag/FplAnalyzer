#!/bin/bash
echo "=========================================="
echo "Full Pipeline Test - Predicted Lineups"
echo "=========================================="
echo ""

cd /Users/ilay/RiderProjects/fpl_analyzer
source .venv/bin/activate

echo "Running comprehensive test..."
echo ""

python test_production_scraper.py --gameweek 22

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check the results above"
echo "2. If successful, proceed to frontend integration"
echo "3. Start server: python run_server.py --debug"
