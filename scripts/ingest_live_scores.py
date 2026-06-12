#!/usr/bin/env python3
"""Scheduled live-scoring runner — NO LLM, just Python + free public data.

One pass: refresh the WhoScored match-id map (cheap, daily-ish), then score
every live / recently-finished WC fixture from WhoScored (DefCon + FIFA points)
or ESPN as fallback. Idempotent + non-finalizing, so running it every ~10 min
during matches and for an hour after is safe and free.

Cron (every 10 min, 13:00–02:00 UTC covers all WC kickoff windows + 1h after):
    */10 13-23,0-2 * * *  cd /path/to/fpl_analyzer && \
      GOOGLE_APPLICATION_CREDENTIALS=secrets.json .venv/bin/python \
      scripts/ingest_live_scores.py >> /tmp/wc_ingest.log 2>&1
"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json as _json
from google.cloud import firestore

PROJECT = "fpl-analyzer-792eb"
from fpl_predictor.data.wc_live_ingest import run_scheduled_ingest, discover_whoscored_ids


def _db():
    """Firestore (gamedb) via a real service-account JSON if one is configured,
    else Application Default Credentials (`gcloud auth application-default
    login`). Never the API-keys secrets.json (that is not an SA cert)."""
    sa = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if sa and os.path.exists(sa):
        try:
            if _json.load(open(sa)).get("type") == "service_account":
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(sa)
                return firestore.Client(project=PROJECT, credentials=creds, database="gamedb")
        except Exception:
            pass
    # Otherwise use the gcloud CLI's active-account access token (the same
    # identity used interactively). Refreshed each run, so a 10-min cron always
    # has a valid ~1h token. Requires `gcloud auth login` once on the host.
    import subprocess
    try:
        tok = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True).strip()
        from google.oauth2.credentials import Credentials
        return firestore.Client(project=PROJECT,
                                credentials=Credentials(token=tok), database="gamedb")
    except Exception:
        return firestore.Client(project=PROJECT, database="gamedb")  # last resort: ADC


def main():
    db = _db()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # refresh the WhoScored id map (new matches appear as the calendar advances)
    try:
        disc = discover_whoscored_ids(db)
    except Exception as e:
        disc = {"error": str(e)}
    res = run_scheduled_ingest(db)
    scored = [s for s in res.get("scored", []) if s.get("n") or s.get("via")]
    print(f"[{stamp}] gw={res['gw']} map={disc.get('matched','?')} "
          f"scored={scored} skipped={len(res.get('skipped',[]))}")


if __name__ == "__main__":
    main()
