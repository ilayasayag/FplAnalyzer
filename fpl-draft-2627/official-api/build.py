#!/usr/bin/env python3
"""
FPL Draft 26/27 - model builder.

Spine is the OFFICIAL draft.premierleague.com API (live injuries, official ids,
FPL's own draft_rank, real fixtures). Three opinion layers are merged on top and
disagreement is flagged rather than resolved.

  python3 fpl_build.py            # fetch live + build
  python3 fpl_build.py --offline  # reuse cached boot.json
"""
import json, os, sys, math, re, unicodedata, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.join(HERE, "boot.json")
API = "https://draft.premierleague.com/api"
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
SHAPE = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}      # official settings.squad


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


# ---------------------------------------------------------------- 1. official
if "--offline" in sys.argv and os.path.exists(BOOT):
    boot = json.load(open(BOOT))
    print("using cached boot.json")
else:
    boot = get(f"{API}/bootstrap-static")
    json.dump(boot, open(BOOT, "w"))
    print("fetched bootstrap-static")

TEAM = {t["id"]: t["short_name"] for t in boot["teams"]}
TEAMNAME = {t["id"]: t["name"] for t in boot["teams"]}
els = boot["elements"]
print(f"official elements: {len(els)}  teams: {len(TEAM)}")

# fixtures -> per-club GW1..6 with a difficulty derived from opponent strength
fixtures = boot["fixtures"]
if isinstance(fixtures, dict):
    flat = []
    for v in fixtures.values():
        if isinstance(v, list):
            flat += v
    fixtures = flat
# opponent strength from last season's total points per club (data-driven, not hand-set)
club_pts = defaultdict(int)
for e in els:
    club_pts[e["team"]] += e.get("total_points") or 0
mx, mn = max(club_pts.values()), min(club_pts.values())
STR = {t: 2.0 + (club_pts[t] - mn) / max(1, mx - mn) * 3.0 for t in TEAM}   # 2.0-5.0

fx = defaultdict(list)
for f in fixtures:
    gw = f.get("event")
    if not gw or gw > 6:
        continue
    h, a = f.get("team_h"), f.get("team_a")
    if not h or not a:
        continue
    fx[h].append({"gw": gw, "opp": TEAM[a], "ha": "H", "d": round(STR[a] - 0.35, 2)})
    fx[a].append({"gw": gw, "opp": TEAM[h], "ha": "A", "d": round(STR[h] + 0.35, 2)})
for t in fx:
    fx[t].sort(key=lambda x: x["gw"])
FDR6 = {TEAM[t]: round(sum(x["d"] for x in v) / len(v), 2) for t, v in fx.items() if v}
FIX3 = {TEAM[t]: [x for x in v if x["gw"] <= 3] for t, v in fx.items()}
print(f"fixtures mapped for {len(FDR6)} clubs (GW1-6)")

# ---------------------------------------------------------------- 2. opinions
def load(fname):
    p = os.path.join(HERE, fname)
    return json.load(open(p)) if os.path.exists(p) else None

# (a) Draft Fantasy 240: [rank, name, club, pos, tier, xP, edge]
DF = defaultdict(list)
src = load("df240.json")
if src:
    for r in src:
        DF[norm(r[1])].append({"rank": r[0], "xp": r[5], "edge": r[6],
                               "tier": r[4], "club": r[2], "pos": r[3]})
print(f"Draft Fantasy rows: {len(DF)}")

# (b) LofLife sheet tiers  {canonical-ish name: tier}
LOF = {norm(k): v for k, v in (load("loflife.json") or {}).items()}
print(f"LofLife tiers: {len(LOF)}")

# (c) our 15-league consensus ADP (8-team scale, snake corrected)
ADP = {norm(k): v for k, v in (load("adp15.json") or {}).items()}
print(f"15-league ADP samples: {len(ADP)}")

# ---------------------------------------------------------------- 3. merge
CLUBFIX = {"NFO": "NFO", "NOT": "NFO", "SPU": "TOT", "TOT": "TOT"}
def match(e, table, need_pos=True):
    """Official element -> opinion row. A surname alone is NOT enough: the
    position must agree (and the club too when the source carries one),
    otherwise Cole Palmer collides with Ipswich's keeper Palmer."""
    pos, club = POS[e["element_type"]], TEAM[e["team"]]
    keys = [norm(e["web_name"]), norm(e["second_name"] or ""),
            norm((e["second_name"] or "").split()[-1] if e["second_name"] else "")]
    for key in keys:
        if not key or key not in table:
            continue
        rows = table[key]
        rows = rows if isinstance(rows, list) else [rows]
        cand = []
        for r in rows:
            if isinstance(r, dict) and r.get("pos"):
                if need_pos and r["pos"] != pos:
                    continue
                rc = CLUBFIX.get(r.get("club", ""), r.get("club", ""))
                if rc and rc != club:
                    continue     # same name, same position, different club
            cand.append(r)
        if cand:
            return cand[0]
    return None

players, contested = [], []
for e in els:
    pos = POS[e["element_type"]]
    club = TEAM[e["team"]]
    df = match(e, DF)
    lof = match(e, LOF, need_pos=False)
    adp = match(e, ADP, need_pos=False)
    dr = e.get("draft_rank") or 9999
    # official availability
    ch = e.get("chance_of_playing_next_round")
    st = e.get("status")
    avail = "ok"
    if st == "u":       avail = "gone"        # left the league
    elif st == "i":     avail = "out"
    elif st == "s":     avail = "susp"
    elif st == "d":     avail = "doubt"
    elif st == "n":     avail = "out"
    players.append({
        "id": e["id"], "n": e["web_name"], "p": pos, "c": club,
        "dr": dr,                                   # FPL official draft rank
        "df": df["rank"] if df else None,           # Draft Fantasy rank
        "xp": df["xp"] if df else None,
        "edge": df["edge"] if df else None,
        "lof": lof if isinstance(lof, int) else None,
        "adp": adp if isinstance(adp, (int, float)) else None,
        "tp": e.get("total_points") or 0,
        "ppg": float(e.get("points_per_game") or 0),
        "dc": e.get("defensive_contribution") or 0,
        "mins": e.get("minutes") or 0,
        "av": avail, "ch": ch,
        "news": (e.get("news") or "")[:110],
    })

# disagreement flag: official draft_rank vs Draft Fantasy rank
for p in players:
    p["cont"] = 0
    # only meaningful if at least one source rates him draftable, otherwise the
    # flat goalkeeper curve floods this with backup keepers nobody will pick
    if (p["df"] and p["dr"] < 9999 and abs(p["df"] - p["dr"]) >= 40
            and p["dr"] <= 200):
        p["cont"] = 1
        contested.append(p)

# EVERY player still in the league goes in the pool. Anyone in your room can draft
# an obscure squad player, and if he is missing here the sync silently drops that
# pick and the board wrongly shows him as available. Ranking hides the deep ones.
pool = [p for p in players if p["av"] != "gone"]
pool.sort(key=lambda p: p["dr"])
print(f"draftable pool: {len(pool)}   contested (|official - DF| >= 40): {len(contested)}")
byp = defaultdict(int)
for p in pool:
    byp[p["p"]] += 1
print("  by position:", dict(byp))

print("\n=== biggest official-vs-DraftFantasy disagreements ===")
for p in sorted(contested, key=lambda p: -abs(p["df"] - p["dr"]))[:12]:
    side = "DF fades" if p["df"] > p["dr"] else "DF likes"
    print(f"  {p['n'][:20]:20} {p['p']} {p['c']:4} official#{p['dr']:<4} DF#{p['df']:<4} "
          f"xP {p['xp'] if p['xp'] else '--':>6}  {side}")

print("\n=== live availability (official, updates continuously) ===")
flag = [p for p in pool if p["av"] != "ok"]
print(f"  {len(flag)} flagged in the draftable pool")
for p in sorted(flag, key=lambda p: p["dr"])[:14]:
    print(f"  {p['n'][:20]:20} {p['c']:4} {p['av']:5} ch={p['ch']}  {p['news'][:58]}")

out = {
    "meta": {
        "built": boot.get("events", {}).get("data", [{}])[0].get("deadline_time", ""),
        "source": "draft.premierleague.com/api/bootstrap-static",
        "squad": SHAPE, "teams_default": 8,
    },
    "clubs": {TEAM[t]: TEAMNAME[t] for t in TEAM},
    "fdr6": FDR6, "fix3": FIX3,
    "players": pool,
}
json.dump(out, open(os.path.join(HERE, "model.json"), "w"), separators=(",", ":"))
print(f"\nwrote model.json  ({os.path.getsize(os.path.join(HERE,'model.json'))} bytes)")
