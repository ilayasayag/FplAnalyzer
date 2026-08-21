#!/usr/bin/env python3
"""Post-draft: score the 8 squads and find the best free-agent swaps for GW1-3."""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "model.json")))
SQ = json.load(open(os.path.join(HERE, "squads.json")))
XI1 = json.load(open(os.path.join(HERE, "xi_gw1.json")))
PL = M["players"]; BYID = {p["id"]: p for p in PL}
CURVE = M["curve"]; FIX3 = M["fix3"]; FDR6 = M["fdr6"]
POSO = ["GKP", "DEF", "MID", "FWD"]
SHAPE = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
RSLOT = {"GKP": 16, "DEF": 40, "MID": 40, "FWD": 24}
# official lineup rules: play 11, 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD
MINP = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
MAXP = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}
W = {"off": 40, "df": 25, "lof": 20, "adp": 15}
# Plan to the halfway point, not GW38. Halving the scale is cosmetically
# neutral on its own, but it doubles what an absence costs as a share of the
# horizon and doubles the weight of the opening fixtures against season-long
# quality - which is where the ranking actually moves.
HALF = 0.5


def blended(p):
    parts = []
    if p["dr"] < 9999: parts.append((W["off"], p["dr"]))
    if p.get("df") and not p.get("cont"): parts.append((W["df"], p["df"]))
    if p.get("lofr"): parts.append((W["lof"], p["lofr"]))
    if p.get("adp"): parts.append((W["adp"], p["adp"] * 2.2))
    if not parts: return 500.0
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


# rank inside position -> real Draft Fantasy xP curve
order = sorted(PL, key=blended)
XP, k = {}, defaultdict(int)
for p in order:
    k[p["p"]] += 1
    c = CURVE.get(p["p"], [])
    r = k[p["p"]]
    full = c[r - 1] if r <= len(c) else max(35, c[-1] - (r - len(c)) * 1.4)
    XP[p["id"]] = full * HALF
REPL = {pos: CURVE[pos][min(RSLOT[pos], len(CURVE[pos]) - 1)] * HALF for pos in POSO}


def avail_mult(p):
    """How much of a player you actually expect to get over GW1-3."""
    if p["av"] in ("out", "susp"): return 0.05
    if p["av"] == "doubt":
        ch = p["ch"] if p["ch"] is not None else 50
        return 0.25 + ch / 100 * 0.6      # steeper: half the season is 19 games
    return 1.0


# a club has exactly one first-choice keeper: anyone else keeps a clean sheet on the bench
GK1 = {}
for _p in sorted([q for q in PL if q["p"] == "GKP"], key=lambda q: (q["dr"], -(q["mins"] or 0))):
    GK1.setdefault(_p["c"], _p["id"])


def secure(p):
    """Minutes security. Draft rank says how good a player is, not whether he plays.
    Over GW1-3 a rotation option scores nothing however kind the fixtures, and rank
    alone floated Man City bench players over 2,700-minute starters."""
    if p["p"] == "GKP" and GK1.get(p["c"]) != p["id"]:
        return 0.08                      # backup keeper: he does not play, ever
    # Two independent pieces of evidence that a man plays: he played a lot last
    # season, or FPL rates him highly for this one. Take the better of the two -
    # minutes alone punishes anyone who was injured last year but is fit now
    # (Havertz 577, Maddison 34), which is exactly the trap Draft Fantasy fell into.
    mins_conf = min(1.0, (p.get("mins") or 0) / 2000.0)
    dr = p["dr"]
    rank_conf = (1.0 if dr <= 30 else 0.9 if dr <= 60 else 0.8 if dr <= 100
                 else 0.65 if dr <= 160 else 0.45 if dr <= 250 else 0.25)
    longrun = max(mins_conf, rank_conf)
    # Whether he is in his club's projected XI beats both of the above for the
    # games that are actually coming. It is how a Mosquera - starting only because
    # Saliba and Timber are out - gets credited, and how a benched name gets cut.
    starts = 1 if XI1.get(str(p["id"])) else 0
    xi_sig = 1.0 if starts else 0.32
    return max(0.15, min(1.0, 0.55 * xi_sig + 0.45 * longrun))


def starts_gw1(p):
    return 1 if XI1.get(str(p["id"])) else 0


def gw13(p):
    """GW1-3 strength above replacement.

    Scale the PROJECTION by how much of the player you expect to get, then compare
    to replacement - never the other way round. Applying a penalty to an
    already-negative edge makes it smaller, i.e. better, which had the model
    recommending a third-choice keeper (0 minutes) over a 3,040-minute starter."""
    d = FIX3.get(p["c"], [])
    ease = (3.35 - sum(f["d"] for f in d) / len(d)) if d else 0
    effective = (XP[p["id"]] + ease * 22) * avail_mult(p) * secure(p)
    return effective - REPL[p["p"]]


def best_xi(ids):
    """Highest-scoring legal XI for GW1-3."""
    byp = {pos: sorted([BYID[i] for i in ids if BYID[i]["p"] == pos],
                       key=gw13, reverse=True) for pos in POSO}
    best, chosen = None, None
    for nd in range(MINP["DEF"], MAXP["DEF"] + 1):
        for nm in range(MINP["MID"], MAXP["MID"] + 1):
            nf = 11 - 1 - nd - nm
            if not (MINP["FWD"] <= nf <= MAXP["FWD"]): continue
            if nd > len(byp["DEF"]) or nm > len(byp["MID"]) or nf > len(byp["FWD"]): continue
            xi = byp["GKP"][:1] + byp["DEF"][:nd] + byp["MID"][:nm] + byp["FWD"][:nf]
            s = sum(gw13(p) for p in xi)
            if best is None or s > best:
                best, chosen = s, (xi, f"{nd}-{nm}-{nf}")
    return best or 0, chosen


def score(ids):
    sq = [BYID[i] for i in ids]
    xi_s, (xi, form) = best_xi(ids)
    clubs = defaultdict(int)
    for p in sq: clubs[p["c"]] += 1
    flags = [p for p in sq if p["av"] != "ok"]
    depth = {}
    for pos in POSO:
        got = sorted([p for p in sq if p["p"] == pos], key=gw13, reverse=True)
        need_start = MINP[pos] if pos != "GKP" else 1
        depth[pos] = sum(gw13(p) for p in got[:need_start])
    return {
        "xi": round(xi_s, 1), "form": form,
        "total": round(sum(XP[p["id"]] - REPL[p["p"]] for p in sq), 1),
        "risk": round(sum(1 - avail_mult(p) for p in sq) * 100 / 15, 1),
        "fdr": round(sum(FDR6.get(p["c"], 3.35) for p in sq) / 15, 2),
        "maxclub": max(clubs.values()), "clubs": len(clubs),
        "flags": [(p["n"], p["av"], p["ch"]) for p in flags],
        "xi_names": [p["n"] for p in xi], "depth": depth,
    }


def swaps(team, ids, top=6):
    """Best add/drop pairs: same position, must improve the starting XI."""
    owned = set()
    for t, v in SQ.items(): owned.update(v)
    mine = set(ids)
    base, _ = best_xi(ids)
    out = []
    for pos in POSO:
        fa = sorted([p for p in PL if p["p"] == pos and p["id"] not in owned
                     and p["av"] != "gone"], key=gw13, reverse=True)[:14]
        drops = sorted([BYID[i] for i in ids if BYID[i]["p"] == pos], key=gw13)
        for d in drops[:3]:
            for a in fa:
                # Never trade a confirmed starter for someone who is not in his
                # club's XI. Kind fixtures cannot help a man who is not on the
                # pitch, and over a half-season horizon that floor matters more
                # than the ceiling.
                if starts_gw1(d) and not starts_gw1(a) and d["av"] == "ok":
                    continue
                clubs = defaultdict(int)
                for i in ids:
                    if i != d["id"]: clubs[BYID[i]["c"]] += 1
                if clubs[a["c"]] >= 3: continue
                new = [i for i in ids if i != d["id"]] + [a["id"]]
                gain = best_xi(new)[0] - base
                if gain > 0.5:
                    out.append({"pos": pos, "drop": d, "add": a, "gain": round(gain, 1)})
    out.sort(key=lambda x: -x["gain"])
    seen, uniq = set(), []
    for s in out:
        key = (s["drop"]["id"], s["add"]["id"])
        if key in seen: continue
        if any(u["add"]["id"] == s["add"]["id"] for u in uniq): continue
        seen.add(key); uniq.append(s)
        if len(uniq) >= top: break
    return uniq


rows = []
for team, ids in SQ.items():
    s = score(ids); s["team"] = team; rows.append(s)
rows.sort(key=lambda r: -r["xi"])

print("=" * 96)
print("SQUAD RANKING - best legal XI over GW1-3 (fixtures + availability applied)")
print("=" * 96)
print(f"{'#':>2} {'team':22} {'XI':>7} {'form':>6} {'depth':>7} {'risk%':>6} {'fdr':>5} {'clubs':>6}  flags")
for i, r in enumerate(rows, 1):
    fl = ", ".join(f"{n}({a}{'' if c is None else ' '+str(c)+'%'})" for n, a, c in r["flags"]) or "-"
    print(f"{i:2} {r['team'][:22]:22} {r['xi']:7.1f} {r['form']:>6} {r['total']:7.0f} "
          f"{r['risk']:6.1f} {r['fdr']:5.2f} {r['clubs']:6} {fl[:44]}")

print("\n" + "=" * 96)
print("WAIVER TARGETS - best add/drop per team for GW1-3")
print("=" * 96)
for r in rows:
    team = r["team"]
    print(f"\n{team}   (XI {r['xi']:.0f}, {r['form']})")
    for s in swaps(team, SQ[team], 4):
        d, a = s["drop"], s["add"]
        dn = f"{d['n']}({d['c']}{'/'+d['av'] if d['av']!='ok' else ''})"
        an = f"{a['n']}({a['c']})"
        fx = " ".join(f"{f['opp']}{f['ha']}" for f in FIX3.get(a["c"], []))
        xi = "XI" if starts_gw1(a) else "  "
        dxi = "XI" if starts_gw1(d) else "--"
        print(f"   {s['pos']}  drop {dn:24}{dxi} -> add {an:20}{xi} +{s['gain']:5.1f}  "
              f"{a['mins']:>4}min {a['ppg']:.1f}ppg  {fx}")
