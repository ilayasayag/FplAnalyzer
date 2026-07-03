#!/usr/bin/env python3
"""Within each national team, try to pair DB-only players with FIFA-only
players that are really the SAME person spelled differently.

Reads _diff_report.json (missing_in_fifa = DB-only, missing_in_db = FIFA-only)
and emits _fuzzy_pairs.json + a console summary.

Matching is conservative-but-thorough:
  proper transliteration (Ø->o, ß->ss, å->a, ñ->n, accents dropped) then
  a pair (db, fifa) is a candidate when ANY of:
    - last token equal AND (first token equal OR first initial equal)
    - one token-set is a subset of the other (handles middle names / short forms)
    - SequenceMatcher ratio on the joined string >= 0.84
    - last token equal AND token-set ratio >= 0.5
  Each FIFA name is assigned to at most one DB name (greedy by best score).
"""
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))

MANUAL = {
    "ø": "o", "œ": "oe", "æ": "ae", "ß": "ss", "đ": "d", "ð": "d",
    "ł": "l", "ı": "i", "þ": "th", "ħ": "h", "ŧ": "t", "ʿ": "", "ʾ": "",
}


def translit(s: str) -> str:
    s = s.lower()
    s = "".join(MANUAL.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", " ").replace(".", " ").replace("-", " ")
    s = re.sub(r"\([^)]*\)", " ", s)   # drop "(Kaku)" etc.
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return [t for t in translit(s).split(" ") if t]


def score(a, b):
    """Higher = more likely same player. 0 = reject."""
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    ratio = SequenceMatcher(None, translit(a), translit(b)).ratio()
    last_eq = ta[-1] == tb[-1]
    first_eq = ta[0] == tb[0]
    first_init = ta[0][:1] == tb[0][:1]
    subset = sa <= sb or sb <= sa
    jacc = len(sa & sb) / len(sa | sb)

    if last_eq and (first_eq or first_init):
        return 0.95 + 0.05 * ratio
    if subset and (sa & sb):
        return 0.90 + 0.05 * ratio
    if ratio >= 0.84:
        return 0.80 + 0.10 * ratio
    if last_eq and jacc >= 0.5:
        return 0.70 + 0.10 * ratio
    # surname-token appears anywhere in the other (compound surnames)
    if (ta[-1] in sb or tb[-1] in sa) and ratio >= 0.6:
        return 0.60 + 0.10 * ratio
    return 0.0


def main():
    with open(os.path.join(HERE, "_diff_report.json"), encoding="utf-8") as f:
        rep = json.load(f)

    db_by_team, fifa_by_team = {}, {}
    for d in rep["missing_in_fifa"]:
        db_by_team.setdefault(d["team"], []).append(d["player"])
    for d in rep["missing_in_db"]:
        fifa_by_team.setdefault(d["team"], []).append(d)

    pairs, db_unpaired, fifa_unpaired = [], [], []
    teams = sorted(set(db_by_team) | set(fifa_by_team))
    for t in teams:
        dbs = list(db_by_team.get(t, []))
        fifas = list(fifa_by_team.get(t, []))
        cands = []
        for dbn in dbs:
            for fp in fifas:
                s = score(dbn, fp["player"])
                if s > 0:
                    cands.append((s, dbn, fp))
        cands.sort(key=lambda x: -x[0])
        used_db, used_fifa = set(), set()
        for s, dbn, fp in cands:
            if dbn in used_db or fp["player"] in used_fifa:
                continue
            used_db.add(dbn)
            used_fifa.add(fp["player"])
            pairs.append({
                "team": t,
                "db_name": dbn,
                "fifa_name": fp["player"],
                "fifa_position": fp.get("fifa_position"),
                "score": round(s, 3),
            })
        for dbn in dbs:
            if dbn not in used_db:
                db_unpaired.append({"team": t, "player": dbn})
        for fp in fifas:
            if fp["player"] not in used_fifa:
                fifa_unpaired.append({"team": t, "player": fp["player"],
                                      "fifa_position": fp.get("fifa_position")})

    out = {
        "summary": {
            "db_only_before": len(rep["missing_in_fifa"]),
            "fifa_only_before": len(rep["missing_in_db"]),
            "pairs_found": len(pairs),
            "db_only_truly_missing": len(db_unpaired),
            "fifa_only_truly_missing": len(fifa_unpaired),
        },
        "pairs": sorted(pairs, key=lambda x: (x["team"], x["db_name"])),
        "db_only_truly_missing": db_unpaired,
        "fifa_only_truly_missing": fifa_unpaired,
    }
    with open(os.path.join(HERE, "_fuzzy_pairs.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    s = out["summary"]
    print("DB-only before  :", s["db_only_before"])
    print("FIFA-only before:", s["fifa_only_before"])
    print("PAIRS FOUND     :", s["pairs_found"])
    print("DB-only truly missing  :", s["db_only_truly_missing"])
    print("FIFA-only truly missing:", s["fifa_only_truly_missing"])
    print("\n--- pairs (low scores first, eyeball these) ---")
    for p in sorted(pairs, key=lambda x: x["score"]):
        flag = "  <-- CHECK" if p["score"] < 0.92 else ""
        print(f'{p["score"]:.2f} {p["team"]}: {p["db_name"]!r} == {p["fifa_name"]!r} ({p["fifa_position"]}){flag}')


if __name__ == "__main__":
    main()
