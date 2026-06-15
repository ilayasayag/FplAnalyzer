#!/bin/bash
# Wrapper for launchd/cron: ensures gcloud + venv are on PATH, runs one pass.
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/ilay/RiderProjects/fpl_analyzer || exit 1
# Keep the Mac awake until the next tick (StartInterval=600s): this assertion
# expires in 660s, so each run renews it before the previous one lapses,
# preventing the overnight-sleep gaps that block WhoScored DefCon scoring.
/usr/bin/caffeinate -i -t 660 &
/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python scripts/ingest_live_scores.py
