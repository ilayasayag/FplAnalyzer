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
    from google.auth.credentials import AnonymousCredentials
    firebase_admin.initialize_app(credential=AnonymousCredentials(), options={"projectId": "fpl-analyzer-792eb"})

# Match the Flask backend's database target so seeded data is visible to the
# API (Flask defaults to (default); the emulator serves a separate store per
# database_id, so writing to (default) here is required).
db = firestore.client(database_id=os.environ.get("FIRESTORE_DB_ID", "(default)"))

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

from firebase_admin import auth as fb_auth

# Create local emulator user for Netanel
try:
    fb_auth.create_user(
        uid="u_netanel",
        email="netanel@wc2026.local",
        password="password123",
        display_name="Netanel"
    )
    print("👤 Created local emulator user: netanel@wc2026.local")
except Exception as e:
    # If the user already exists in the emulator store (e.g. from previous run), ignore the error
    print(f"ℹ️ Local user netanel@wc2026.local already exists or: {e}")

seed_everything(db, "u_netanel", "Netanel")
print("✅ Successfully seeded Emulator database!")
