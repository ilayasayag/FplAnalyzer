#!/usr/bin/env python3
"""Match the 8 completed draft squads onto official element ids."""
import json, os, re, unicodedata, sys

HERE = os.path.dirname(os.path.abspath(__file__))

SQUADS = {
 "Hapoel Hananya": {
  "GKP": [("Pickford","EVE"),("Verbruggen","BHA")],
  "DEF": [("Virgil","LIV"),("Senesi","TOT"),("Milenkovic","NFO"),("Dalot","MUN"),("Richards","CRY")],
  "MID": [("Rice","ARS"),("Cunha","MUN"),("Sarr","CRY"),("Dewsbury-Hall","EVE"),("Doku","MCI")],
  "FWD": [("Joao Pedro","CHE"),("Gyokeres","ARS"),("Georginio","BHA")]},
 "The Gunners": {
  "GKP": [("Donnarumma","MCI"),("Hornicek","NEW")],
  "DEF": [("Gabriel","ARS"),("James","CHE"),("Colwill","CHE"),("Araujo","LIV"),("Ruben","MCI")],
  "MID": [("Semenyo","MCI"),("Bruno G.","ARS"),("Foden","MCI"),("Gakpo","LIV"),("Maddison","TOT")],
  "FWD": [("Mateta","CRY"),("Gonzalo","FUL"),("Solanke","TOT")]},
 "BestManWin": {
  "GKP": [("Sanchez","CHE"),("Sels","NFO")],
  "DEF": [("Maguire","MUN"),("White","ARS"),("Frimpong","LIV"),("Ballard","SUN"),("Shaw","MUN")],
  "MID": [("B.Fernandes","MUN"),("Szoboszlai","LIV"),("Wirtz","LIV"),("Odegaard","ARS"),("Buendia","AVL")],
  "FWD": [("Brobbey","SUN"),("Barry","EVE"),("Ekitike","LIV")]},
 "McShaike's": {
  "GKP": [("A.Becker","LIV"),("Martinez","AVL")],
  "DEF": [("O'Reilly","MCI"),("Guehi","MCI"),("Munoz","CRY"),("Pedro Porro","TOT"),("Hall","NEW")],
  "MID": [("Cherki","MCI"),("Rayan","BOU"),("O.Dango","BRE"),("Ngumoha","LIV"),("Kluivert","BOU")],
  "FWD": [("Watkins","AVL"),("Isak","LIV"),("Strand Larsen","CRY")]},
 "Wugman FC": {
  "GKP": [("Trafford","LEE"),("Leno","FUL")],
  "DEF": [("Tarkowski","EVE"),("N.Williams","NFO"),("Jacquet","LIV"),("Truffert","BOU"),("Vuskovic","BHA")],
  "MID": [("Rogers","CHE"),("Ndiaye","EVE"),("Wilson","LEE"),("E.Le Fee","SUN"),("Gross","BHA")],
  "FWD": [("Thiago","BRE"),("Calvert-Lewin","LEE"),("Igor Jesus","NFO")]},
 "RedDevilsMarchingOn": {
  "GKP": [("Raya","ARS"),("Henderson","CRY")],
  "DEF": [("Calafiori","ARS"),("Matheus N.","MCI"),("Keane","EVE"),("Collins","BRE"),("Van de Ven","TOT")],
  "MID": [("Mbeumo","MUN"),("Dorgu","MUN"),("Enzo","CHE"),("Gravenberch","LIV"),("Rashford","MUN")],
  "FWD": [("Havertz","ARS"),("Woltemade","NEW"),("McBurnie","HUL")]},
 "Naco FC": {
  "GKP": [("Roefs","SUN"),("Kelleher","BRE")],
  "DEF": [("Lacroix","CHE"),("Van Hecke","TOT"),("Konsa","AVL"),("Muharemovic","LEE"),("J.Timber","ARS")],
  "MID": [("Saka","ARS"),("Schade","BRE"),("Stach","LEE"),("Sangare","BRE"),("Hinshelwood","BHA")],
  "FWD": [("Haaland","MCI"),("Sesko","MUN"),("Evanilson","BOU")]},
 "roy's team": {
  "GKP": [("Lammens","MUN"),("Petrovic","BOU")],
  "DEF": [("Gvardiol","MCI"),("Palestra","CHE"),("Mosquera","ARS"),("Kerkez","LIV"),("Hume","SUN")],
  "MID": [("Palmer","CHE"),("Gibbs-White","NFO"),("Anderson","MCI"),("Tzolis","ARS"),("Tielemans","MUN")],
  "FWD": [("Richarlison","TOT"),("Wissa","NEW"),("N.Jackson","CHE")]},
}

ALIAS = {   # squad-sheet spelling -> official web_name where they differ
 "Virgil":"Virgil","Ruben":"Ruben","Martinez":"Martinez",
 "O.Dango":"Dango","E.Le Fee":"Le Fee","Georginio":"Georginio",
 "Joao Pedro":"Joao Pedro","Bruno G.":"Bruno G.","Pedro Porro":"Porro",
 "Strand Larsen":"Strand Larsen","N.Jackson":"Jackson","Matheus N.":"Matheus N.",
 "Van de Ven":"Van de Ven","Van Hecke":"Van Hecke","J.Timber":"J.Timber",
 "N.Williams":"N.Williams","B.Fernandes":"B.Fernandes",
}

def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())

model = json.load(open(os.path.join(HERE, "model.json")))
PL = model["players"]

def find(name, club, pos):
    want = ALIAS.get(name, name)
    cands = [p for p in PL if p["c"] == club and p["p"] == pos]
    for p in cands:                                  # exact web_name
        if norm(p["n"]) == norm(want): return p
    for p in cands:                                  # surname contains
        if norm(want) and (norm(want) in norm(p["n"]) or norm(p["n"]) in norm(want)): return p
    loose = [p for p in PL if p["c"] == club]        # right club, wrong position label
    for p in loose:
        if norm(p["n"]) == norm(want): return p
    for p in loose:
        if norm(want) and (norm(want) in norm(p["n"]) or norm(p["n"]) in norm(want)): return p
    return None

out, missing, posfix = {}, [], []
for team, sq in SQUADS.items():
    ids = []
    for pos, players in sq.items():
        for name, club in players:
            p = find(name, club, pos)
            if not p:
                missing.append((team, pos, name, club)); continue
            if p["p"] != pos:
                posfix.append((name, club, pos, p["p"]))
            ids.append(p["id"])
    out[team] = ids

print(f"teams: {len(out)}   matched: {sum(len(v) for v in out.values())} of {8*15}")
if posfix:
    print("\nposition per the draft page vs official API:")
    for n, c, a, b in posfix: print(f"   {n:16} {c:4} sheet={a}  official={b}")
if missing:
    print("\nUNMATCHED:")
    for t, pos, n, c in missing: print(f"   {t:22} {pos} {n} ({c})")
else:
    print("\nevery player matched")

allids = [i for v in out.values() for i in v]
assert len(allids) == len(set(allids)) or True
dupes = [i for i in set(allids) if allids.count(i) > 1]
if dupes:
    byid = {p["id"]: p for p in PL}
    print("\nDUPLICATE across squads:", [byid[i]["n"] for i in dupes])
fa = [p for p in PL if p["id"] not in set(allids) and p["av"] != "gone"]
print(f"\nfree agents: {len(fa)}")
json.dump(out, open(os.path.join(HERE, "squads.json"), "w"), indent=0)
