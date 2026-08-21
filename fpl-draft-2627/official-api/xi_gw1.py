#!/usr/bin/env python3
"""GW1 projected XIs for all 20 clubs (RotoWire, 20 Aug 2026), matched to element ids.

This is the strongest short-horizon minutes signal there is: it says who is on the
pitch on day one, which last season's minutes and a season-long ranking cannot.
"""
import json, os, re, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

XI = {
 "ARS": "Raya|Calafiori Gabriel Mosquera White|Rice Lewis-Skelly Tzolis Odegaard Saka|Havertz",
 "COV": "Rushworth|Dasilva Thomas Amenda van Ewijk|Yirenkyi Onyeka Grimes Tchaouna Sakamoto|Simms",
 "HUL": "Tzolakis|Giles Egan Ajayi Coyle|Slater Crooks Stroud Belloumi Hjerto-Dahl|McBurnie",
 "MUN": "Lammens|Shaw Maguire Yoro Dalot|Santos Tielemans Cunha Fernandes Diallo|Mbeumo",
 "NFO": "Sels|Milenkovic Murillo Diomande Williams|Schlager Sangare Aina Gibbs-White Ndoye|Jesus",
 "LEE": "Trafford|Rodon Bijol Muharemovic Justin|Ampadu Stach Bogle Wilson Aaronson|Calvert-Lewin",
 "IPS": "Scherpen|Davis Diop Greaves O'Shea|Luis Lukic Maeda Nunez Fatawu|Emersonn",
 "SUN": "Roefs|Reinildo Ballard O'Nien Hume|Sadiki Xhaka Angulo Le Fee Talbi|Brobbey",
 "EVE": "Pickford|Mykolenko Branthwaite Tarkowski O'Brien|Armstrong Hackney Ndiaye Dewsbury-Hall Rohl|Barry",
 "CRY": "Henderson|Richards Canvot Riad Mitchell|Kamada Wharton Mingueza McNeil Sarr|Strand Larsen",
 "BRE": "Kelleher|Lewis-Potter Collins Ajer Kayode|Sangare Jensen Janelt Schade Ouattara|Thiago",
 "TOT": "Kinsky|Robertson van Hecke Senesi Porro|Tonali Gallagher Fernandes Tel Moore|Richarlison",
 "MCI": "Donnarumma|O'Reilly Dias Gvardiol Khusanov|Anderson Kovacic Semenyo Foden Cherki|Haaland",
 "BOU": "Petrovic|Truffert Hill Silva Smith|Cook Scott Tavernier Kluivert Rayan|Evanilson",
 "BHA": "Verbruggen|Kadioglu Boscagli Vuskovic Wieffer|Ayari Gross De Cuyper Hinshelwood Gomez|Rutter",
 "AVL": "Suzuki|Maatsen Mings Torres Cash|Kamara Barkley Garnacho Buendia McGinn|Abraham",
 "NEW": "Hornicek|Hall Thiaw Botman Dedic|Ramsey Bamba Barnes Wissa Elanga|Osula",
 "LIV": "Alisson|Kerkez Jacquet Dijk Frimpong|Gravenberch Szoboszlai Gakpo Wirtz Ngumoha|Isak",
 "FUL": "Leno|Robinson Bassey Cuenca Castagne|Iwobi Berge Palacios King Bobb|Gonzalo",
 "CHE": "Sanchez|James Lacroix Colwill Palestra|Caicedo Fernandez Neto Palmer Rogers|Pedro",
}
# ambiguity the surname alone cannot settle (two men, one club, same surname)
PIN = {("MCI", "Dias"): "Ruben", ("TOT", "Fernandes"): "M.Fernandes",
       ("CHE", "Fernandez"): "Enzo", ("CHE", "Pedro"): "Joao Pedro",
       ("LIV", "Dijk"): "Virgil", ("NFO", "Jesus"): "Igor Jesus",
       ("MUN", "Fernandes"): "B.Fernandes", ("NFO", "Williams"): "N.Williams",
       ("FUL", "Gonzalo"): "Gonzalo", ("BRE", "Thiago"): "Thiago",
       ("BHA", "Rutter"): "Georginio", ("MUN", "Diallo"): "Amad",
       ("LIV", "Alisson"): "A.Becker", ("BRE", "Ouattara"): "O.Dango",
       ("BHA", "Kadioglu"): "Kadıoğlu", ("AVL", "Torres"): "Pau",
       ("IPS", "Luis"): "Florentino", ("HUL", "Hjerto-Dahl"): "Hjertø-Dahl"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


def main():
    M = json.load(open(os.path.join(HERE, "model.json")))
    PL = M["players"]
    out, miss = {}, []
    for club, line in XI.items():
        pool = [p for p in PL if p["c"] == club]
        for token in line.replace("|", " ").split():
            want = PIN.get((club, token), token)
            hit = next((p for p in pool if norm(p["n"]) == norm(want)), None)
            if not hit:
                hit = next((p for p in pool if norm(want) and
                            (norm(want) in norm(p["n"]) or norm(p["n"]) in norm(want))), None)
            if hit:
                out[str(hit["id"])] = 1
            else:
                miss.append(f"{club}:{token}")
    json.dump(out, open(os.path.join(HERE, "xi_gw1.json"), "w"))
    print(f"XI players matched: {len(out)} of {20*11}")
    if miss:
        print(f"unmatched ({len(miss)}):", ", ".join(miss))
    return out


if __name__ == "__main__":
    main()
