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
#
# IMPORTANT: do NOT clone another manager's squad as a fallback. The old code
# copied u_roy's squad onto every preserved user who lacked a saved squad,
# which produced several managers sharing an identical 15-man squad (broke the
# propose-trade UI and trade execution — see dedup_squads_migration.py). Each
# restored user now gets a DISJOINT squad drawn from the unowned player pool,
# and any previously-saved squad that overlaps existing ownership is rebuilt.
import json as _json

_seeded_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fpl_predictor", "data", "wc_seeded_data.json",
)
with open(_seeded_path, "r", encoding="utf-8") as _f:
    _ALL_PLAYERS = _json.load(_f).get("players", [])

_NEED = {1: 2, 2: 5, 3: 5, 4: 3}  # GK / DEF / MID / FWD


def _current_owned_ids():
    owned = set()
    for sdoc in mock_ref.collection("squads").get():
        for p in (sdoc.to_dict() or {}).get("players", []):
            owned.add(int(p["playerId"]))
    return owned


def _build_disjoint_squad(owned):
    avail = [p for p in _ALL_PLAYERS
             if int(p["id"]) not in owned and not p.get("eliminated")]
    avail.sort(key=lambda p: (p.get("draftRank", 999), int(p["id"])))
    squad_list = []
    for pos, n in _NEED.items():
        chosen = [p for p in avail if int(p["position"]) == pos][:n]
        if len(chosen) < n:
            raise RuntimeError(f"not enough free players for position {pos}")
        for p in chosen:
            squad_list.append({
                "playerId": int(p["id"]),
                "draftedRound": (len(squad_list) // 8) + 1,
                "position": int(p["position"]),
                "name": p["name"],
                "positionName": p["positionName"],
                "teamIso": p.get("teamIso", ""),
                "eliminated": False,
                "teamId": p.get("teamId", 0),
                "teamName": p.get("teamName", ""),
            })
    return squad_list


print("♻️  Restoring real-user memberships to lg_mock_draft...")
for uid, member_data in saved_members.items():
    mock_ref.collection("members").document(uid).set(member_data)
    owned = _current_owned_ids()  # re-read each loop so users stay disjoint
    saved = saved_squads.get(uid) or {}
    saved_players = saved.get("players") or []
    saved_ids = {int(p["playerId"]) for p in saved_players}
    if saved_players and not (saved_ids & owned):
        squad_data = {"players": saved_players}        # disjoint — keep as-is
        note = "kept saved squad"
    else:
        squad_data = {"players": _build_disjoint_squad(owned)}  # rebuild fresh
        note = "missing/overlapping squad — rebuilt disjoint"
    mock_ref.collection("squads").document(uid).set(squad_data)
    print(f"  Restored {member_data.get('displayName', uid)} ({uid}) — {note}")

print("\n✨ ALL PRODUCTION SEEDING PROCEDURES COMPLETED SUCCESSFULLY!")
