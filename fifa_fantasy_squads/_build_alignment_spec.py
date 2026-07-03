#!/usr/bin/env python3
"""Generate fpl_predictor/data/fifa_alignment_spec.json — the deterministic,
reviewable spec the migration endpoint applies. Built from the 48 FIFA squad
files + _fuzzy_pairs.json (which encodes the 95 same-player renames, 10 drops,
246 adds).

Normalisation MUST match the endpoint exactly: NFKD -> ASCII-ignore (drops ø, ß,
accents to nothing, like the browser diff) -> lowercase -> strip '/./- -> collapse.

Spec shape:
{
  "normalize": "nfkd-ascii-ignore-lower-strip",
  "teams":   {ISO: {norm_name: {"name","pos","rank"}}},   # every FIFA player
  "renames": {ISO: {live_norm: fifa_norm}},                # 95 same-player pairs
  "adds":    [{"iso","name","pos","rank"}],                # 246 FIFA-only
  "drops":   [{"iso","name","norm"}]                       # 10 DB-only (drop if unowned)
}
"""
import json
import os
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "fpl_predictor", "data", "fifa_alignment_spec.json")
FIFA_TO_DB = {"BIH": "BOS", "IRN": "IRA", "JPN": "JAP", "MAR": "MOR",
              "KSA": "SAU", "ESP": "SPA", "SUI": "SWI"}
POS_INT = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}


def nrm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace(".", " ").replace("-", " ")
    return " ".join(s.split())


def main():
    # 1) load FIFA pool, build global price rank
    raw = []  # (price, iso, name, pos)
    for fn in os.listdir(HERE):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        data = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
        iso = FIFA_TO_DB.get(data["abbr"], data["abbr"])
        for p in data["players"]:
            raw.append((p.get("price") or 0, iso, p["name"], p["position"]))
    raw.sort(key=lambda x: (-x[0], x[1], x[2]))
    teams = {}
    collisions = set()  # (iso, norm) -- ambiguous; endpoint must KEEP current position
    for i, (price, iso, name, pos) in enumerate(raw, start=1):
        nn = nrm(name)
        bucket = teams.setdefault(iso, {})
        if nn in bucket:
            collisions.add((iso, nn))   # second+ sighting: ambiguous name within team
            continue                    # keep the FIRST (highest-price/best-rank) entry
        bucket[nn] = {"name": name, "pos": POS_INT[pos], "rank": i}

    # 2) renames + drops + adds from fuzzy pairs
    fz = json.load(open(os.path.join(HERE, "_fuzzy_pairs.json"), encoding="utf-8"))
    renames = {}
    missing_targets = []
    for p in fz["pairs"]:
        iso = p["team"]
        live_norm = nrm(p["db_name"])
        fifa_norm = nrm(p["fifa_name"])
        renames.setdefault(iso, {})[live_norm] = fifa_norm
        if fifa_norm not in teams.get(iso, {}):
            missing_targets.append(f'{iso}|{p["db_name"]} -> {p["fifa_name"]} ({fifa_norm})')

    adds = []
    add_unresolved = []
    add_skipped_collision = []
    for d in fz["fifa_only_truly_missing"]:
        iso, name = d["team"], d["player"]
        nn = nrm(name)
        if (iso, nn) in collisions:
            add_skipped_collision.append(f"{iso}|{name}")
            continue
        entry = teams.get(iso, {}).get(nn)
        if not entry:
            add_unresolved.append(f"{iso}|{name}")
            continue
        adds.append({"iso": iso, "name": name, "pos": entry["pos"], "rank": entry["rank"]})

    drops = [{"iso": d["team"], "name": d["player"], "norm": nrm(d["player"])}
             for d in fz["db_only_truly_missing"]]

    spec = {
        "normalize": "nfkd-ascii-ignore-lower-strip",
        "source": "fifa_fantasy_squads + _fuzzy_pairs.json",
        "counts": {"fifa_players": len(raw), "renames": sum(len(v) for v in renames.values()),
                   "adds": len(adds), "drops": len(drops)},
        "teams": teams,
        "renames": renames,
        "adds": adds,
        "drops": drops,
        "collisions": sorted([f"{i}|{n}" for (i, n) in collisions]),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(spec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("FIFA players:", len(raw))
    print("teams:", len(teams))
    print("renames:", spec["counts"]["renames"])
    print("adds:", len(adds), "(unresolved:", len(add_unresolved), ")")
    print("drops:", len(drops))
    print("norm collisions within a team (keep-position):", len(collisions),
          sorted(f"{i}|{n}" for i, n in collisions))
    print("adds skipped due to collision:", add_skipped_collision)
    print("rename targets missing in FIFA pool:", len(missing_targets))
    for m in missing_targets:
        print("  MISSING", m)
    if add_unresolved:
        print("adds unresolved:", add_unresolved)
    print("\nWrote", os.path.relpath(OUT, os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
