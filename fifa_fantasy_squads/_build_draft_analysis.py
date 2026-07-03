#!/usr/bin/env python3
"""Build wc_draft_analysis.html — two analyses:
  A) Best 8 nations to target for easy GROUP-STAGE fixtures (all 3 rounds).
     Nation strength derived from FIFA squad prices (top-15 sum). Fixture-ease
     for a nation = sum over its 3 opponents of (oppRank - myRank), PLUS a flat
     bonus per opponent that is one of the 6 designated weak teams.
  B) Ilay's 91-player draft watchlist: position + nation breakdown, plus several
     balanced 2/5/5/3 squads (<=3 per nation) drafted by his watchlist ranking.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "wc_draft_analysis.html")
FIFA_TO_DB = {"BIH": "BOS", "IRN": "IRA", "JPN": "JAP", "MAR": "MOR",
              "KSA": "SAU", "ESP": "SPA", "SUI": "SWI"}
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}
WEAK6 = {"CUW", "CPV", "UZB", "JOR", "IRQ", "COD"}   # Curaçao, Cape Verde, Uzbekistan, Jordan, Iraq, Congo DR
WEAK_BONUS = 15      # flat "extra easy" bonus per weak-6 opponent
TOP_N_TARGET = 8
STRENGTH_TOPK = 15   # nation strength = sum of its top-15 FIFA player prices

# ------------------------------------------------------------- group schedule
SCHEDULE = {
 1: [("A","MEX","RSA"),("A","KOR","CZE"),("B","CAN","BOS"),("D","USA","PAR"),
     ("B","QAT","SWI"),("C","BRA","MOR"),("C","HAI","SCO"),("D","AUS","TUR"),
     ("E","GER","CUW"),("F","NED","JAP"),("E","CIV","ECU"),("F","SWE","TUN"),
     ("H","SPA","CPV"),("G","BEL","EGY"),("H","SAU","URU"),("G","IRA","NZL"),
     ("I","FRA","SEN"),("I","IRQ","NOR"),("J","ARG","ALG"),("J","AUT","JOR"),
     ("K","POR","COD"),("L","ENG","CRO"),("L","GHA","PAN"),("K","UZB","COL")],
 2: [("A","CZE","RSA"),("B","SWI","BOS"),("B","CAN","QAT"),("A","MEX","KOR"),
     ("D","USA","AUS"),("C","SCO","MOR"),("C","BRA","HAI"),("D","TUR","PAR"),
     ("F","NED","SWE"),("E","GER","CIV"),("E","ECU","CUW"),("F","TUN","JAP"),
     ("H","SPA","SAU"),("G","BEL","IRA"),("H","URU","CPV"),("G","NZL","EGY"),
     ("J","ARG","AUT"),("I","FRA","IRQ"),("I","NOR","SEN"),("J","JOR","ALG"),
     ("K","POR","UZB"),("L","ENG","GHA"),("L","PAN","CRO"),("K","COL","COD")],
 3: [("B","SWI","CAN"),("B","BOS","QAT"),("C","MOR","HAI"),("C","SCO","BRA"),
     ("A","RSA","KOR"),("A","CZE","MEX"),("E","ECU","GER"),("E","CUW","CIV"),
     ("F","TUN","NED"),("F","JAP","SWE"),("D","TUR","USA"),("D","PAR","AUS"),
     ("I","NOR","FRA"),("I","SEN","IRQ"),("H","URU","SPA"),("H","CPV","SAU"),
     ("G","NZL","BEL"),("G","EGY","IRA"),("L","CRO","GHA"),("L","PAN","ENG"),
     ("K","COD","UZB"),("K","COL","POR"),("J","JOR","ARG"),("J","ALG","AUT")],
}

# ------------------------------------------------------------- watchlist (ranked)
WATCHLIST = """\
1|900854|Kylian Mbappé|4|FRA
2|901160|Harry Kane|4|ENG
3|900953|Julián Alvarez|4|ARG
4|900855|Michael Olise|3|FRA
5|901051|Bruno Fernandes|3|POR
6|900231|Raphinha|3|BRA
7|900954|Lionel Messi|4|ARG
8|900745|Lamine Yamal|3|SPA
9|900928|Erling Haaland|4|NOR
10|900749|Mikel Oyarzabal|4|SPA
11|900438|Kai Havertz|4|GER
12|901056|Cristiano Ronaldo|4|POR
13|900851|Ousmane Dembélé|3|FRA
14|901159|Bukayo Saka|3|ENG
15|900233|Vinícius Júnior|3|BRA
16|900673|Mohamed Salah|3|EGY
17|900431|Jamal Musiala|3|GER
18|900540|Cody Gakpo|4|NED
19|900430|Florian Wirtz|3|GER
20|901208|Antoine Semenyo|4|GHA
21|900642|Jérémy Doku|3|BEL
22|901044|Nuno Mendes|2|POR
23|900237|Achraf Hakimi|2|MOR
24|900421|Joshua Kimmich|2|GER
25|900839|Jules Koundé|2|FRA
26|900730|Marc Cucurella|2|SPA
27|900529|Virgil van Dijk|2|NED
28|900423|Antonio Rüdiger|2|GER
29|900524|Denzel Dumfries|2|NED
30|900225|Endrick|4|BRA
31|900216|Gabriel Magalhães|2|BRA
32|900734|Pedro Porro|2|SPA
33|900841|William Saliba|2|FRA
34|901390|Jeremie Frimpong|2|NED
35|900731|Pau Cubarsí|2|SPA
36|900110|Alphonso Davies|2|CAN
37|900523|Nathan Aké|2|NED
38|900595|Alexander Isak|4|SWE
39|900643|Romelu Lukaku|4|BEL
40|900539|Memphis Depay|4|NED
41|900099|Patrik Schick|4|CZE
42|900019|Raúl Jiménez|4|MEX
43|900929|Alexander Sørloth|4|NOR
44|900204|Dan Ndoye|4|SWI
45|900876|Ismaïla Sarr|4|SEN
46|900952|Enzo Fernández|3|ARG
47|900637|Kevin De Bruyne|3|BEL
48|900127|Jonathan David|4|CAN
49|901135|Luis Díaz|3|COL
50|901131|James Rodríguez|3|COL
51|900253|Brahim Díaz|3|MOR
52|900921|Martin Ødegaard|3|NOR
53|901057|Rafael Leão|3|POR
54|901049|Vitinha|3|POR
55|900740|Pedri|3|SPA
56|900747|Dani Olmo|3|SPA
57|900727|Unai Simón|1|SPA
58|900203|Breel Embolo|4|SWI
59|900402|Hakan Çalhanoglu|3|TUR
60|900407|Arda Güler|3|TUR
61|900819|Federico Valverde|3|URU
62|900831|Mike Maignan|1|FRA
63|900416|Manuel Neuer|1|GER
64|901141|Jordan Pickford|1|ENG
65|900234|Yassine Bounou|1|MOR
66|900188|Ricardo Rodríguez|2|SWI
67|900474|Guéla Doué|2|CIV
68|900487|Amad Diallo|4|CIV
69|900543|Donyell Malen|4|NED
70|900534|Tijjani Reijnders|3|NED
71|901043|João Cancelo|2|POR
72|900631|Maxim De Cuyper|2|BEL
73|900836|Lucas Hernández|2|FRA
74|900842|Dayot Upamecano|2|FRA
75|900850|Rayan Cherki|3|FRA
76|900875|Sadio Mané|3|SEN
77|900880|Nicolas Jackson|4|SEN
78|901050|João Neves|3|POR
79|901062|Pedro Neto|3|POR
80|900937|Emiliano Martínez|1|ARG
81|900520|Bart Verbruggen|1|NED
82|900857|Édouard Mendy|1|SEN
83|900624|Thibaut Courtois|1|BEL
84|900209|Alisson Becker|1|BRA
85|901038|Diogo Costa|1|POR
86|900732|Aymeric Laporte|2|SPA
87|900674|Omar Marmoush|4|EGY
88|900748|Ferran Torres|4|SPA
89|900746|Nico Williams|3|SPA
90|900594|Viktor Gyökeres|4|SWE
91|900852|Désiré Doué|3|FRA"""


def nation_strength():
    """db_iso -> (strength, fullname). strength = sum of top-15 FIFA prices."""
    out = {}
    for fn in os.listdir(HERE):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        d = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
        iso = FIFA_TO_DB.get(d["abbr"], d["abbr"])
        prices = sorted((p.get("price") or 0 for p in d["players"]), reverse=True)
        out[iso] = (round(sum(prices[:STRENGTH_TOPK]), 1), d["team"])
    return out


def main():
    strength = nation_strength()
    # rank nations 1..N by strength desc (1 = strongest)
    ranked = sorted(strength.items(), key=lambda kv: -kv[1][0])
    rank = {iso: i + 1 for i, (iso, _) in enumerate(ranked)}
    name = {iso: v[1] for iso, v in strength.items()}

    # opponents per nation across all 3 rounds
    opps = {}
    for gw, games in SCHEDULE.items():
        for grp, h, a in games:
            opps.setdefault(h, []).append((gw, a))
            opps.setdefault(a, []).append((gw, h))

    # ---- Part A: fixture-ease score
    partA = []
    for iso in strength:
        my = rank[iso]
        breakdown, score = [], 0
        for gw, o in sorted(opps.get(iso, [])):
            delta = rank.get(o, 48) - my            # positive = opponent weaker
            bonus = WEAK_BONUS if o in WEAK6 else 0
            contrib = delta + bonus
            score += contrib
            breakdown.append((gw, o, rank.get(o, 48), delta, bonus, contrib, o in WEAK6))
        partA.append({"iso": iso, "name": name[iso], "rank": my,
                      "strength": strength[iso][0], "score": score, "bd": breakdown})
    partA.sort(key=lambda x: -x["score"])
    for i, r in enumerate(partA):
        r["ease_rank"] = i + 1
    target8 = [r["iso"] for r in partA[:TOP_N_TARGET]]

    # ---- Part B: parse watchlist
    wl = []
    for line in WATCHLIST.splitlines():
        rk, pid, nm, pos, iso = line.split("|")
        wl.append({"rank": int(rk), "id": pid, "name": nm, "pos": int(pos), "iso": iso})
    bypos = {1: 0, 2: 0, 3: 0, 4: 0}
    bynat = {}
    for p in wl:
        bypos[p["pos"]] += 1
        bynat[p["iso"]] = bynat.get(p["iso"], 0) + 1

    def build_squad(ordered, prefer=None, exclude=None):
        exclude = exclude or set()
        squad, pc, nc = [], {1: 0, 2: 0, 3: 0, 4: 0}, {}
        def try_add(p):
            if p["id"] in exclude or any(s["id"] == p["id"] for s in squad):
                return
            if pc[p["pos"]] >= QUOTA[p["pos"]] or nc.get(p["iso"], 0) >= 3:
                return
            squad.append(p); pc[p["pos"]] += 1; nc[p["iso"]] = nc.get(p["iso"], 0) + 1
        conds = ([lambda p: p["iso"] in prefer] if prefer else []) + [lambda p: True]
        for cond in conds:
            for p in ordered:
                if len(squad) >= 15:
                    break
                if cond(p):
                    try_add(p)
            if len(squad) >= 15:
                break
        return squad, pc, nc

    sqA, pcA, ncA = build_squad(wl)
    sqB, pcB, ncB = build_squad(wl, prefer=set(target8))
    used = {p["id"] for p in sqA}
    sqC, pcC, ncC = build_squad(wl, exclude=used)   # "second team" from the remainder

    write_html(partA, target8, rank, name, strength, wl, bypos, bynat,
               [("Highest-ranked balanced XV", "Pure watchlist order — your top picks that still fit 2/5/5/3 with ≤3 per nation.", sqA, pcA, ncA),
                ("Easy-fixtures balanced XV", "Same ranking, but prioritising players from the 8 best-fixture nations (Part A) before filling gaps.", sqB, pcB, ncB),
                ("Second-string balanced XV", "Best balanced XV from everyone NOT in squad #1 — your depth / fallback team.", sqC, pcC, ncC)])
    print("nations ranked:", len(rank))
    print("Part A top 8:", [f"{r['name']}({r['score']})" for r in partA[:8]])
    print("watchlist:", len(wl), "byPos", {POS[k]: v for k, v in bypos.items()})
    for label, _, sq, pc, _ in [("A", 0, sqA, pcA, 0), ("B", 0, sqB, pcB, 0), ("C", 0, sqC, pcC, 0)]:
        print(f"squad {label}: {len(sq)} players {[pc[i] for i in (1,2,3,4)]}")
    print("Wrote", os.path.relpath(OUT, os.path.join(HERE, "..")))


def write_html(partA, target8, rank, name, strength, wl, bypos, bynat, squads):
    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    POSCLR = {1: "#6b7280", 2: "#2563eb", 3: "#16a34a", 4: "#dc2626"}
    H = []
    H.append("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>WC26 Draft Analysis — Ilay</title>
<style>
*{box-sizing:border-box} body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1226;color:#e8eaf2}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:30px;margin:0 0 4px} h2{font-size:22px;margin:34px 0 6px;border-bottom:2px solid #2e3358;padding-bottom:8px}
h3{font-size:16px;margin:20px 0 8px;color:#c9cdf0} .sub{color:#9aa0c7;font-size:14px;margin:0 0 16px}
.card{background:#171b35;border:1px solid #2a2f55;border-radius:12px;padding:16px 18px;margin:14px 0}
.grid{display:grid;gap:12px} .g4{grid-template-columns:repeat(4,1fr)} .g3{grid-template-columns:repeat(3,1fr)}
.stat{background:#1d2243;border:1px solid #313769;border-radius:10px;padding:14px;text-align:center}
.stat .n{font-size:30px;font-weight:800} .stat .l{font-size:12px;color:#9aa0c7;text-transform:uppercase;letter-spacing:.06em}
table{width:100%;border-collapse:collapse;font-size:13px} th,td{padding:7px 9px;text-align:left;border-bottom:1px solid #262b50}
th{color:#9aa0c7;font-size:11px;text-transform:uppercase;letter-spacing:.05em} tr:hover td{background:#1b2042}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;color:#fff}
.tag{font-size:10px;font-weight:800;padding:1px 6px;border-radius:5px;background:#3b2f12;color:#f5c518;margin-left:6px}
.weak{color:#f5c518;font-weight:700} .pos{font-weight:800;font-size:11px}
.good{color:#34d399} .bad{color:#f87171} .muted{color:#8b91bd}
.rown{display:flex;align-items:center;gap:8px} .rk{color:#8b91bd;width:26px;text-align:right;font-variant-numeric:tabular-nums}
.target{background:#13301f !important}
.formula{background:#10142e;border-left:3px solid #f5c518;padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;color:#cfd3f5}
.sqcard{background:#171b35;border:1px solid #2a2f55;border-radius:12px;padding:14px 16px}
.sqhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
small{color:#8b91bd}
</style></head><body><div class="wrap">""")
    H.append("<h1>WC 2026 Draft Analysis · Ilay</h1>")
    H.append('<p class="sub">Nation strength derived from FIFA fantasy squad prices (sum of each team\'s top-15 player prices). Group-stage schedule = all 3 rounds.</p>')

    # ---------- Part A
    H.append("<h2>A · Best 8 nations to target — easiest group-stage fixtures</h2>")
    H.append('<div class="formula"><b>Scoring per nation</b> = sum over its 3 group opponents of '
             '<b>(opponent’s strength-rank − my strength-rank)</b> '
             '<span class="muted">(positive = opponent is weaker = easier)</span> '
             f'<b>+ {WEAK_BONUS} bonus</b> for every opponent that is one of the 6 designated weak teams '
             '<span class="weak">(Curaçao, Cape Verde, Uzbekistan, Jordan, Iraq, Congo DR)</span>. Higher total = easier run.</div>')
    H.append('<div class="card"><h3 style="margin-top:0">🎯 Recommended 8 nations</h3><div class="grid g4">')
    for r in partA[:TOP_N_TARGET]:
        H.append(f'<div class="stat target"><div class="n">{esc(r["name"])}</div>'
                 f'<div class="l">ease {r["score"]} · str#{r["rank"]}</div></div>')
    H.append("</div></div>")
    H.append('<div class="card"><table><thead><tr><th>#</th><th>Nation</th><th>Str rank</th>'
             '<th>GW1 opp</th><th>GW2 opp</th><th>GW3 opp</th><th>Ease score</th></tr></thead><tbody>')
    for r in partA:
        cells = {1: "", 2: "", 3: ""}
        for gw, o, orank, delta, bonus, contrib, isweak in r["bd"]:
            wk = ' <span class="tag">WEAK</span>' if isweak else ""
            cells[gw] = f'{esc(o)} <small>(#{orank}, +{contrib})</small>{wk}'
        cls = ' class="target"' if r["iso"] in target8 else ""
        H.append(f'<tr{cls}><td>{r["ease_rank"]}</td><td><b>{esc(r["name"])}</b> <small>{esc(r["iso"])}</small></td>'
                 f'<td>#{r["rank"]}</td><td>{cells[1]}</td><td>{cells[2]}</td><td>{cells[3]}</td>'
                 f'<td style="font-weight:800;font-size:15px">{r["score"]}</td></tr>')
    H.append("</tbody></table></div>")

    # ---------- Part B stats
    H.append("<h2>B · Ilay’s draft watchlist — 91 players</h2>")
    H.append('<div class="grid g4">')
    for pos in (1, 2, 3, 4):
        H.append(f'<div class="stat"><div class="n" style="color:{POSCLR[pos]}">{bypos[pos]}</div><div class="l">{POS[pos]}</div></div>')
    H.append("</div>")
    H.append('<div class="card"><h3 style="margin-top:0">By nation</h3><div class="grid g4">')
    for iso, c in sorted(bynat.items(), key=lambda kv: -kv[1]):
        tgt = ' class="weak"' if iso in target8 else ""
        H.append(f'<div class="stat"><div class="n"{tgt}>{c}</div><div class="l">{esc(name.get(iso, iso))}</div></div>')
    H.append("</div></div>")

    # ---------- Part B squads
    H.append("<h3>Balanced squad options (2 GK / 5 DEF / 5 MID / 3 FWD · max 3 per nation)</h3>")
    for label, desc, sq, pc, nc in squads:
        H.append('<div class="sqcard">')
        natstr = ", ".join(f"{k}×{v}" for k, v in sorted(nc.items(), key=lambda x: -x[1]))
        H.append(f'<div class="sqhead"><h3 style="margin:0">{esc(label)}</h3>'
                 f'<small>{pc[1]} GK · {pc[2]} DEF · {pc[3]} MID · {pc[4]} FWD</small></div>')
        H.append(f'<p class="sub" style="margin:0 0 10px">{esc(desc)} <br><small>Nations: {esc(natstr)}</small></p>')
        H.append('<table><thead><tr><th>Pos</th><th>Player</th><th>Nation</th><th>My rank</th><th>Fixture ease</th></tr></thead><tbody>')
        order = sorted(sq, key=lambda p: (p["pos"], p["rank"]))
        easemap = {r["iso"]: r["score"] for r in partA}
        for p in order:
            ease = easemap.get(p["iso"], 0)
            ecls = "good" if p["iso"] in target8 else ("bad" if ease < 0 else "muted")
            etag = ' <span class="tag">TOP-8</span>' if p["iso"] in target8 else ""
            H.append(f'<tr><td class="pos" style="color:{POSCLR[p["pos"]]}">{POS[p["pos"]]}</td>'
                     f'<td>{esc(p["name"])}</td><td>{esc(name.get(p["iso"], p["iso"]))}</td>'
                     f'<td class="rk">#{p["rank"]}</td>'
                     f'<td class="{ecls}">{ease}{etag}</td></tr>')
        H.append("</tbody></table></div>")

    H.append('<p class="sub" style="margin-top:30px">Generated from Ilay’s live watchlist + FIFA fantasy prices + the real group-stage schedule.</p>')
    H.append("</div></body></html>")
    open(OUT, "w", encoding="utf-8").write("".join(H))


if __name__ == "__main__":
    main()
