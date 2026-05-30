#!/usr/bin/env python3
import os
import firebase_admin
from firebase_admin import firestore
from fpl_predictor.seed.seed_league import seed_everything

# Point exclusively to the local Firestore emulator
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"

# Initialize Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})

db = firestore.client(database_id="gamedb")

# Clear collections
print("🧹 Cleaning local emulator collections...")
for col in ["wc_teams", "wc_players", "wc_fixtures", "leagues", "users", "wc_config"]:
    docs = db.collection(col).get()
    for doc in docs:
        if col == "leagues":
            for subcol in ["members", "squads", "lineups", "scores", "schedule", "knockout", "transfer_windows", "transactions", "standings"]:
                subdocs = doc.reference.collection(subcol).get()
                for sdoc in subdocs:
                    sdoc.reference.delete()
        doc.reference.delete()
print("✨ Local collections cleared.")

seed_everything(db, "u_roy", "Roy")
print("✅ Successfully seeded Emulator database!")
