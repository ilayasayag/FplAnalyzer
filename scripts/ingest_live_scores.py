#!/usr/bin/env python3
"""Standalone live-scoring cron — no server needed.

Fetches FIFA fantasy round points + ESPN stat lines and writes them to prod
Firestore (gamedb). Schedule on match days, e.g. every 10 min during the match
window and a final pass ~1h after the last kickoff:

    */10 14-23 * * *  cd /path/to/fpl_analyzer && \
        GOOGLE_APPLICATION_CREDENTIALS=secrets.json .venv/bin/python \
        scripts/ingest_live_scores.py >> /tmp/wc_ingest.log 2>&1

Usage:
    python scripts/ingest_live_scores.py            # current GW, today (UTC)
    python scripts/ingest_live_scores.py --gw 1 --date 20260611
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin
from firebase_admin import credentials, firestore
from fpl_predictor.data.wc_live_ingest import ingest_live

PROJECT = "fpl-analyzer-792eb"


def _db():
    if not firebase_admin._apps:
        sa = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "secrets.json")
        if os.path.exists(sa):
            firebase_admin.initialize_app(credentials.Certificate(sa))
        else:
            firebase_admin.initialize_app(options={"projectId": PROJECT})
    return firestore.client(database_id="gamedb")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gw", type=int, default=None)
    ap.add_argument("--date", default=None, help="YYYYMMDD (UTC); default today")
    args = ap.parse_args()

    db = _db()
    gw = args.gw
    if gw is None:
        lg = db.collection("leagues").document("lg_mock_draft").get()
        gw = (lg.to_dict() or {}).get("currentGw", 1) if lg.exists else 1
    date = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res = ingest_live(db, int(gw), str(date))
    print(f"[{stamp}] gw={gw} date={date} -> "
          f"fixtures={res['fixturesTouched']} "
          f"scores={res['playerScoresWritten']} "
          f"leagues={res['leaguesUpdated']}")


if __name__ == "__main__":
    main()
