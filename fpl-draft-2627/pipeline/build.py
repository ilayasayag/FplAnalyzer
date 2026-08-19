#!/usr/bin/env python3
"""Rebuild the 26/27 FPL draft model: DF240 projections x 3-board market ADP."""
import json, statistics, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
DIST = os.path.join(ROOT, "app")
data = json.load(open(os.path.join(DATA, "sources.json")))

# ---- canonical name aliases (board spelling -> DF name) ----
ALIAS = {
    "Fernandes B.": "B.Fernandes",
    "Gonzalo": "García",          # Gonzalo García, FUL
    "Alisson Becker": "A.Becker",
    "Virgil van Dijk": "Virgil",
}

# Players drafted on boards but absent from the DF top-240.
# pos/club best-effort (club from board C's printed label where available).
EXTRAS = {
    "Wissa":       ("FWD", "NEW"), "Mosquera":   ("DEF", "ARS"),
    "Frimpong":    ("DEF", "LIV"), "Kluivert":   ("MID", "BOU"),
    "Kerkez":      ("DEF", "LIV"), "Mings":      ("DEF", "AVL"),
    "Netz":        ("DEF", "BHA"), "Tonali":     ("MID", "TOT"),
    "Manzambi":    ("MID", "AVL"), "Tielemans":  ("MID", "MUN"),
    "Mazraoui":    ("DEF", "MUN"), "Kostoulas":  ("FWD", "BHA"),
    "Sánchez":     ("GKP", "CHE"), "Leno":       ("GKP", "FUL"),
    "Hall":        ("DEF", "NEW"), "Dubravka":   ("GKP", "HUL"),
    "Maatsen":     ("DEF", "AVL"), "Ngumoha":    ("FWD", "LIV"),
    "Konsa":       ("DEF", "AVL"), "Shaw":       ("DEF", "MUN"),
    "Petrović":    ("GKP", "BOU"), "Scherpen":   ("GKP", "IPS"),
    "Ouattara":    ("MID", "BRE"), "Antonee Robinson": ("DEF", "FUL"),
    "Kayode":      ("DEF", "BRE"), "B.Thomas":   ("DEF", "COV"),
    "Angulo":      ("MID", "SUN"), "Bobb":       ("MID", "FUL"),
    "De Cuyper":   ("DEF", "BHA"), "Tel":        ("FWD", "TOT"),
    "Rutter":      ("MID", "BHA"), "Elanga":     ("MID", "NEW"),
    "Mitoma":      ("MID", "BHA"), "Mainoo":     ("MID", "MUN"),
    "Lisandro Martínez": ("DEF", "MUN"),
    "Pino":        ("MID", "CRY"), "Mingueza":   ("DEF", "CRY"),
    "Hume":        ("DEF", "SUN"), "Joao Gomes": ("MID", "AVL"),
    "Diop":        ("DEF", "IPS"), "Davis":      ("DEF", "IPS"),
    "Hutchinson":  ("MID", "NFO"), "Estevao":    ("MID", "CHE"),
    "Ndoye":       ("MID", "NFO"), "Maeda":      ("FWD", "IPS"),
    "Bergvall":    ("MID", "TOT"), "Lewis-Skelly": ("DEF", "ARS"),
    "George":      ("DEF", "EVE"), "Mykolenko":  ("DEF", "EVE"),
    "Savio":       ("MID", "MCI"), "Hamer":      ("MID", "COV"),
    "Barco":       ("DEF", "CHE"), "Belloumi":   ("MID", "HUL"),
    "Bogle":       ("DEF", "LEE"), "Abdul Fatawu": ("FWD", "IPS"),
    "van Ewijk":   ("DEF", "COV"), "Andrey Santos": ("MID", "MUN"),
    "Reinildo":    ("DEF", "SUN"), "Gusto":      ("DEF", "CHE"),
    "Struijk":     ("DEF", "BHA"), "Ramsey":     ("MID", "NEW"),
    "Kevin":       ("MID", "FUL"), "Philogene":  ("MID", "IPS"),
    "Kitching":    ("DEF", "COV"), "Robertson":  ("DEF", "TOT"),
    "Jensen":      ("MID", "BRE"), "Hackney":    ("MID", "HUL"),
    "Jacob Murphy":("MID", "NEW"), "Wesley Fofana": ("DEF", "CHE"),
}

df = {}
for rank, name, club, pos, tier, xp, edge in data["df240"]:
    df[name] = dict(rank=rank, name=name, club=club, pos=pos, tier=tier, xp=xp, edge=edge)

def canon(n):
    return ALIAS.get(n, n)

# ---- boards -> overall picks -> fractional rounds ----
picks_by_player = {}   # name -> {boardId: fractional_round}
board_meta = []
for b in data["boards"]:
    teams = len(b["teams"]); rounds = len(b["rows"])
    board_meta.append(dict(id=b["id"], label=b["label"], teams=teams, rounds=rounds))
    seen = set()
    for r, row in enumerate(b["rows"], start=1):
        if len(row) != teams:
            print(f"!! board {b['id']} round {r}: {len(row)} cells, expected {teams}")
        for c, raw in enumerate(row, start=1):
            name = canon(raw)
            pick_in_round = c if r % 2 == 1 else teams + 1 - c
            overall = (r - 1) * teams + pick_in_round
            fr = (overall - 1) / teams + 1.0
            if name in seen:
                print(f"!! board {b['id']}: duplicate pick of {name} (round {r})")
            seen.add(name)
            picks_by_player.setdefault(name, {})[b["id"]] = round(fr, 3)

# ---- assemble player table ----
players = {}
for name, p in df.items():
    players[name] = dict(p, est=False)
for name in picks_by_player:
    if name not in players:
        if name in EXTRAS:
            pos, club = EXTRAS[name]
        else:
            pos, club = "?", "?"
            print(f"!! no metadata for unmatched board player: {name}")
        players[name] = dict(rank=None, name=name, club=club, pos=pos, tier=None,
                             xp=None, edge=None, est=True)

# consensus ADP: mean fractional round; boards where undrafted impute rounds+1
imputes = {bm["id"]: bm["rounds"] + 1 for bm in board_meta}
for name, p in players.items():
    got = picks_by_player.get(name, {})
    samples_all = [got.get(bm["id"], imputes[bm["id"]]) for bm in board_meta]
    p["adpByBoard"] = got
    p["draftedIn"] = len(got)
    p["adpFr"] = round(sum(samples_all) / len(samples_all), 2)
    real = list(got.values())
    p["adpSigma"] = round(max(0.6, statistics.pstdev(samples_all)), 2)
    p["adpFrDraftedOnly"] = round(sum(real) / len(real), 2) if real else None

# ---- estimate xp/edge for unmatched via ADP->edge interpolation ----
matched = sorted((p for p in players.values() if not p["est"] and p["draftedIn"] > 0),
                 key=lambda p: p["adpFr"])
xs = [p["adpFr"] for p in matched]; es = [p["edge"] for p in matched]
pos_floor_xp = {}
for p in players.values():
    if not p["est"]:
        pos_floor_xp[p["pos"]] = min(pos_floor_xp.get(p["pos"], 1e9), p["xp"])

def interp_edge(fr):
    if fr <= xs[0]: return es[0]
    if fr >= xs[-1]: return es[-1]
    for i in range(1, len(xs)):
        if xs[i] >= fr:
            w = (fr - xs[i-1]) / (xs[i] - xs[i-1] or 1)
            return es[i-1] + w * (es[i] - es[i-1])
    return es[-1]

for p in players.values():
    if p["est"]:
        e = round(interp_edge(p["adpFr"]), 1)
        p["edge"] = e
        p["xp"] = round(pos_floor_xp.get(p["pos"], 100) + max(e, 0) + 10, 1)

# value rank across everyone (DF rank primary; est players slotted by edge)
ordered = sorted(players.values(), key=lambda p: -p["edge"])
for i, p in enumerate(ordered, 1):
    p["valueRank"] = i

# market rank by consensus ADP
mkt = sorted(players.values(), key=lambda p: (p["adpFr"], -(p["edge"])))
for i, p in enumerate(mkt, 1):
    p["adpRank"] = i
for p in players.values():
    p["delta"] = p["adpRank"] - p["valueRank"]   # + = market lets him fall = STEAL
    p["injury"] = data["injuries"].get(p["name"])
    p["fixtures"] = data["fixtures"].get(p["club"])

out = dict(meta=data["meta"], boards=board_meta,
           players=sorted(players.values(), key=lambda p: p["adpRank"]),
           fixtures=data["fixtures"])
json.dump(out, open(os.path.join(DATA, "model.json"), "w"), ensure_ascii=False, indent=1)

# inline the model into the standalone artifact page
payload = json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = open(os.path.join(HERE, "template.html")).read().replace("__MODEL_JSON__", payload)
open(os.path.join(DIST, "warroom.html"), "w").write(html)
print(f"wrote data/model.json and app/warroom.html ({len(html)} bytes)")

# ---- validation report ----
n_est = sum(1 for p in players.values() if p["est"])
n_drafted = sum(1 for p in players.values() if p["draftedIn"] > 0)
print(f"players total={len(players)} df240={len(df)} boardDrafted={n_drafted} estimated={n_est}")
print("\n== consensus market top 25 (by ADP) ==")
for p in list(out["players"])[:25]:
    print(f"  {p['adpRank']:>3}. {p['name']:<18} {p['pos']:<3} {p['club']:<3} adpFr={p['adpFr']:<5} edge={p['edge']:>6} vRank={p['valueRank']:>3} Δ={p['delta']:>4}")
print("\n== biggest STEALS (value high, market sleeps; drafted in >=2 boards) ==")
steals = sorted((p for p in players.values() if p["draftedIn"] >= 2 and p["valueRank"] <= 80),
                key=lambda p: -p["delta"])[:15]
for p in steals:
    print(f"  {p['name']:<18} {p['pos']:<3} vRank={p['valueRank']:>3} adpRank={p['adpRank']:>3} Δ=+{p['delta']} adpFr={p['adpFr']}")
print("\n== biggest REACHES (market loves, model doesn't) ==")
reaches = sorted((p for p in players.values() if p["draftedIn"] >= 2 and p["adpRank"] <= 60),
                 key=lambda p: p["delta"])[:15]
for p in reaches:
    print(f"  {p['name']:<18} {p['pos']:<3} vRank={p['valueRank']:>3} adpRank={p['adpRank']:>3} Δ={p['delta']} adpFr={p['adpFr']}")
print("\n== DF top-60 never drafted in any of the 3 boards ==")
for p in sorted(players.values(), key=lambda p: p["valueRank"]):
    if p["valueRank"] <= 60 and p["draftedIn"] == 0:
        print(f"  vRank={p['valueRank']:>3} {p['name']} {p['pos']} {p['club']} edge={p['edge']}")
