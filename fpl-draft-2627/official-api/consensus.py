#!/usr/bin/env python3
"""GW1 lineup consensus across four independent all-20-club sources, arbitrated by
the official availability feed, plus a reasoned season-long first-choice XI.

Sources
  RW  RotoWire predicted lineups          20 Aug 2026  (all 20)
  YH  Yahoo Sports FPL GW1 lineups        18 Aug 2026  (all 20)
  FA  FPL Assistant predicted lineups     undated      (all 20; demonstrably stale)
  OF  OneFPL predicted lineups            17 Aug 2026  (all 20, partial detail)
  +   ESPN 18 Aug for the seven big clubs, and club-specific pieces for Arsenal
The official draft.premierleague.com feed overrides all of them on availability:
a source that names an injured player is stale, not a dissenting opinion.
"""
import json, os, re, unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- source A: RotoWire, 20 Aug -------------------------------------------
RW = {
 "ARS":"Raya|Calafiori Gabriel Mosquera White|Rice Lewis-Skelly Tzolis Odegaard Saka|Havertz",
 "COV":"Rushworth|Dasilva Thomas Amenda van Ewijk|Yirenkyi Onyeka Grimes Tchaouna Sakamoto|Simms",
 "HUL":"Tzolakis|Giles Egan Ajayi Coyle|Slater Crooks Stroud Belloumi Hjerto-Dahl|McBurnie",
 "MUN":"Lammens|Shaw Maguire Yoro Dalot|Santos Tielemans Cunha Fernandes Diallo|Mbeumo",
 "NFO":"Sels|Milenkovic Murillo Diomande Williams|Schlager Sangare Aina Gibbs-White Ndoye|Jesus",
 "LEE":"Trafford|Rodon Bijol Muharemovic Justin|Ampadu Stach Bogle Wilson Aaronson|Calvert-Lewin",
 "IPS":"Scherpen|Davis Diop Greaves O'Shea|Luis Lukic Maeda Nunez Fatawu|Emersonn",
 "SUN":"Roefs|Reinildo Ballard O'Nien Hume|Sadiki Xhaka Angulo Le Fee Talbi|Brobbey",
 "EVE":"Pickford|Mykolenko Branthwaite Tarkowski O'Brien|Armstrong Hackney Ndiaye Dewsbury-Hall Rohl|Barry",
 "CRY":"Henderson|Richards Canvot Riad Mitchell|Kamada Wharton Mingueza McNeil Sarr|Strand Larsen",
 "BRE":"Kelleher|Lewis-Potter Collins Ajer Kayode|Sangare Jensen Janelt Schade Ouattara|Thiago",
 "TOT":"Kinsky|Robertson van Hecke Senesi Porro|Tonali Gallagher Fernandes Tel Moore|Richarlison",
 "MCI":"Donnarumma|O'Reilly Dias Gvardiol Khusanov|Anderson Kovacic Semenyo Foden Cherki|Haaland",
 "BOU":"Petrovic|Truffert Hill Silva Smith|Cook Scott Tavernier Kluivert Rayan|Evanilson",
 "BHA":"Verbruggen|Kadioglu Boscagli Vuskovic Wieffer|Ayari Gross De Cuyper Hinshelwood Gomez|Rutter",
 "AVL":"Suzuki|Maatsen Mings Torres Cash|Kamara Barkley Garnacho Buendia McGinn|Abraham",
 "NEW":"Hornicek|Hall Thiaw Botman Dedic|Ramsey Bamba Barnes Wissa Elanga|Osula",
 "LIV":"Alisson|Kerkez Jacquet Dijk Frimpong|Gravenberch Szoboszlai Gakpo Wirtz Ngumoha|Isak",
 "FUL":"Leno|Robinson Bassey Cuenca Castagne|Iwobi Berge Palacios King Bobb|Gonzalo",
 "CHE":"Sanchez|James Lacroix Colwill Palestra|Caicedo Fernandez Neto Palmer Rogers|Pedro",
}
# ---- source B: Yahoo, 18 Aug ----------------------------------------------
YH = {
 "ARS":"Raya|White Mosquera Gabriel Calafiori|Odegaard Lewis-Skelly Rice Madueke Tzolis|Gyokeres",
 "COV":"Rushworth|van Ewijk Thomas Amenda Dasilva|Yirenkyi Grimes Onyeka Tchaouna Thomas-Asante|Simms",
 "HUL":"Tzolakis|Coyle Ajayi Mendy Giles|Slater Crooks Belloumi Hjerto-Dahl Stroud|McBurnie",
 "MUN":"Lammens|Dalot Maguire Heaven Shaw|Tielemans Santos Diallo Fernandes Dorgu|Mbeumo",
 "IPS":"Scherpen|O'Shea Diop Greaves Davis|Nunez Lukic Fatawu Egeli Maeda|Emersonn",
 "SUN":"Roefs|Meunier O'Nien Ballard Reinildo|Xhaka Sadiki Hume Le Fee Angulo|Brobbey",
 "EVE":"Pickford|O'Brien Tarkowski Branthwaite Mykolenko|Hackney Armstrong Rohl Dewsbury-Hall Ndiaye|Barry",
 "CRY":"Henderson|Canvot Richards Riad|Mingueza Kamada Wharton Mitchell Sarr McNeil|Strand Larsen",
 "NFO":"Sels|Diomande Milenkovic Murillo|Aina Schlager Sangare Williams Ndoye Gibbs-White|Jesus",
 "LEE":"Trafford|Rodon Bijol Muharemovic|Bogle Ampadu Stach Justin Wilson Aaronson|Calvert-Lewin",
 "BRE":"Kelleher|Kayode Ajer Collins Lewis-Potter|Sangare Janelt Ouattara Jensen Schade|Thiago",
 "TOT":"Kinsky|Gray van Hecke Senesi Robertson|Tonali Fernandes Moore Gallagher Tel|Richarlison",
 "MCI":"Donnarumma|Khusanov Dias Guehi Gvardiol|Anderson Kovacic Semenyo Foden Doku|Haaland",
 "BOU":"Petrovic|Smith Hill Silva Truffert|Cook Scott Rayan Kluivert Tavernier|Evanilson",
 "BHA":"Verbruggen|Wieffer Vuskovic Boscagli Kadioglu|Ayari Gross Gomez Hinshelwood De Cuyper|Rutter",
 "AVL":"Martinez|Cash Lindelof Torres Maatsen|Barkley Kamara McGinn Buendia Garnacho|Watkins",
 "NEW":"Hornicek|Miley Thiaw Botman Hall|Steur Bamba Elanga Ramsey Toure|Wissa",
 "LIV":"Alisson|Frimpong Jacquet Dijk Kerkez|Gravenberch Szoboszlai Ngumoha Wirtz Gakpo|Isak",
 "FUL":"Leno|Castagne Cuenca Bassey Robinson|Berge Iwobi Bobb King Palacios|Gonzalo",
 "CHE":"Sanchez|James Lacroix Colwill|Palestra Lavia Caicedo Neto Palmer Pedro|Rogers",
}
# ---- source C: FPL Assistant (stale: names players the official feed has out) --
FA = {
 "ARS":"Raya|White Mosquera Gabriel Hincapie|Guimaraes Odegaard Eze Madueke Tzolis|Gyokeres",
 "AVL":"Martinez|Cash Konsa Torres Maatsen|Kamara Gomes McGinn Buendia Manzambi|Watkins",
 "BOU":"Petrovic|Smith Hill Silva Truffert|Adams Scott Tavernier Kluivert Rayan|Evanilson",
 "BRE":"Kelleher|Kayode Ajer Collins Lewis-Potter|Yarmoliuk Janelt Ouattara Jensen Schade|Thiago",
 "BHA":"Verbruggen|Kadioglu Vuskovic Dunk De Cuyper|Baleba Gross Gomez Hinshelwood Minteh|Rutter",
 "CHE":"Sanchez|Palestra Lacroix Colwill Hato|Lavia Caicedo Neto Palmer Rogers|Pedro",
 "COV":"Rushworth|van Ewijk Thomas Amenda Dasilva|Grimes Onyeka Sakamoto Torp Mason-Clark|Wright",
 "CRY":"Henderson|Canvot Richards Riad Munoz|Wharton Kamada Mitchell Sarr McNeil|Strand Larsen",
 "EVE":"Pickford|O'Brien Tarkowski Branthwaite Mykolenko|Hackney Rohl Johnson Dewsbury-Hall Ndiaye|Barry",
 "FUL":"Leno|Tete Cuenca Bassey Robinson|Lukic Iwobi Bobb Smith Rowe Kevin|Muniz",
 "HUL":"Butland|Coyle Egan Ajayi Giles|Slater Crooks Belloumi Omur Millar|McBurnie",
 "IPS":"Scherpen|Furlong O'Shea Greaves Davis|Nunez Humphreys Fatawu Mehmeti Maeda|Emersonn",
 "LEE":"Perri|Bogle Rodon Bijol Justin|Ampadu Tanaka Stach Aaronson Wilson|Calvert-Lewin",
 "LIV":"Alisson|Frimpong Araujo Dijk Kerkez|Gravenberch Szoboszlai Ngumoha Wirtz Gakpo|Isak",
 "MCI":"Donnarumma|Nunes Khusanov Gvardiol Ait-Nouri|Kovacic Anderson Semenyo Foden Doku|Haaland",
 "MUN":"Lammens|Dalot Yoro Maguire Shaw|Tielemans Santos Amad Fernandes Cunha|Mbeumo",
 "NEW":"Pope|Miley Thiaw Botman Hall|Joelinton Willock Elanga Ramsey Barnes|Osula",
 "NFO":"Sels|Diomande Milenkovic Murillo Aina|Sangare Dominguez Williams Gibbs-White Jesus|Wood",
 "SUN":"Roefs|Mukiele Ballard Alderete Reinildo|Xhaka Sadiki Hume Le Fee Angulo|Brobbey",
 "TOT":"Kinsky|Porro van Hecke Van de Ven Robertson|Tonali Fernandes Kudus Gallagher Tel|Solanke",
}
SOURCES = {"RotoWire 20 Aug": RW, "Yahoo 18 Aug": YH, "FPL Assistant": FA}
# OneFPL 17 Aug is a prose summary rather than full XIs; its agreements are recorded
# per club in NOTES below rather than as a fourth column of names.
NOTES = {
 "ARS": "OneFPL: Tzolis left, defence reshaped without Saliba/Timber. ESPN 18 Aug: Saka and Rice start after the Community Shield, Mosquera replaces Saliba, Guimaraes doubtful.",
 "LIV": "OneFPL: Gakpo/Isak/Wirtz core, centre-back pick open between Jacquet and others. ESPN: Araujo likely partners van Dijk.",
 "MCI": "OneFPL: Haaland available, Gvardiol secure, midfield open. ESPN: Donnarumma, Haaland, Foden at 10, Anderson starting.",
 "MUN": "OneFPL: Shaw and Maguire strong, Sesko short of pre-season. ESPN: Fernandes captain, Santos anchor, Tielemans and Mainoo compete.",
 "CHE": "OneFPL and ESPN both describe Alonso moving to a back three; RotoWire keeps a four.",
 "TOT": "OneFPL: Kinsky number one, Richarlison central. ESPN: Kulusevski and Solanke unavailable, Gray covers right-back.",
 "AVL": "ESPN: severe squad depletion, a 19-year-old may debut out of necessity.",
 "NEW": "OneFPL: Thiaw and Botman, Barnes and Elanga wide, striker unsettled.",
 "LEE": "OneFPL: Muharemovic in the back three, Calvert-Lewin central.",
 "NFO": "OneFPL: 3-4-3 retained, Igor Jesus competing with Wood and Kalimuendo.",
 "BHA": "OneFPL: Minteh injured, De Cuyper possibly advanced.",
 "CRY": "OneFPL: back three, Mitchell as wing-back.",
 "BRE": "OneFPL: Thiago, Schade and Ouattara; van den Berg a doubt.",
 "BOU": "OneFPL: Kluivert and Tavernier secure, defence unsettled.",
 "SUN": "OneFPL: O'Nien expected, Le Fee advanced, Hume's role open.",
 "FUL": "OneFPL: Garcia leads the striker race.",
 "EVE": "OneFPL: Pickford fit, Ndiaye key, Garner's fitness open.",
 "IPS": "OneFPL: Scherpen; Diop and Greaves at centre-back.",
 "HUL": "OneFPL: Tzolakis in the goalkeeping race; Hughes out.",
 "COV": "OneFPL: Awoniyi and Simms compete at striker.",
}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


def main():
    M = json.load(open(os.path.join(HERE, "model.json")))
    PL = M["players"]
    PIN = json.load(open(os.path.join(HERE, "xi_pins.json"))) if \
        os.path.exists(os.path.join(HERE, "xi_pins.json")) else {}

    def find(club, token):
        pool = [p for p in PL if p["c"] == club]
        want = PIN.get(f"{club}|{token}", token)
        hit = next((p for p in pool if norm(p["n"]) == norm(want)), None)
        if hit: return hit
        cands = [p for p in pool if norm(want) and
                 (norm(want) in norm(p["n"]) or norm(p["n"]) in norm(want))]
        return cands[0] if len(cands) == 1 else (cands[0] if cands else None)

    votes = defaultdict(lambda: defaultdict(list))   # club -> pid -> [source...]
    unmatched = defaultdict(list)
    for sname, src in SOURCES.items():
        for club, line in src.items():
            for tok in line.replace("|", " ").split():
                p = find(club, tok)
                if p: votes[club][p["id"]].append(sname)
                else: unmatched[sname].append(f"{club}:{tok}")

    byid = {p["id"]: p for p in PL}
    out = {}
    for club in sorted(votes):
        rows = []
        for pid, srcs in votes[club].items():
            p = byid[pid]
            rows.append({"id": pid, "n": p["n"], "p": p["p"], "v": len(srcs),
                         "src": srcs, "av": p["av"], "ch": p["ch"],
                         "news": p["news"], "mins": p["mins"], "ppg": p["ppg"],
                         "dr": p["dr"]})
        rows.sort(key=lambda r: (-r["v"], ["GKP","DEF","MID","FWD"].index(r["p"])))
        out[club] = {"rows": rows, "note": NOTES.get(club, "")}
    json.dump(out, open(os.path.join(HERE, "consensus.json"), "w"), indent=0)

    print(f"clubs: {len(out)}   sources: {len(SOURCES)} full XIs + OneFPL/ESPN notes")
    tot_un = sum(len(v) for v in unmatched.values())
    if tot_un:
        print(f"unmatched tokens: {tot_un}")
        for s, v in unmatched.items():
            if v: print(f"  {s}: {', '.join(v[:14])}")
    # who do the sources actually disagree about, and who does the feed contradict?
    print("\nSOURCE NAMES A PLAYER THE OFFICIAL FEED HAS UNAVAILABLE (source is stale):")
    for club, d in out.items():
        for r in d["rows"]:
            if r["av"] in ("out", "susp"):
                print(f"  {club} {r['n']:14} {r['av']:5} <- {', '.join(r['src'])}  ({r['news'][:44]})")


if __name__ == "__main__":
    main()
