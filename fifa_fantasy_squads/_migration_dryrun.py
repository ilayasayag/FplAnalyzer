#!/usr/bin/env python3
"""READ-ONLY dry run for the DB->FIFA alignment migration.

Computes, WITHOUT writing anything:
  - pool-level changes: position flips (103), renames (95), adds (246), drops (10)
  - per-manager squad impact: which players flip position, which get renamed,
    and the MINIMAL rebalance swaps needed to restore a valid 2/5/5/3 squad
    (drop the lowest-FIFA-value player in each surplus position; add the
     highest-FIFA-value free agent in each deficit position)
  - which position-flipped owned players will change GW1/GW2 points

Outputs _migration_dryrun.json + _migration_dryrun.md
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_INT = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
QUOTA = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
ROSTER = ["u_ilay", "u_yuval", "u_netanel", "u_shay", "u_nadav", "u_roy"]
FIFA_TO_DB = {"BIH": "BOS", "IRN": "IRA", "JPN": "JAP", "MAR": "MOR",
              "KSA": "SAU", "ESP": "SPA", "SUI": "SWI"}
MANUAL = {"ø": "o", "œ": "oe", "æ": "ae", "ß": "ss", "đ": "d", "ð": "d",
          "ł": "l", "ı": "i", "þ": "th", "ħ": "h", "ŧ": "t"}

# live squads: "playerId|name|teamIso|positionInt"
SQUADS_RAW = {
"u_ilay": """901228|Éric Davis|PAN|2
901039|Rui Silva|POR|1
900950|Nicolás González|ARG|3
900148|Dženis Burnić|BOS|3
900231|Raphinha|BRA|4
900841|William Saliba|FRA|2
900430|Florian Wirtz|GER|3
900423|Antonio Rüdiger|GER|2
900629|Arthur Theate|BEL|2
900857|Édouard Mendy|SEN|1
900253|Brahim Diaz|MOR|4
900118|Tajon Buchanan|CAN|3
900047|Lyle Foster|RSA|4
900015|Obed Vargas|MEX|3
900397|Merih Demiral|TUR|2""",
"u_yuval": """900504|Moisés Caicedo|ECU|3
900205|Rubén Vargas|SWI|4
900668|Marwan Attia|EGY|3
900474|Guéla Doué|CIV|2
900237|Achraf Hakimi|MOR|2
900731|Pau Cubarsí|SPA|2
900727|Unai Simón|SPA|1
900502|Joel Ordóñez|ECU|2
900806|Santiago Mele|URU|1
900233|Vinicius Júnior|BRA|4
900008|Israel Reyes|MEX|2
901006|Nicolas Seiwald|AUT|3
900021|Santiago Giménez|MEX|4
900223|Fabinho|BRA|3
900640|Nicolas Raskin|BEL|3""",
"u_netanel": """900221|Bruno Guimarães|BRA|3
900530|Frenkie de Jong|NED|3
900392|Ugurcan Cakir|TUR|1
900554|Hiroki Ito|JAP|2
901176|Martin Erlic|CRO|2
900216|Gabriel Magalhães|BRA|2
901209|Elisha Owusu|GHA|3
900997|Michael Svoboda|AUT|2
900458|Ar'jany Martha|CUW|3
901010|Michael Gregoritsch|AUT|4
900114|Richie Laryea|CAN|2
900566|Yuito Suzuki|JAP|3
900261|Alexandre Pierre|HAI|1
900567|Koki Ogawa|JAP|4
900130|Tani Oluwaseyi|CAN|4""",
"u_shay": """901205|Caleb Yirenkyi|GHA|3
900373|Harry Souttar|AUS|2
900200|Ardon Jashari|SWI|3
900529|Virgil van Dijk|NED|2
901144|Ezri Konsa|ENG|2
900737|Marc Pubill|SPA|2
900844|Manu Kone|FRA|3
900326|Sebastian Berhalter|USA|3
900675|Alireza Beiranvand|IRA|1
901142|Dean Henderson|ENG|1
900726|Lachlan Bayliss|NZL|4
900957|Nico Paz|ARG|4
901119|Santiago Arias|COL|2
900126|Jacob Shaffelburg|CAN|3
900514|Enner Valencia|ECU|4""",
"u_nadav": """900929|Alexander Sorloth|NOR|4
900350|Diego Gómez|PAR|3
900644|Leandro Trossard|BEL|3
900985|Riyad Mahrez|ALG|4
900899|Aimar Sher|IRQ|3
900028|Sipho Chaine|RSA|1
900395|Eren Elmali|TUR|2
900784|Jehad Thikri|SAU|2
900293|Jack Hendry|SCO|2
901122|Jhon Lucumí|COL|2
900107|Dayne St. Clair|CAN|1
900059|Lee Tae-seok|KOR|2
900952|Enzo Fernández|ARG|3
900797|Alaa Al Hajji|SAU|3
900259|Yassine Gessime|MOR|4""",
"u_roy": """900751|Borja Iglesias|SPA|4
900360|Julio Enciso|PAR|4
900421|Joshua Kimmich|GER|2
900532|Ryan Gravenberch|NED|3
900736|Marcos Llorente|SPA|2
901178|Luka Modric|CRO|3
901046|Nélson Semedo|POR|2
900144|Ivan Bašić|BOS|3
900916|Kristoffer Ajer|NOR|2
901042|Gonçalo Inácio|POR|2
900728|David Raya|SPA|1
900949|Exequiel Palacios|ARG|3
900750|Yéremy Pino|SPA|3
900211|Weverton|BRA|1
900699|Shahriar Moghanlou|IRA|4""",
}


def norm(s):
    s = s.lower()
    s = "".join(MANUAL.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", " ").replace(".", " ").replace("-", " ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    rep = json.load(open(os.path.join(HERE, "_diff_report.json"), encoding="utf-8"))
    fz = json.load(open(os.path.join(HERE, "_fuzzy_pairs.json"), encoding="utf-8"))

    # (iso, norm(db_name)) -> fifa position string  (exact-match position flips)
    posdiff = {(d["team"], norm(d["player"])): d["fifa_position"]
               for d in rep["position_diffs"]}
    # (iso, norm(db_name)) -> {fifa_name, fifa_position}  (fuzzy renames)
    fuzzy = {(p["team"], norm(p["db_name"])): p for p in fz["pairs"]}
    truly_missing = {(d["team"], norm(d["player"]))
                     for d in fz["db_only_truly_missing"]}

    # FIFA pool: db_iso -> list of {name, pos, price}; also a global price rank
    fifa_pool = {}
    for fn in os.listdir(HERE):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        data = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
        iso = FIFA_TO_DB.get(data["abbr"], data["abbr"])
        for p in data["players"]:
            fifa_pool.setdefault(iso, []).append({
                "name": p["name"], "norm": norm(p["name"]),
                "pos": p["position"], "price": p.get("price") or 0,
            })

    # ----- resolve every owned squad player to its FIFA identity + new pos
    squads = {}
    owned = set()  # (iso, norm fifa name)
    for uid in ROSTER:
        players = []
        for line in SQUADS_RAW[uid].splitlines():
            pid, name, iso, posi = line.split("|")
            cur = POS_NAMES[int(posi)]
            nn = norm(name)
            new_name, new_pos, why = name, cur, None
            if (iso, nn) in truly_missing:
                why = "drop-not-in-fifa"
                new_pos = None
            elif (iso, nn) in posdiff:
                new_pos = posdiff[(iso, nn)]
                if new_pos != cur:
                    why = "flip"
            elif (iso, nn) in fuzzy:
                fp = fuzzy[(iso, nn)]
                new_name = fp["fifa_name"]
                new_pos = fp["fifa_position"]
                if fp["fifa_name"] != name and new_pos != cur:
                    why = "rename+flip"
                elif fp["fifa_name"] != name:
                    why = "rename"
                elif new_pos != cur:
                    why = "flip"
            players.append({"pid": pid, "old_name": name, "new_name": new_name,
                            "iso": iso, "old_pos": cur, "new_pos": new_pos,
                            "why": why})
            if new_pos is not None:
                owned.add((iso, norm(new_name)))
        squads[uid] = players

    # free-agent price lookup: best-priced unowned FIFA player per position
    def free_agents(position, exclude):
        cands = []
        for iso, lst in fifa_pool.items():
            for p in lst:
                if p["pos"] != position:
                    continue
                key = (iso, p["norm"])
                if key in owned or key in exclude:
                    continue
                cands.append((p["price"], iso, p["name"], key))
        cands.sort(key=lambda x: -x[0])
        return cands

    def price_of(iso, nn):
        for p in fifa_pool.get(iso, []):
            if p["norm"] == nn:
                return p["price"]
        return 0

    # ----- per-squad rebalance
    rebalances = {}
    picked = set()
    for uid in ROSTER:
        kept = [p for p in squads[uid] if p["new_pos"] is not None]
        dropped_missing = [p for p in squads[uid] if p["new_pos"] is None]
        counts = {k: 0 for k in QUOTA}
        for p in kept:
            counts[p["new_pos"]] += 1
        swaps = {"drop": list(dropped_missing), "add": []}
        # surplus positions: drop lowest-value player there
        cur_players = list(kept)
        # account for missing drops creating deficits too
        def recount():
            c = {k: 0 for k in QUOTA}
            for p in cur_players:
                c[p["new_pos"]] += 1
            return c
        # 1) trim surpluses: drop the LOWEST-FIFA-value player in each surplus pos
        c = recount()
        drop_prices = []
        for pos, need in QUOTA.items():
            while c[pos] > need:
                victims = [p for p in cur_players if p["new_pos"] == pos]
                victims.sort(key=lambda p: price_of(p["iso"], norm(p["new_name"])))
                v = victims[0]
                cur_players.remove(v)
                swaps["drop"].append(v)
                drop_prices.append(price_of(v["iso"], norm(v["new_name"])))
                c = recount()
        # 2) fill deficits with VALUE-MATCHED free agents (closest price to a drop)
        c = recount()
        deficit_slots = []
        for pos, need in QUOTA.items():
            deficit_slots += [pos] * (need - c[pos])
        drop_prices.sort(reverse=True)
        for i, pos in enumerate(deficit_slots):
            target = drop_prices[i] if i < len(drop_prices) else 0
            fa = free_agents(pos, picked)
            if not fa:
                swaps["add"].append({"new_name": "(none available)", "iso": "?",
                                     "new_pos": pos, "price": 0})
                continue
            fa.sort(key=lambda x: abs(x[0] - target))
            price, iso, name, key = fa[0]
            picked.add(key)
            owned.add(key)
            swaps["add"].append({"new_name": name, "iso": iso,
                                 "new_pos": pos, "price": price})
        if swaps["drop"] or swaps["add"]:
            rebalances[uid] = swaps

    # ----- assemble report
    flips = [p for u in ROSTER for p in squads[u] if p["why"] in ("flip", "rename+flip")]
    renames = [p for u in ROSTER for p in squads[u] if p["why"] in ("rename", "rename+flip")]

    out = {
        "pool_changes": {
            "position_flips": rep["totals"]["position_diffs"],
            "renames_to_fifa": fz["summary"]["pairs_found"],
            "players_added": fz["summary"]["fifa_only_truly_missing"],
            "players_dropped": fz["summary"]["db_only_truly_missing"],
        },
        "owned_position_flips": [
            {"uid": u, "player": p["old_name"], "iso": p["iso"],
             "from": p["old_pos"], "to": p["new_pos"]}
            for u in ROSTER for p in squads[u] if p["why"] in ("flip", "rename+flip")],
        "owned_renames": [
            {"uid": u, "from": p["old_name"], "to": p["new_name"], "iso": p["iso"]}
            for u in ROSTER for p in squads[u] if p["why"] in ("rename", "rename+flip")],
        "rebalances": {
            u: {
                "drop": [f'{d["old_name"]} ({d["iso"]} {d.get("new_pos") or d["old_pos"]})'
                         if "old_name" in d else d for d in s["drop"]],
                "add": [f'{a["new_name"]} ({a["iso"]} {a["new_pos"]}, price {a["price"]})'
                        for a in s["add"]],
            } for u, s in rebalances.items()},
    }
    json.dump(out, open(os.path.join(HERE, "_migration_dryrun.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)

    L = []
    L.append("# DB -> FIFA alignment — DRY RUN (no writes)\n")
    pc = out["pool_changes"]
    L.append("## Pool-level changes")
    L.append(f"- Position flips: **{pc['position_flips']}**")
    L.append(f"- Renames to FIFA spelling: **{pc['renames_to_fifa']}**")
    L.append(f"- Players added (FIFA-only): **{pc['players_added']}**")
    L.append(f"- Players dropped (not in FIFA, none owned): **{pc['players_dropped']}**\n")
    L.append("## Squad impact (the part that touches managers' teams)\n")
    for u in ROSTER:
        fl = [p for p in squads[u] if p["why"] in ("flip", "rename+flip")]
        rn = [p for p in squads[u] if p["why"] in ("rename", "rename+flip")]
        rb = rebalances.get(u)
        L.append(f"### {u}")
        if fl:
            L.append("- **Position flips (affect GW1/GW2 points):**")
            for p in fl:
                L.append(f"    - {p['old_name']} ({p['iso']}): {p['old_pos']} → {p['new_pos']}")
        if rn:
            L.append("- **Renames:** " + ", ".join(f"{p['old_name']}→{p['new_name']}" for p in rn))
        if rb:
            L.append(f"- **Rebalance ({len(rb['add'])} swap(s) to restore 2/5/5/3):**")
            for d in rb["drop"]:
                nm = d["old_name"] if isinstance(d, dict) and "old_name" in d else d
                tag = d.get("new_pos") or d.get("old_pos") if isinstance(d, dict) else ""
                L.append(f"    - DROP {nm} ({d['iso']} {tag})" if isinstance(d, dict) else f"    - DROP {d}")
            for a in rb["add"]:
                L.append(f"    - ADD  {a['new_name']} ({a['iso']} {a['new_pos']}, FIFA price {a['price']})")
        if not (fl or rn or rb):
            L.append("- no change")
        L.append("")
    open(os.path.join(HERE, "_migration_dryrun.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    print("pool:", pc)
    print(f"owned position flips: {len(out['owned_position_flips'])}")
    print(f"owned renames: {len(out['owned_renames'])}")
    print(f"squads needing rebalance: {len(rebalances)}")
    for u in ROSTER:
        rb = rebalances.get(u)
        n = len(rb["add"]) if rb else 0
        print(f"  {u}: {n} swap(s)")
    print("\nWrote _migration_dryrun.md / .json")


if __name__ == "__main__":
    main()
