#!/usr/bin/env python3
import os
import sys
import time
import requests
import firebase_admin
from firebase_admin import firestore

# Point exclusively to the local Firestore emulator
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"

# Initialize Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})

db = firestore.client(database_id="gamedb")

# API Keys
API_KEY = "73314c7b7198d9a5f4248e44a1fb63c9"
HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json",
}

POS_MAP = {"Goalkeeper": 1, "Defender": 2, "Midfielder": 3, "Attacker": 4}
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# All 48 qualified nations and their correct API IDs
QUALIFIED_TEAMS = {
    1: {"name": "Belgium", "code": "BEL", "group": "A"},
    2: {"name": "France", "code": "FRA", "group": "B"},
    3: {"name": "Croatia", "code": "CRO", "group": "C"},
    5: {"name": "Sweden", "code": "SWE", "group": "D"},
    6: {"name": "Brazil", "code": "BRA", "group": "E"},
    7: {"name": "Uruguay", "code": "URU", "group": "F"},
    8: {"name": "Colombia", "code": "COL", "group": "G"},
    9: {"name": "Spain", "code": "SPA", "group": "H"},
    10: {"name": "England", "code": "ENG", "group": "I"},
    11: {"name": "Panama", "code": "PAN", "group": "J"},
    12: {"name": "Japan", "code": "JAP", "group": "K"},
    13: {"name": "Senegal", "code": "SEN", "group": "L"},
    15: {"name": "Switzerland", "code": "SWI", "group": "A"},
    16: {"name": "Mexico", "code": "MEX", "group": "B"},
    17: {"name": "South Korea", "code": "KOR", "group": "C"},
    20: {"name": "Australia", "code": "AUS", "group": "D"},
    22: {"name": "Iran", "code": "IRA", "group": "E"},
    23: {"name": "Saudi Arabia", "code": "SAU", "group": "F"},
    25: {"name": "Germany", "code": "GER", "group": "G"},
    26: {"name": "Argentina", "code": "ARG", "group": "H"},
    27: {"name": "Portugal", "code": "POR", "group": "I"},
    28: {"name": "Tunisia", "code": "TUN", "group": "J"},
    31: {"name": "Morocco", "code": "MOR", "group": "K"},
    32: {"name": "Egypt", "code": "EGY", "group": "L"},
    775: {"name": "Austria", "code": "AUT", "group": "A"},
    770: {"name": "Czech Republic", "code": "CZE", "group": "B"},
    777: {"name": "Turkey", "code": "TUR", "group": "C"},
    1090: {"name": "Norway", "code": "NOR", "group": "D"},
    1108: {"name": "Scotland", "code": "SCO", "group": "E"},
    1113: {"name": "Bosnia & Herzegovina", "code": "BOS", "group": "F"},
    1118: {"name": "Netherlands", "code": "NED", "group": "G"},
    1501: {"name": "Ivory Coast", "code": "CIV", "group": "H"},
    1504: {"name": "Ghana", "code": "GHA", "group": "I"},
    1508: {"name": "Congo DR", "code": "COD", "group": "J"},
    1531: {"name": "South Africa", "code": "RSA", "group": "K"},
    1532: {"name": "Algeria", "code": "ALG", "group": "L"},
    1533: {"name": "Cape Verde", "code": "CPV", "group": "A"},
    1548: {"name": "Jordan", "code": "JOR", "group": "B"},
    1567: {"name": "Iraq", "code": "IRQ", "group": "C"},
    1568: {"name": "Uzbekistan", "code": "UZB", "group": "D"},
    1569: {"name": "Qatar", "code": "QAT", "group": "E"},
    2380: {"name": "Paraguay", "code": "PAR", "group": "F"},
    2382: {"name": "Ecuador", "code": "ECU", "group": "G"},
    2384: {"name": "USA", "code": "USA", "group": "H"},
    2386: {"name": "Haiti", "code": "HAI", "group": "I"},
    4673: {"name": "New Zealand", "code": "NZL", "group": "J"},
    5529: {"name": "Canada", "code": "CAN", "group": "K"},
    5530: {"name": "Curaçao", "code": "CUW", "group": "L"}
}

# Top 30 teams we want to fetch real active squads for
TEAMS_TO_FETCH = [
    26, 6, 2, 10, 9, 25, 27, 1118, 1, 7, 8, 3, 1090, 1108, 15, 2384, 16, 5529, 31, 13, 777, 1501, 32, 28, 5, 1533, 1567, 1568, 5530, 2386
]

# Our custom draft rankings based on YouTubers aggregation + internet research
CUSTOM_DRAFT_RANKS = {
    # Forwards
    "Mikel Oyarzabal": 1, "Erling Haaland": 2, "Kylian Mbappé": 3, "Harry Kane": 4, "Lionel Messi": 5,
    "Kai Havertz": 6, "Cody Gakpo": 7, "Cristiano Ronaldo": 8, "Robert Lewandowski": 9, "Lautaro Martínez": 10,
    "Viktor Gyökeres": 11, "Breel Embolo": 12, "Julián Álvarez": 13, "Vinícius Júnior": 14, "Darwin Núñez": 15,
    "Romelu Lukaku": 16, "Loïs Openda": 17, "Santiago Giménez": 18, "Jonathan David": 19, "Christian Pulisic": 20,
    # Midfielders
    "Florian Wirtz": 21, "Raphinha": 22, "Bruno Fernandes": 23, "James Rodríguez": 24, "Michael Olise": 25,
    "Lamine Yamal": 26, "Kevin De Bruyne": 27, "Jamal Musiala": 28, "Nico Williams": 29, "Scott McTominay": 30,
    "Hakan Çalhanoğlu": 31, "Jude Bellingham": 32, "Bukayo Saka": 33, "Cole Palmer": 34, "Antoine Griezmann": 35,
    "Granit Xhaka": 36, "Endrick": 37, "Arda Güler": 38, "Phil Foden": 39, "Declan Rice": 40,
    # Defenders
    "Marc Cucurella": 41, "Joshua Kimmich": 42, "Ali Abdi": 43, "Denzel Dumfries": 44, "Virgil van Dijk": 45,
    "Gabriel Magalhães": 46, "Gabriel": 47, "Pedro Porro": 48, "Johan Mojica": 49, "Dayot Upamecano": 50,
    "David Raum": 51, "Maxim De Cuyper": 52, "Daniel Muñoz": 53, "Nuno Mendes": 54, "Theo Hernández": 55,
    "Trent Alexander-Arnold": 56, "Nico O'Reilly": 57, "Achraf Hakimi": 58, "Nicolás Tagliafico": 59, "Cristian Romero": 60,
    # Goalkeepers
    "Camilo Vargas": 61, "Sergio Rochet": 62, "Diogo Costa": 63, "Emiliano Martínez": 64, "Bart Verbruggen": 65,
    "Ørjan Nyland": 66, "Mike Maignan": 67, "Jordan Pickford": 68, "Marc-André ter Stegen": 69, "Unai Simón": 70,
    "Alisson Becker": 71, "Jan Oblak": 72, "Yassine Bounou": 73, "Gianluigi Donnarumma": 74, "Gregor Kobel": 75
}

def clean_database():
    print("🧹 Cleaning existing 'wc_teams' and 'wc_players' in Firestore emulator...")
    
    # Clean players
    p_docs = db.collection("wc_players").get()
    for d in p_docs:
        d.reference.delete()
    print(f"🗑️ Deleted {len(p_docs)} players.")
    
    # Clean teams
    t_docs = db.collection("wc_teams").get()
    for d in t_docs:
        d.reference.delete()
    print(f"🗑️ Deleted {len(t_docs)} teams.")

def populate_teams():
    print("🌱 Registering all 48 qualified World Cup 2026 teams...")
    for tid, info in QUALIFIED_TEAMS.items():
        doc = {
            "id": tid,
            "name": info["name"],
            "logo": f"https://media.api-sports.io/football/teams/{tid}.png",
            "isoCode": info["code"],
            "group": info["group"],
            "eliminated": False,
            "eliminatedAfterGw": None,
            "groupFinished": False
        }
        db.collection("wc_teams").document(str(tid)).set(doc)
    print(f"✅ Registered {len(QUALIFIED_TEAMS)} teams successfully.")

def populate_players():
    print("🚀 Fetching real-world national squad players from api-sports.io...")
    total_added = 0
    
    for idx, tid in enumerate(TEAMS_TO_FETCH, 1):
        team_name = QUALIFIED_TEAMS[tid]["name"]
        team_code = QUALIFIED_TEAMS[tid]["code"]
        print(f"[{idx}/{len(TEAMS_TO_FETCH)}] Fetching squad for {team_name} (ID: {tid})...")
        
        url = "https://v3.football.api-sports.io/players/squads"
        params = {"team": tid}
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Failed to fetch {team_name} squad: {resp.status_code}")
                continue
                
            data = resp.json()
            response_list = data.get("response", [])
            if not response_list:
                print(f"⚠️ Empty squad returned for {team_name}")
                continue
                
            players_added = 0
            players = response_list[0].get("players", [])
            for p in players:
                pid = p.get("id")
                pname = p.get("name", "")
                raw_pos = p.get("position", "")
                pos_val = POS_MAP.get(raw_pos, 3) # default MID
                
                # Check for custom draft rank or default to 999
                draft_rank = 999
                for rec_name, rank in CUSTOM_DRAFT_RANKS.items():
                    if rec_name.lower() in pname.lower() or pname.lower() in rec_name.lower():
                        draft_rank = rank
                        break
                
                player_doc = {
                    "id": pid,
                    "name": pname,
                    "photo": p.get("photo", f"https://media.api-sports.io/football/players/{pid}.png"),
                    "position": pos_val,
                    "positionName": POS_NAMES[pos_val],
                    "teamId": tid,
                    "teamName": team_name,
                    "teamIso": team_code,
                    "eliminated": False,
                    "draftRank": draft_rank
                }
                
                db.collection("wc_players").document(str(pid)).set(player_doc)
                players_added += 1
                total_added += 1
                
            print(f"   Saved {players_added} real players for {team_name}.")
            
        except Exception as e:
            print(f"💥 Error fetching/saving squad for {team_name}: {e}")
            
        # Respect API Rate limit (10 req/min -> ~6.5s delay)
        time.sleep(6.5)

    print(f"\n✨ DONE! Successfully populated database with {total_added} official, active national team players.")

def main():
    clean_database()
    populate_teams()
    populate_players()

if __name__ == "__main__":
    main()
