import json

with open("scratch/mapped_draft.json") as f:
    draft = json.load(f)

# Missing manual overrides
draft["Bukayo Saka"] = {"id": 99901, "name": "Bukayo Saka", "position": 3, "positionName": "MID", "teamIso": "ENG"}
draft["Cristiano Ronaldo"] = {"id": 99902, "name": "Cristiano Ronaldo", "position": 4, "positionName": "FWD", "teamIso": "POR"}
draft["Harry Kane"] = {"id": 99903, "name": "Harry Kane", "position": 4, "positionName": "FWD", "teamIso": "ENG"}
draft["A. Ne'matov"] = {"id": 73507, "name": "A. Ne'matov", "position": 1, "positionName": "GK", "teamIso": "UZB"}

squads_raw = {
    "u_roy": [
        "Al Mahdi Soliman", "B. Ergashev", "M. Guéhi", "A. Abdi", "A. Kaplan", "A. Ralston", "A. Trusty", "J. Kimmich", "A. Adli", "A. Karazor", "A. Rabiot", "A. Tchouaméni", "Kylian Mbappé", "A. Diallo", "A. El Kaabi"
    ],
    "u_yonatan": [
        "Alisson Becker", "A. Pierre", "I. Konaté", "Pedro Porro", "A. Khusanov", "A. Robertson", "Aymeric Laporte", "A. Ahmed", "A. Jasim", "A. Stiller", "A. Wharton", "B. Aaronson", "Lamine Yamal", "A. Canobbio", "A. Elanga"
    ],
    "USER_UID": [
        "Unai Simón", "A. Lafont", "Gabriel Magalhães", "A. Ait Boudlal", "A. Robinson", "António Silva", "B. Karimov", "M. Olise", "J. Rodríguez", "A. Ounahi", "A. Stach", "A. Witsel", "A. Budimir", "A. Ezzalzouli", "A. González"
    ],
    "u_nadav": [
        "A. Ramsdale", "Ahmed El Shenawy", "A. Amenda", "A. Freeman", "A. Theate", "Ahmed Abou El Fotouh", "B. Mechele", "Bruno Fernandes", "Bukayo Saka", "A. Jashari", "A. Mac Allister", "A. Onana", "Cristiano Ronaldo", "Gabriel Martinelli", "A. Bonny"
    ],
    "u_yuval": [
        "A. Dahmen", "A. Nübel", "Marc Cucurella", "A. Arous", "A. Giay", "A. Martha", "A. Rüdiger", "A. Irving", "A. Sher", "Ahmed Koka", "Amir Al Ammari", "B. El Khannouss", "O. Dembélé", "L. Messi", "Endrick"
    ],
    "u_ido": [
        "A. Gunn", "A. Ne'matov", "A. Hakimi", "A. Bardakcı", "A. Mendy", "A. Seck", "Ahmed Eid", "A. Ben Slimane", "A. Gʻaniyev", "A. Saelemaekers", "Akam Rahman", "B. Gilmour", "E. Haaland", "Vinícius Júnior", "Mikel Oyarzabal"
    ],
    "u_shai": [
        "A. Bayındır", "Ahmed Basil", "Nuno Mendes", "A. Ben Hmida", "A. Salah-Eddine", "Ahmed Hasan Al Reeshawee", "B. White", "A. Gutiérrez", "A. Güler", "A. Morris", "A. Mozgovoy", "A. Sanches", "Harry Kane", "Raphinha", "J. Álvarez"
    ]
}

squad_ids = {}
for uid, names in squads_raw.items():
    squad_ids[uid] = []
    for name in names:
        # Fuzzy match key
        clean_name = name.replace("&apos;", "").replace("'", "").replace("’", "").replace("ʻ", "").replace("ʻ", "").lower().strip()
        matched_key = None
        for k in draft:
            clean_k = k.replace("&apos;", "").replace("'", "").replace("’", "").replace("ʻ", "").replace("ʻ", "").lower().strip()
            if clean_name == clean_k or clean_name in clean_k or clean_k in clean_name:
                matched_key = k
                break
        if matched_key:
            squad_ids[uid].append(draft[matched_key])
        else:
            print("ERROR: missing", name)

with open("scratch/squad_ids.json", "w") as f:
    json.dump(squad_ids, f, indent=2)
print("Saved scratch/squad_ids.json successfully!")
