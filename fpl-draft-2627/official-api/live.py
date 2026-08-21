#!/usr/bin/env python3
"""
Hands-free live draft monitor.

The published artifact cannot make network calls (strict CSP), so this runs on
your machine, polls the official feed, and prints who has gone plus what to take
next. Leave it running in a terminal during the draft.

    python3 fpl_live.py 12345            # your league id, polls every 5s
    python3 fpl_live.py 12345 --seat 3   # you are seat 3 (1-indexed)
    python3 fpl_live.py 12345 --once     # single snapshot, then exit

Find your league id in the URL on draft.premierleague.com, or run with --find
after setting FPL_EMAIL/FPL_PASSWORD (not required for public league feeds).
"""
import json, os, sys, time, argparse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://draft.premierleague.com/api"
POSO = ["GKP", "DEF", "MID", "FWD"]
SHAPE = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
STARTERS = {"GKP": 1, "DEF": 4, "MID": 4, "FWD": 2}
CLUBCAP = 3
XPCAL = {"FWD": (262, 113, 25, .85), "MID": (258, 141, 41, 1.0),
         "DEF": (252, 136, 41, 1.0), "GKP": (162, 130, 17, .35)}
C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[34m",
     "d": "\033[2m", "B": "\033[1m", "x": "\033[0m"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def xp_at(pos, r):
    top, repl, R, a = XPCAL[pos]
    if r > R:
        return max(40, repl - (r - R) * 1.6)
    return repl + (top - repl) * ((r ** -a - R ** -a) / (1 - R ** -a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("league", help="your draft league id")
    ap.add_argument("--seat", type=int, default=0, help="your seat, 1-indexed")
    ap.add_argument("--every", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="debug: only use the first N picks")
    a = ap.parse_args()

    model = json.load(open(os.path.join(HERE, "model.json")))
    PL = model["players"]
    by_id = {p["id"]: p for p in PL}
    FDR = model["fdr6"]

    # static rank -> per-position xP, using the same blend the war room uses
    def blended(p):
        parts = []
        if p["dr"] < 9999: parts.append((40, p["dr"]))
        if p.get("df"):    parts.append((25, p["df"]))
        if p.get("lof"):   parts.append((20, p["lof"] * 18))
        if p.get("adp"):   parts.append((15, p["adp"] * 2.2))
        if not parts: return 400
        return sum(w * v for w, v in parts) / sum(w for w, _ in parts)

    order = sorted(PL, key=blended)
    xp = {}
    k = defaultdict(int)
    for p in order:
        k[p["p"]] += 1
        xp[p["id"]] = xp_at(p["p"], k[p["p"]])

    seen = 0
    while True:
        try:
            feed = get(f"{API}/draft/{a.league}/choices")
        except Exception as e:
            print(f"{C['r']}feed error: {e}{C['x']}")
            time.sleep(a.every); continue
        ch = sorted(feed.get("choices", []), key=lambda c: c.get("index", 0))
        ch = [c for c in ch if c.get("element")]
        if a.limit: ch = ch[:a.limit]
        entries, seats = [], {}
        for c in ch:
            if c["entry"] not in entries: entries.append(c["entry"])
        teams = max(len(entries), 2)
        for c in ch:
            if (c.get("round") == 1) and c["entry"] not in seats:
                seats[c["entry"]] = len(seats)
        for e in entries:
            seats.setdefault(e, len(seats))
        names = {seats[c["entry"]]: c.get("entry_name", "?") for c in ch}

        taken = {c["element"] for c in ch}
        squads = defaultdict(list)
        for c in ch:
            p = by_id.get(c["element"])
            if p: squads[seats[c["entry"]]].append(p)

        if len(ch) != seen or a.once:
            seen = len(ch)
            os.system("clear")
            nxt = len(ch) + 1
            rnd = (nxt - 1) // teams + 1
            idx = (nxt - 1) % teams
            on = idx if rnd % 2 else teams - 1 - idx
            me = a.seat - 1 if a.seat else None
            mine = (me is not None and on == me)
            print(f"{C['B']}FPL DRAFT {a.league}{C['x']}  round {rnd} · pick {nxt} · "
                  f"{teams} teams   " +
                  (f"{C['g']}{C['B']}>>> YOUR PICK <<<{C['x']}" if mine
                   else f"on the clock: {names.get(on,'seat '+str(on+1))}"))
            if ch:
                last = ch[-1]
                lp = by_id.get(last["element"])
                print(f"{C['d']}last: {last.get('entry_name','?')} took "
                      f"{lp['n'] if lp else last.get('player_last_name','?')}"
                      f"{' (auto)' if last.get('was_auto') else ''}{C['x']}")

            if me is not None:
                need = dict(SHAPE)
                cl = defaultdict(int)
                for p in squads[me]:
                    need[p["p"]] -= 1; cl[p["c"]] += 1
                print(f"\n{C['B']}your squad{C['x']} " +
                      " ".join(f"{pos} {SHAPE[pos]-need[pos]}/{SHAPE[pos]}" for pos in POSO))
                for pos in POSO:
                    got = [p["n"] for p in squads[me] if p["p"] == pos]
                    if got: print(f"  {C['d']}{pos}{C['x']} " + ", ".join(got))

                # when is my next pick, and what drains before it
                def seat_at(pn):
                    r = (pn - 1) // teams + 1; i = (pn - 1) % teams
                    return i if r % 2 else teams - 1 - i
                nx = next((p for p in range(nxt + (0 if mine else 1), teams * 15 + 1)
                           if seat_at(p) == me), None)
                gap = (nx - nxt) if nx else 0

                avail = defaultdict(list)
                for p in PL:
                    if p["id"] not in taken and p["av"] != "gone":
                        avail[p["p"]].append(p)
                for pos in POSO:
                    avail[pos].sort(key=lambda p: -xp[p["id"]])
                lg = {pos: sum(max(0, SHAPE[pos] - sum(1 for q in squads[s] if q["p"] == pos))
                               for s in range(teams)) for pos in POSO}
                tot = sum(lg.values()) or 1
                base = {}
                for pos in POSO:
                    L = avail[pos]
                    base[pos] = xp[L[min(lg[pos], len(L) - 1)]["id"]] if L else XPCAL[pos][1]

                left = 15 - len(squads[me])
                cands = []
                for pos in POSO:
                    if need[pos] <= 0: continue
                    for i, p in enumerate(avail[pos][:6]):
                        if cl[p["c"]] >= CLUBCAP: continue
                        e = xp[p["id"]] - base[pos]
                        if (SHAPE[pos] - need[pos]) >= STARTERS[pos]: e *= .22
                        ease = 3.35 - FDR.get(p["c"], 3.35)
                        rk = 45 if p["av"] == "out" else (35 if p["av"] == "susp" else
                             ((100 - (p["ch"] if p["ch"] is not None else 50)) * .35
                              if p["av"] == "doubt" else 0))
                        ph = 2 if rnd >= 13 else (1 if rnd >= 7 else 0)
                        sc = e + ease * [5, 13, 30][ph] - rk * .9
                        if cl[p["c"]] >= 2: sc -= 20 if ph else 9
                        if need[pos] >= left: sc += 250
                        cands.append((sc, e, p, pos))
                cands.sort(key=lambda t: -t[0])

                if nx:
                    print(f"\n{C['B']}priority{C['x']}  next pick {C['B']}{nx}{C['x']} "
                          f"({gap} away)")
                    for pos in POSO:
                        if need[pos] <= 0: continue
                        L = avail[pos]
                        go = max(1, round(gap * lg[pos] / tot))
                        drop = (xp[L[0]["id"]] - xp[L[min(go, len(L) - 1)]["id"]]) if L else 0
                        bar = "█" * min(20, int(drop / 3))
                        print(f"  {pos}  -{drop:5.0f} {C['y']}{bar}{C['x']}")

                print(f"\n{C['B']}take next{C['x']}")
                for sc, e, p, pos in cands[:6]:
                    tags = []
                    if p["av"] == "out":   tags.append(f"{C['r']}OUT{C['x']}")
                    elif p["av"] == "doubt": tags.append(f"{C['y']}{p['ch']}%{C['x']}")
                    if p.get("cont"):      tags.append(f"{C['b']}contested{C['x']}")
                    print(f"  {C['g']}{e:+6.0f}{C['x']} {p['n'][:20]:20} {pos} {p['c']:4} "
                          f"{C['d']}FPL#{p['dr'] if p['dr']<9999 else '--'}"
                          f"{' DF#'+str(p['df']) if p.get('df') else ''}{C['x']} "
                          + " ".join(tags))
            print(f"\n{C['d']}{len(ch)} picks · polling every {a.every}s · ctrl-c to stop{C['x']}")
        if a.once: break
        time.sleep(a.every)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nstopped.")
