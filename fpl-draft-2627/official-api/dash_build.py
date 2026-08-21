#!/usr/bin/env python3
"""Emit the post-draft dashboard data + page."""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "analyse.py")).read().split("rows = []")[0]
ns = {"__file__": os.path.join(HERE, "analyse.py")}
exec(src, ns)
PL, BYID, SQ = ns["PL"], ns["BYID"], ns["SQ"]
XP, REPL, FIX3, FDR6 = ns["XP"], ns["REPL"], ns["FIX3"], ns["FDR6"]
gw13, best_xi, score, swaps, secure, avail_mult = (
    ns["gw13"], ns["best_xi"], ns["score"], ns["swaps"], ns["secure"], ns["avail_mult"])
starts_gw1 = ns["starts_gw1"]
POSO = ns["POSO"]
M = json.load(open(os.path.join(HERE, "model.json")))

owned = {i for v in SQ.values() for i in v}


def slim(p, extra=None):
    d = {"id": p["id"], "n": p["n"], "p": p["p"], "c": p["c"],
         "dr": p["dr"], "df": p.get("df"), "lof": p.get("lof"),
         "mins": p["mins"], "ppg": p["ppg"], "av": p["av"], "ch": p["ch"],
         "news": p["news"], "cont": p.get("cont", 0),
         "xp": round(XP[p["id"]], 1), "g3": round(gw13(p), 1),
         "s1": starts_gw1(p),
         "sec": round(secure(p), 2), "fdr": FDR6.get(p["c"], 3.35)}
    if extra: d.update(extra)
    return d


teams = []
for team, ids in SQ.items():
    s = score(ids)
    xi_ids = {p["id"] for p in best_xi(ids)[1][0]}
    sq = [slim(BYID[i], {"xi": 1 if i in xi_ids else 0}) for i in ids]
    sq.sort(key=lambda x: (POSO.index(x["p"]), -x["g3"]))
    sw = [{"pos": w["pos"], "gain": w["gain"],
           "drop": slim(w["drop"]), "add": slim(w["add"])}
          for w in swaps(team, ids, 8)]
    clubs = defaultdict(int)
    for i in ids: clubs[BYID[i]["c"]] += 1
    teams.append({
        "name": team, "xi": s["xi"], "form": s["form"], "depth": round(s["total"], 0),
        "risk": s["risk"], "fdr": s["fdr"], "clubs": s["clubs"], "maxclub": s["maxclub"],
        "squad": sq, "swaps": sw,
        "byclub": sorted(clubs.items(), key=lambda kv: -kv[1])[:4],
    })
teams.sort(key=lambda t: -t["xi"])

fa = sorted([p for p in PL if p["id"] not in owned and p["av"] != "gone"],
            key=gw13, reverse=True)
fa_slim = [slim(p) for p in fa[:160]]

# normalise the headline scores across the eight squads
def nrm(vals):
    lo, hi = min(vals), max(vals)
    return [50 if hi - lo < 1e-9 else round((v - lo) / (hi - lo) * 100) for v in vals]

xis = nrm([t["xi"] for t in teams])
dep = nrm([t["depth"] for t in teams])
rsk = nrm([t["risk"] for t in teams])
fdr = nrm([-t["fdr"] for t in teams])
bal = []
for t in teams:
    per = defaultdict(list)
    for p in t["squad"]: per[p["p"]].append(p["g3"])
    strengths = [sum(sorted(v, reverse=True)[:{"GKP":1,"DEF":3,"MID":2,"FWD":1}[k]])
                 for k, v in per.items()]
    spread = max(strengths) - min(strengths)
    bal.append(-spread)
bal = nrm(bal)
for i, t in enumerate(teams):
    t["s_xi"], t["s_depth"], t["s_risk"] = xis[i], dep[i], rsk[i]
    t["s_fdr"], t["s_bal"] = fdr[i], bal[i]
    t["s_total"] = round(t["s_xi"] * .40 + t["s_depth"] * .20 + t["s_bal"] * .15
                         + t["s_fdr"] * .15 + (100 - t["s_risk"]) * .10)

data = {"teams": teams, "fa": fa_slim, "clubs": M["clubs"], "fix3": FIX3,
        "counts": {"fa": len(fa), "pool": len(PL)}}
json.dump(data, open(os.path.join(HERE, "dash.json"), "w"), separators=(",", ":"))
print(f"teams {len(teams)} | free agents {len(fa)} (top {len(fa_slim)} shipped)")
print(f"{'team':22}{'XI':>7}{'form':>7}{'total':>7}  top club block")
for t in teams:
    print(f"{t['name'][:22]:22}{t['xi']:7.0f}{t['form']:>7}{t['s_total']:7}  "
          f"{', '.join(f'{c}x{n}' for c, n in t['byclub'][:3])}")
