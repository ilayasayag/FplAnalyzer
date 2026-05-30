import os
import json
import firebase_admin
from firebase_admin import firestore

print("📥 Reading teams and players from local emulator...")
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
emulator_app = firebase_admin.initialize_app(
    options={"projectId": "fpl-analyzer-792eb"},
    name="emulator"
)
emulator_db = firestore.client(app=emulator_app, database_id="gamedb")

teams = [d.to_dict() for d in emulator_db.collection("wc_teams").get()]
players = [d.to_dict() for d in emulator_db.collection("wc_players").get()]

data = {
    "teams": teams,
    "players": players
}

output_path = os.path.join(os.path.dirname(__file__), "..", "fpl_predictor", "data", "wc_seeded_data.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Exported {len(teams)} teams and {len(players)} players to {output_path}")
