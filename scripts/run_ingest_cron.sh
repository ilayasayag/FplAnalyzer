#!/bin/bash
# Wrapper for launchd/cron: ensures gcloud + venv are on PATH, runs one pass.
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/ilay/RiderProjects/fpl_analyzer || exit 1
# Keep the Mac awake until the next tick (StartInterval=600s): this assertion
# expires in 660s, so each run renews it before the previous one lapses,
# preventing the overnight-sleep gaps that block WhoScored DefCon scoring.
/usr/bin/caffeinate -i -t 660 &
/Users/ilay/RiderProjects/fpl_analyzer/.venv/bin/python scripts/ingest_live_scores.py

# Window tick: fires the wishlist auto-run when the Free-agents window is open
# and that GW's auction hasn't run (idempotent server-side lease — extra ticks
# are no-ops). Goes through the DEPLOYED API so only merged code ever resolves
# an auction. Secret = wc_config/cron.secret, mirrored once into
# ~/.wc_cron_secret (chmod 600); silently skipped if that file is absent.
# See OPS_RUNBOOK.md "Wishlist auto-run".
if [ -f "$HOME/.wc_cron_secret" ]; then
  curl -sS -m 120 "https://fpl-analyzer-792eb.web.app/api/v1/wc/cron/window-tick?key=$(cat "$HOME/.wc_cron_secret")" \
    >> /tmp/wc_window_tick.log 2>&1 || true
  echo "" >> /tmp/wc_window_tick.log
fi
