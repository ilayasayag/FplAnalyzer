import json

# Load mapped draft
with open("scratch/mapped_draft.json") as f:
    draft = json.load(f)

# Hardcode the missing players' mappings
missing = {
    "Bukayo Saka": {"id": 99901, "name": "Bukayo Saka", "position": 3, "positionName": "MID", "teamIso": "ENG"},
    "Cristiano Ronaldo": {"id": 99902, "name": "Cristiano Ronaldo", "position": 4, "positionName": "FWD", "teamIso": "POR"},
    "Harry Kane": {"id": 99903, "name": "Harry Kane", "position": 4, "positionName": "FWD", "teamIso": "ENG"}
}
for k, v in missing.items():
    draft[k] = v

# Goalscorer and assist maps for GW1, GW2, GW3
# (match_id, player_name, 'goal'/'assist')
events_gw1 = [
    # Spain 4-1 Cape Verde
    ("Pedri", "goal"), ("Aymeric Laporte", "goal"), ("Borja Iglesias", "goal"),
    # Spain assists: Martín Zubimendi (2), Borja Iglesias (1), Álex Grimaldo (1)
    ("Borja Iglesias", "assist"),
    # Cape Verde: Willy Semedo goal
    ("Willy Semedo", "goal"),
    # Norway 3-1 Iraq
    ("E. Haaland", "goal"), # fuzzy match or assumed
    ("Amir Al Ammari", "assist"),
    # Colombia 5-0 Uzbekistan
    ("J. Rodríguez", "assist"),
    # France 5-0 Senegal
    ("A. Tchouaméni", "assist"), ("Kylian Mbappé", "goal"), ("O. Dembélé", "assist"), ("A. Rabiot", "goal"), ("A. Rabiot", "assist"),
    # Uruguay 4-1 Saudi Arabia
    ("D. Núñez", "goal"),
    # Brazil 5-0 Morocco
    ("Gabriel Martinelli", "goal"), ("Raphinha", "goal"),
    # Portugal 6-0 Congo DR
    ("Gonçalo Ramos", "goal"), ("Gonçalo Ramos", "goal"), ("João Neves", "goal"), ("João Neves", "assist"), ("Rúben Neves", "goal"),
    # Switzerland 2-1 Qatar
    ("A. Jashari", "assist"),
    # England 4-1 Haiti
    ("P. Foden", "goal"), ("E. Anderson", "assist")
]

events_gw2 = [
    # Spain 3-0 Colombia
    ("Borja Iglesias", "goal"), ("Aymeric Laporte", "goal"), ("Mikel Oyarzabal", "goal"),
    # France 4-0 Uruguay
    ("A. Tchouaméni", "goal"), ("A. Rabiot", "assist"),
    # Brazil 1-1 Portugal
    ("Gabriel Martinelli", "goal"), ("Gabriel Magalhães", "assist"), ("Mateus Fernandes", "mid"),
    # Switzerland 2-2 Mexico
    ("A Amenda", "assist"),
    # Senegal 4-2 Saudi Arabia
    ("B. Dia", "goal"),
    # Uzbekistan 1-0 Cape Verde
    ("O. O'runov", "goal")
]

events_gw3 = [
    # Spain 5-0 Uzbekistan
    ("Borja Iglesias", "goal"), ("Yeremy Pino", "goal"), ("Lamine Yamal", "goal"),
    # France 6-0 Saudi Arabia
    ("O. Dembélé", "goal"), ("O. Dembélé", "goal"), ("O. Dembélé", "assist"), ("M. Olise", "assist"), ("A. Rabiot", "assist"), ("A. Tchouaméni", "assist"),
    # Brazil 6-1 Congo DR
    ("Vinícius Júnior", "goal"), ("Vinícius Júnior", "assist"), ("Endrick", "goal"), ("Raphinha", "goal"),
    # England 4-1 Jordan
    ("J. Stones", "goal"), ("J. Bowen", "goal"), ("J. Bowen", "assist"),
    # Netherlands 3-0 Algeria
    ("C. Gakpo", "goal"),
    # USA 2-1 Ecuador
    ("B. Aaronson", "assist"),
    # Norway 4-0 Curaçao
    ("E. Haaland", "goal"),
    # Colombia 5-0 Cape Verde
    ("J. Rodríguez", "goal"), ("J. Rodríguez", "assist"),
    # Uruguay 4-0 Senegal
    ("A. Canobbio", "goal"), ("A. Canobbio", "goal"),
    # Portugal 4-0 Morocco
    ("Gonçalo Ramos", "goal"), ("Gonçalo Ramos", "goal"), ("Rúben Neves", "assist"), ("António Silva", "goal")
]

# Match sheets (team, conceded)
conceded_gw1 = {
    "GER": 0, "CUW": 5, "SPA": 1, "CPV": 4, "NOR": 1, "IRQ": 3, "COL": 0, "UZB": 5,
    "FRA": 0, "SEN": 5, "URU": 1, "KSA": 4, "BRA": 0, "MOR": 5, "POR": 0, "COD": 6,
    "SWI": 1, "QAT": 2, "MEX": 2, "RSA": 2, "ENG": 1, "HAI": 4, "ARG": 0, "JOR": 4,
    "NED": 1, "TUN": 4, "BEL": 1, "ALG": 5, "USA": 1, "PAR": 3, "CAN": 0, "ECU": 2
}

conceded_gw2 = {
    "GER": 1, "NOR": 3, "SPA": 0, "COL": 3, "FRA": 0, "URU": 4, "BRA": 1, "POR": 1,
    "ENG": 0, "ARG": 1, "NED": 2, "BEL": 2, "USA": 2, "CAN": 0, "CUW": 0, "IRQ": 2,
    "CPV": 1, "UZB": 0, "SEN": 2, "KSA": 4, "MOR": 0, "COD": 2, "SWI": 2, "MEX": 2,
    "QAT": 2, "RSA": 2, "HAI": 1, "JOR": 2, "TUN": 1, "ALG": 0, "PAR": 0, "ECU": 2
}

conceded_gw3 = {
    "GER": 1, "IRQ": 4, "SPA": 0, "UZB": 5, "FRA": 0, "KSA": 6, "BRA": 1, "COD": 6,
    "ENG": 1, "JOR": 4, "NED": 0, "ALG": 3, "USA": 1, "ECU": 2, "NOR": 0, "CUW": 4,
    "COL": 0, "CPV": 5, "URU": 0, "SEN": 4, "POR": 0, "MOR": 4, "SWI": 1, "RSA": 0,
    "MEX": 1, "QAT": 2, "CAN": 0, "PAR": 2, "BEL": 0, "TUN": 3, "CRO": 0, "JPN": 3
}

def calculate_points(gw, player, events, conceded_map):
    pts = 0
    # Appearance: assume played 90 minutes
    pts += 2
    
    # Clean sheet
    team = player["teamIso"]
    conceded = conceded_map.get(team, 2)
    pos = player["position"]
    
    if conceded == 0:
        if pos in (1, 2):  # GK/DEF
            pts += 4
        elif pos == 3:  # MID
            pts += 1
            
    # Conceded goals deduction
    if pos in (1, 2) and conceded >= 2:
        pts -= (conceded // 2)
        
    # Event points
    for ev_name, ev_type in events:
        # Check name prefix
        if ev_name.lower() in player["name"].lower() or player["name"].lower() in ev_name.lower():
            if ev_type == "goal":
                if pos in (1, 2): pts += 6
                elif pos == 3: pts += 5
                elif pos == 4: pts += 4
            elif ev_type == "assist":
                pts += 3
                
    return max(0, pts)

print("GW1 Sample Points:")
for name, p in list(draft.items())[:10]:
    pts = calculate_points(1, p, events_gw1, conceded_gw1)
    print(f"{name} ({p['positionName']} - {p['teamIso']}): {pts} pts")
