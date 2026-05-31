#!/usr/bin/env python3
import os
import sys
import firebase_admin
from firebase_admin import firestore, auth
from fpl_predictor.seed.seed_league import seed_everything

# Connect to Production Firestore (database: gamedb)
print("📤 Connecting to Production Firebase (fpl-analyzer-792eb)...")
if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})

db = firestore.client()

# Retrieve first authenticated production user to seed
print("👤 Checking production Auth users list...")
try:
    auth_users = auth.list_users().users
    user_list = [u for u in auth_users]
    if user_list:
        real_user = user_list[0]
        USER_UID = real_user.uid
        USER_NAME = real_user.display_name or real_user.email.split("@")[0]
        print(f"🎯 Found production user: {USER_NAME} (UID: {USER_UID})")
    else:
        USER_UID = "u_roy"
        USER_NAME = "Roy"
        print("⚠️ No production user found. Defaulting to 'u_roy'.")
except Exception as e:
    USER_UID = "u_roy"
    USER_NAME = "Roy"
    print(f"⚠️ Failed to list auth users ({e}). Defaulting to 'u_roy'.")

# Force complete delete of mock leagues in production before seeding
for lid in ["lg_mock_draft", "lg_pre_draft"]:
    mock_league_ref = db.collection("leagues").document(lid)
    for sub_name in ["members", "squads", "lineups", "scores", "standings", "knockout", "schedule"]:
        coll = mock_league_ref.collection(sub_name)
        for doc in coll.get():
            doc.reference.delete()
    mock_league_ref.delete()

# Run consolidated seed everything on production db
seed_everything(db, USER_UID, USER_NAME)

print("\n✨ ALL PRODUCTION SEEDING PROCEDURES COMPLETED SUCCESSFULLY!")
