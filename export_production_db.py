#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import datetime
from google.cloud import firestore
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as TokenCredentials

# Reconfigure stdout/stderr to UTF-8 to prevent UnicodeEncodeError on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

PROJECT = "fpl-analyzer-792eb"
DATABASE = "gamedb"

ROOT_COLLECTIONS = {
    "wc_config": {},
    "wc_teams": {},
    "wc_players": {},
    "wc_fixtures": {"playerScores": {}},
    "leagues": {
        "members": {},
        "squads": {},
        "lineups": {},
        "scores": {},
        "schedule": {},
        "knockout": {},
        "standings": {},
        "transfer_windows": {},
        "transactions": {},
        "trades": {},
        "waivers": {},
        "draft": {"picks": {}}
    }
}

def serialize_value(val):
    if isinstance(val, datetime.datetime):
        return {"seconds": int(val.timestamp()), "nanoseconds": val.microsecond * 1000}
    elif isinstance(val, dict):
        return {k: serialize_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [serialize_value(v) for v in val]
    return val

def export_subcollections(doc_ref, spec):
    out = {}
    for name, child_spec in spec.items():
        sub_coll = doc_ref.collection(name)
        docs = list(sub_coll.get())
        if not docs:
            continue
        out[name] = {}
        for sdoc in docs:
            out[name][sdoc.id] = {
                "_data": serialize_value(sdoc.to_dict()),
                "_subcollections": export_subcollections(sdoc.reference, child_spec)
            }
    return out

def get_client():
    errs = []
    # Try 1: Plain Application Default Credentials (ADC)
    try:
        db = firestore.Client(project=PROJECT, database=DATABASE)
        # Test read to verify permissions
        list(db.collection("wc_config").limit(1).get())
        return db
    except Exception as e:
        errs.append(f"Plain ADC failed: {e}")

    # Try 2: Service account credentials from GOOGLE_APPLICATION_CREDENTIALS
    sa = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sa and os.path.exists(sa):
        try:
            creds = service_account.Credentials.from_service_account_file(sa)
            db = firestore.Client(project=PROJECT, credentials=creds, database=DATABASE)
            list(db.collection("wc_config").limit(1).get())
            return db
        except Exception as e:
            errs.append(f"SA file credentials failed: {e}")

    # Try 3: gcloud print-access-token fallback
    try:
        tok = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        db = firestore.Client(project=PROJECT, credentials=TokenCredentials(token=tok), database=DATABASE)
        list(db.collection("wc_config").limit(1).get())
        return db
    except Exception as e:
        errs.append(f"gcloud access token fallback failed: {e}")

    raise ValueError(f"All authentication methods failed:\n" + "\n".join(f"  - {err}" for err in errs))

def main():
    print(f"🔌 Connecting to Production Firestore ({PROJECT} / database: {DATABASE})...")
    # Clean Firestore emulator env variables if they exist in the process,
    # so we don't accidentally query the local emulator instead of production.
    if "FIRESTORE_EMULATOR_HOST" in os.environ:
        del os.environ["FIRESTORE_EMULATOR_HOST"]
    if "FIREBASE_AUTH_EMULATOR_HOST" in os.environ:
        del os.environ["FIREBASE_AUTH_EMULATOR_HOST"]

    try:
        db = get_client()
    except Exception as e:
        print(f"❌ Failed to initialize Firestore Client: {e}")
        print("Authenticate with the firebase-adminsdk service account, then retry:")
        print("  GOOGLE_APPLICATION_CREDENTIALS=/path/to/fpl-analyzer-792eb-firebase-adminsdk-*.json")
        print("  (or `gcloud auth login` as the firebase-adminsdk SA). Bare ADC → 403.")
        return

    data = {}
    for col_name, spec in ROOT_COLLECTIONS.items():
        print(f"📦 Exporting collection: {col_name}...")
        try:
            coll = db.collection(col_name)
            docs = list(coll.get())
            data[col_name] = {}
            for doc in docs:
                data[col_name][doc.id] = {
                    "_data": serialize_value(doc.to_dict()),
                    "_subcollections": export_subcollections(doc.reference, spec)
                }
        except Exception as e:
            print(f"❌ Failed to export collection '{col_name}': {e}")
            print("Make sure you are logged in and have access permissions.")
            return

    output_dir = "exports"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"firestore_export_{datetime.date.today().isoformat()}.json")
    print(f"💾 Saving data to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("✅ Export completed successfully!")

if __name__ == "__main__":
    main()
