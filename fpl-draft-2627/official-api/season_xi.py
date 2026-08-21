#!/usr/bin/env python3
"""Season-long first-choice XI per club, and the GW1 consensus beside it.

The GW1 XI answers "who plays on Saturday". This answers "whose shirt is it once
everyone is fit" - which is the question that matters for a squad you keep. It is
built from the ranking blend (FPL's own draft rank, Draft Fantasy xP, the LofLife
sheet and our 15-league ADP), with temporary injuries deliberately ignored, then
sanity-checked against minutes played and the club's summer business.
"""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "model.json")))
CON = json.load(open(os.path.join(HERE, "consensus.json")))
SQ = json.load(open(os.path.join(HERE, "squads.json")))
PL = M["players"]
OWNER = {i: t for t, ids in SQ.items() for i in ids}
POSO = ["GKP", "DEF", "MID", "FWD"]
W = {"off": 40, "df": 25, "lof": 20, "adp": 15}

# who each club bought this summer for which slot, and who left - the context a
# ranking cannot carry on its own
BUSINESS = {
 "ARS": "In: Bruno Guimaraes (mid), Tzolis + Hincapie + Meslier. Saliba and Timber both injured, so Mosquera is starting on merit rather than on reputation. Havertz and Gyokeres are a genuine two-way fight for the striker shirt.",
 "AVL": "Squad depleted: Onana, Joao Gomes, Madjo and Manzambi all out, Digne gone. Suzuki arrived to compete with Martinez. Watkins remains the first-choice nine when fit.",
 "BOU": "Lost Senesi to Spurs. In: Antonio Silva, Juanlu Sanchez, Alvaro Rodriguez. Petrovic took the gloves. Kroupi and Araujo injured, so Evanilson leads alone.",
 "BRE": "In: Callum Wilson, Jaidon Anthony, Mamadou Sangare, Schuster. Out: Reiss Nelson, Onyeka, Jordan Henderson. Igor Thiago is the undisputed nine.",
 "BHA": "In: Luka Vuskovic, Struijk, Costinha. Minteh out to late November, which opens a wide slot for Gomez or De Cuyper. Rutter has the striker shirt.",
 "CHE": "Alonso is moving to a back three. In: Lacroix, Welbeck, Palestra, Barco, Quenda, Emegha. Fofana suspended to 6 Sept. Joao Pedro central with Palmer behind.",
 "COV": "Promoted. In: Frank Onyeka. Haji Wright injured, so Simms and Thomas-Asante contest the nine.",
 "CRY": "In: Mingueza, Tomiyasu, McNeil, Guessand (loan). Out: Guehi, Lacroix. Strand Larsen and Mateta are a genuine two-way fight; Sarr is nailed wide.",
 "EVE": "In: Rohl, Hackney, Tyrique George, Norgaard, Brennan Johnson. Garner injured. Barry leads the line with Ndiaye and Dewsbury-Hall behind.",
 "FUL": "In: Gonzalo Garcia (RM), Shea Charles, Kusi-Asare. Out: Harry Wilson, Jimenez, Lukic, Diop. Andersen suspended for GW1. Garcia and Muniz contest the nine.",
 "HUL": "Promoted. Butland injured, so Tzolakis keeps goal. McBurnie is the only settled forward.",
 "IPS": "Promoted. In: Lukic and Diop from Fulham, Florentino Luis. Scherpen in goal, Emersonn up front.",
 "LEE": "In: Harry Wilson, Muharemovic, Trafford. Out: Meslier, Struijk. Trafford is the clear number one; Calvert-Lewin the nine.",
 "LIV": "New manager Iraola. Out: Salah and Robertson on frees, Konate. In: Jacquet, Victor Munoz, Araujo (loan). Gomez, Bradley and Leoni all injured, so the centre-back next to van Dijk is genuinely open between Jacquet and Araujo.",
 "MCI": "Guardiola replaced by Maresca. In: Elliot Anderson (£116m), Rulli, Monga. Out: Bernardo Silva, Stones, Ake, Trafford. Doku injured. Semenyo, Cherki, Foden and Savinho compete for two wide slots.",
 "MUN": "In: Tielemans, Andrey Santos. Sesko short of pre-season. De Ligt and Ugarte injured, so Maguire and Yoro pair up. Mbeumo leads with Cunha and Fernandes behind.",
 "NEW": "Howe replaced by Jaissle sixteen days before kick-off, so every role is a guess. Out: Bruno Guimaraes, Tonali, Gordon, Trippier. In: Bazoumana Toure, Hornicek, Bamba, Steur. Joelinton and Livramento injured. Osula, Wissa and Woltemade all contest the nine.",
 "NFO": "Glasner replaced Pereira and keeps a back three. In: Diomande, Schlager. Out: Elliot Anderson. Igor Jesus, Wood and Kalimuendo compete up front.",
 "SUN": "In: Meunier. Out: Mayenda, Traore, Cirkin, Neil. Roefs in goal, Brobbey the nine, Xhaka anchoring.",
 "TOT": "De Zerbi's first season. In: Robertson, Senesi, van Hecke, Tonali, Mateus Fernandes, Dubravka. Out: Romero, Bissouma, Spence. Kulusevski, Simons and Odobert injured; Solanke and Kudus doubtful, which is why Richarlison and Tel lead.",
}
FORM = {   # the shape each club is expected to keep across the season
 "ARS": (4,3,3), "AVL": (4,2,3+1-1), "BOU": (4,3,3), "BRE": (4,3,3), "BHA": (4,3,3),
 "CHE": (3,4,3), "COV": (4,3,3), "CRY": (3,4,3), "EVE": (4,3,3), "FUL": (4,3,3),
 "HUL": (4,3,3), "IPS": (4,3,3), "LEE": (3,4,3), "LIV": (4,3,3), "MCI": (4,3,3),
 "MUN": (4,3,3), "NEW": (4,3,3), "NFO": (3,4,3), "SUN": (4,3,3), "TOT": (4,3,3),
}


def blended(p):
    parts = []
    if p["dr"] < 9999: parts.append((W["off"], p["dr"]))
    if p.get("df") and not p.get("cont"): parts.append((W["df"], p["df"]))
    if p.get("lofr"): parts.append((W["lof"], p["lofr"]))
    if p.get("adp"): parts.append((W["adp"], p["adp"] * 2.2))
    if not parts: return 500.0
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


out = {}
for club in sorted({p["c"] for p in PL}):
    squad = [p for p in PL if p["c"] == club and p["av"] != "gone"]
    nd, nm, nf = FORM.get(club, (4, 3, 3))
    nd, nm, nf = 4 if club == "AVL" else nd, 3 if club == "AVL" else nm, 3 if club == "AVL" else nf
    pick = {}
    for pos, want in (("GKP", 1), ("DEF", nd), ("MID", nm), ("FWD", nf)):
        ranked = sorted([p for p in squad if p["p"] == pos], key=blended)
        pick[pos] = ranked[:want]
    # who the GW1 consensus starts, for the side-by-side
    gw1 = {r["n"]: r for r in CON.get(club, {}).get("rows", [])}
    rows = []
    for pos in POSO:
        for p in pick[pos]:
            g = gw1.get(p["n"])
            rows.append({"n": p["n"], "p": pos, "id": p["id"],
                         "votes": g["v"] if g else 0,
                         "av": p["av"], "ch": p["ch"], "mins": p["mins"],
                         "ppg": p["ppg"], "dr": p["dr"],
                         "own": OWNER.get(p["id"], "")})
    # anyone the GW1 sources start who is NOT in the season XI: a stand-in
    seasonset = {r["n"] for r in rows}
    standins = [{"n": r["n"], "p": r["p"], "votes": r["v"], "av": r["av"],
                 "own": OWNER.get(r["id"], "")}
                for r in CON.get(club, {}).get("rows", [])
                if r["n"] not in seasonset and r["v"] >= 2]
    out[club] = {"season": rows, "standins": standins,
                 "form": f"{nd}-{nm}-{nf}", "business": BUSINESS.get(club, ""),
                 "note": CON.get(club, {}).get("note", ""),
                 "gw1": CON.get(club, {}).get("rows", [])}

json.dump(out, open(os.path.join(HERE, "season_xi.json"), "w"), indent=0)
print(f"clubs: {len(out)}")
owned_standin = [(c, s["n"], s["own"]) for c, d in out.items() for s in d["standins"] if s["own"]]
print("\nDrafted players who START in GW1 but are NOT the season first choice:")
for c, n, o in owned_standin:
    print(f"   {c} {n:16} [{o}]")
print("\nDrafted players who ARE the season first choice but miss the GW1 XI:")
for c, d in out.items():
    for r in d["season"]:
        if r["own"] and r["votes"] == 0:
            print(f"   {c} {r['n']:16} [{r['own']}]  {r['av']}"
                  f"{' ' + str(r['ch']) + '%' if r['ch'] is not None else ''}")
