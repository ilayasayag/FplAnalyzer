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

db = firestore.client(database_id=os.environ.get("FIRESTORE_DB_ID", "gamedb"))

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
        USER_UID = "u_netanel"
        USER_NAME = "Netanel"
        print("⚠️ No production user found. Defaulting to 'u_netanel'.")
except Exception as e:
    USER_UID = "u_netanel"
    USER_NAME = "Netanel"
    print(f"⚠️ Failed to list auth users ({e}). Defaulting to 'u_netanel'.")

# Wipe and re-seed both seeded leagues, but preserve real-user memberships
# in lg_mock_draft so people who joined via invite code aren't orphaned.
# AI-slot UIDs always start with "u_mk_" — those are safe to delete.
# Real users (any other UID) get their member doc and squad kept intact so
# they still see data after the reseed.

print("🧹 Saving real-user memberships from lg_mock_draft...")
saved_members = {}
saved_squads = {}
mock_ref = db.collection("leagues").document("lg_mock_draft")
for mdoc in mock_ref.collection("members").get():
    if not mdoc.id.startswith("u_mk_"):
        saved_members[mdoc.id] = mdoc.to_dict()
        squad_doc = mock_ref.collection("squads").document(mdoc.id).get()
        if squad_doc.exists:
            saved_squads[mdoc.id] = squad_doc.to_dict()
print(f"  Preserved {len(saved_members)} real-user member(s): {list(saved_members.keys())}")

for lid in ["lg_mock_draft", "lg_pre_draft"]:
    league_ref = db.collection("leagues").document(lid)
    for sub_name in ["members", "squads", "lineups", "scores", "standings", "knockout", "schedule"]:
        coll = league_ref.collection(sub_name)
        for doc in coll.get():
            doc.reference.delete()
    league_ref.delete()

# Run consolidated seed everything on production db
seed_everything(db, USER_UID, USER_NAME)

# Restore preserved real-user memberships into the freshly-seeded mock league.
# Source a fallback squad (u_roy is the "real user" slot in the mock draft).
print("♻️  Restoring real-user memberships to lg_mock_draft...")
fallback_squad = mock_ref.collection("squads").document("u_roy").get()
fallback_squad_data = fallback_squad.to_dict() if fallback_squad.exists else {"players": []}
for uid, member_data in saved_members.items():
    mock_ref.collection("members").document(uid).set(member_data)
    squad_data = saved_squads.get(uid, fallback_squad_data)
    mock_ref.collection("squads").document(uid).set(squad_data)
    print(f"  Restored {member_data.get('displayName', uid)} ({uid})")

print("\n✨ ALL PRODUCTION SEEDING PROCEDURES COMPLETED SUCCESSFULLY!")
