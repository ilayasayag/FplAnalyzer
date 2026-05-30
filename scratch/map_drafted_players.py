import os
import json
import re

# Load players
json_path = "fpl_predictor/data/wc_seeded_data.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)
players = data["players"]

drafted_names = [
    # GoldenGoalFF
    "Al Mahdi Soliman", "B. Ergashev", "M. Guéhi", "A. Abdi", "A. Kaplan", "A. Ralston", "A. Trusty", "J. Kimmich", "A. Adli", "A. Karazor", "A. Rabiot", "A. Tchouaméni", "Kylian Mbappé", "A. Diallo", "A. El Kaabi",
    # FPLtfs
    "Alisson Becker", "A. Pierre", "I. Konaté", "Pedro Porro", "A. Khusanov", "A. Robertson", "Aymeric Laporte", "A. Ahmed", "A. Jasim", "A. Stiller", "A. Wharton", "B. Aaronson", "Lamine Yamal", "A. Canobbio", "A. Elanga",
    # FPLFRAN
    "Unai Simón", "A. Lafont", "Gabriel Magalhães", "A. Ait Boudlal", "A. Robinson", "António Silva", "B. Karimov", "M. Olise", "J. Rodríguez", "A. Ounahi", "A. Stach", "A. Witsel", "A. Budimir", "A. Ezzalzouli", "A. González",
    # LloydHassell
    "A. Ramsdale", "Ahmed El Shenawy", "A. Amenda", "A. Freeman", "A. Theate", "Ahmed Abou El Fotouh", "B. Mechele", "Bruno Fernandes", "Bukayo Saka", "A. Jashari", "A. Mac Allister", "A. Onana", "Cristiano Ronaldo", "Gabriel Martinelli", "A. Bonny",
    # nordburfor
    "A. Dahmen", "A. Nübel", "Marc Cucurella", "A. Arous", "A. Giay", "A. Martha", "A. Rüdiger", "A. Irving", "A. Sher", "Ahmed Koka", "Amir Al Ammari", "B. El Khannouss", "O. Dembélé", "L. Messi", "Endrick",
    # FPLMate
    "A. Gunn", "A. Ne'matov", "A. Hakimi", "A. Bardakcı", "A. Mendy", "A. Seck", "Ahmed Eid", "A. Ben Slimane", "A. Gʻaniyev", "A. Saelemaekers", "Akam Rahman", "B. Gilmour", "E. Haaland", "Vinícius Júnior", "Mikel Oyarzabal",
    # CantWinFPL
    "A. Bayındır", "Ahmed Basil", "Nuno Mendes", "A. Ben Hmida", "A. Salah-Eddine", "Ahmed Hasan Al Reeshawee", "B. White", "A. Gutiérrez", "A. Güler", "A. Morris", "A. Mozgovoy", "A. Sanches", "Harry Kane", "Raphinha", "J. Álvarez"
]

mapped = {}
not_found = []

for name in drafted_names:
    # clean name for search
    clean = name.replace("'", "").replace("’", "").lower()
    matches = []
    for p in players:
        p_name = p["name"].replace("'", "").replace("’", "").lower()
        if clean == p_name:
            matches.append(p)
            
    if not matches:
        # fuzzy match
        for p in players:
            p_name = p["name"].replace("'", "").replace("’", "").lower()
            if clean in p_name or p_name in clean:
                matches.append(p)
                
    if matches:
        # pick the best match
        matches.sort(key=lambda x: x["id"])
        mapped[name] = matches[0]
    else:
        not_found.append(name)

print("Mapped:", len(mapped))
print("Not found:", not_found)

# Save mapped to scratch
with open("scratch/mapped_draft.json", "w") as f:
    json.dump({name: {"id": p["id"], "name": p["name"], "position": p["position"], "positionName": p["positionName"], "teamIso": p["teamIso"]} for name, p in mapped.items()}, f, indent=2)
