#!/usr/bin/env python3
import os
import json
import datetime
from google.cloud import firestore

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

def main():
    print(f"🔌 Connecting to Production Firestore ({PROJECT} / database: {DATABASE})...")
    # Clean Firestore emulator env variables if they exist in the process,
    # so we don't accidentally query the local emulator instead of production.
    if "FIRESTORE_EMULATOR_HOST" in os.environ:
        del os.environ["FIRESTORE_EMULATOR_HOST"]
    if "FIREBASE_AUTH_EMULATOR_HOST" in os.environ:
        del os.environ["FIREBASE_AUTH_EMULATOR_HOST"]

    try:
        db = firestore.Client(project=PROJECT, database=DATABASE)
    except Exception as e:
        print(f"❌ Failed to initialize Firestore Client: {e}")
        print("Make sure you have authenticated your local shell using: gcloud auth application-default login")
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

    output_file = f"firestore_export_{datetime.date.today().isoformat()}.json"
    print(f"💾 Saving data to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("✅ Export completed successfully!")

if __name__ == "__main__":
    main()
