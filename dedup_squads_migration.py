#!/usr/bin/env python3
"""Make every squad in a league pairwise-disjoint.

Background
----------
``populate_production_real_squads.py`` used to fall back to *cloning*
``u_roy``'s squad onto any preserved real user who lacked a saved squad
(see the fixed fallback in that script). The result in ``lg_mock_draft``
was four managers (``u_roy`` and three clones) sharing a near-identical
15-man squad, which made the propose-trade UI show identical players in
both columns and broke trade execution (duplicate ownership).

This migration repairs the data: it walks every squad in priority order
(managers with the fewest shared players first, so the "originals" keep
their picks) and, whenever a player is already claimed by an
earlier-processed manager, swaps it for an unowned player of the SAME
position drawn from the ``wc_players`` catalogue. Position counts
(2 GK / 5 DEF / 5 MID / 3 FWD) are therefore preserved.

It is idempotent: a league whose squads are already disjoint is left
untouched. Lineups are NOT rewritten — ``WCSquadManager.get_lineup``
reconciles them against the squad on read.

Usage
-----
    # dry-run (default) against prod gamedb
    GOOGLE_APPLICATION_CREDENTIALS=<sa.json> \
        .venv/bin/python dedup_squads_migration.py --league lg_mock_draft

    # actually write
    .venv/bin/python dedup_squads_migration.py --league lg_mock_draft --apply

Credentials: either set GOOGLE_APPLICATION_CREDENTIALS, or pass --cred.
"""

import argparse
import os
import sys
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _squad_obj_from_catalogue(p: dict) -> dict:
    """Build a squad-shaped player dict from a wc_players catalogue doc."""
    return {
        "playerId": int(p["id"]),
        "position": int(p["position"]),
        "positionName": p.get("positionName", POS_NAMES.get(int(p["position"]), "")),
        "teamId": p.get("teamId", 0),
        "teamName": p.get("teamName", ""),
        "teamIso": p.get("teamIso", ""),
        "name": p.get("name", ""),
        "eliminated": p.get("eliminated", False),
        "draftedRound": 0,  # post-draft acquisition (migration backfill)
    }


def _load_pool_by_position(db, owned_ids: set) -> dict:
    """Return {pos: [catalogue dicts]} of NON-eliminated players not in
    ``owned_ids``, sorted by draftRank (best first) for determinism."""
    pool = {1: [], 2: [], 3: [], 4: []}
    for doc in db.collection("wc_players").stream():
        p = doc.to_dict()
        pid = int(p.get("id", doc.id))
        if pid in owned_ids:
            continue
        if p.get("eliminated"):
            continue
        pos = int(p.get("position", 0))
        if pos in pool:
            pool[pos].append(p)
    for pos in pool:
        pool[pos].sort(key=lambda x: (x.get("draftRank", 999), int(x["id"])))
    return pool


def dedup_league(db, lid: str, apply: bool = False) -> bool:
    league_ref = db.collection("leagues").document(lid)
    squad_docs = list(league_ref.collection("squads").stream())
    if not squad_docs:
        print(f"  ⚠️  no squads in {lid}")
        return False

    squads = {d.id: (d.to_dict() or {}).get("players", []) for d in squad_docs}

    # How many of each manager's players are shared with ANY other manager?
    global_owner_count = Counter()
    for players in squads.values():
        for p in players:
            global_owner_count[p["playerId"]] += 1
    shared_count = {
        uid: sum(1 for p in players if global_owner_count[p["playerId"]] > 1)
        for uid, players in squads.items()
    }

    # Fewest-shared managers first => "originals" keep their picks; clones
    # get reassigned. Tie-break on uid for determinism.
    order = sorted(squads.keys(), key=lambda u: (shared_count[u], u))

    owned_all = {p["playerId"] for players in squads.values() for p in players}
    pool = _load_pool_by_position(db, owned_all)
    pool_idx = {1: 0, 2: 0, 3: 0, 4: 0}

    def _next_from_pool(pos: int, assigned: set):
        lst = pool[pos]
        while pool_idx[pos] < len(lst):
            cand = lst[pool_idx[pos]]
            pool_idx[pos] += 1
            if int(cand["id"]) not in assigned:
                return cand
        raise RuntimeError(f"pool exhausted for position {POS_NAMES[pos]}")

    assigned: set = set()
    new_squads: dict = {}
    any_change = False

    for uid in order:
        players = squads[uid]
        kept, conflicts = [], Counter()
        for p in players:
            pid = p["playerId"]
            if pid in assigned:
                conflicts[int(p["position"])] += 1
            else:
                assigned.add(pid)
                kept.append(p)
        if not conflicts:
            new_squads[uid] = players
            continue

        any_change = True
        replacements = []
        for pos, n in sorted(conflicts.items()):
            for _ in range(n):
                cand = _next_from_pool(pos, assigned)
                assigned.add(int(cand["id"]))
                replacements.append(_squad_obj_from_catalogue(cand))
        new_players = kept + replacements
        new_squads[uid] = new_players

        old_ids = sorted(p["playerId"] for p in players)
        new_ids = sorted(p["playerId"] for p in new_players)
        dropped = sorted(set(old_ids) - set(new_ids))
        added = sorted(set(new_ids) - set(old_ids))
        print(f"  {uid}: shared={shared_count[uid]:>2}  "
              f"drop {dropped} -> add {added}")

    if not any_change:
        print(f"  ✅ {lid}: squads already disjoint — nothing to do.")
        return False

    # ---- integrity checks before writing ----
    seen = set()
    for uid, players in new_squads.items():
        ids = [p["playerId"] for p in players]
        counts = Counter(int(p["position"]) for p in players)
        assert len(ids) == 15, f"{uid}: {len(ids)} players (expected 15)"
        assert counts == Counter({1: 2, 2: 5, 3: 5, 4: 3}), \
            f"{uid}: bad position counts {dict(counts)}"
        for pid in ids:
            assert pid not in seen, f"player {pid} still shared after dedup!"
            seen.add(pid)
    print(f"  ✔ integrity OK: {len(new_squads)} disjoint 2/5/5/3 squads")

    if not apply:
        print("  (dry-run — pass --apply to write)")
        return True

    for uid, players in new_squads.items():
        if players is not squads.get(uid):  # only write changed docs
            league_ref.collection("squads").document(uid).set(
                {"players": players}, merge=True)
            print(f"  💾 wrote {uid}")
    print(f"  ✅ {lid}: applied.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="lg_mock_draft")
    ap.add_argument("--db", default=os.environ.get("FIRESTORE_DB_ID", "gamedb"))
    ap.add_argument("--cred", default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not firebase_admin._apps:
        if args.cred:
            firebase_admin.initialize_app(credentials.Certificate(args.cred))
        else:
            firebase_admin.initialize_app(options={"projectId": "fpl-analyzer-792eb"})
    db = firestore.client(database_id=args.db)

    print(f"{'APPLY' if args.apply else 'DRY-RUN'} dedup on '{args.league}' (db={args.db})")
    changed = dedup_league(db, args.league, apply=args.apply)
    sys.exit(0 if (args.apply or not changed) else 0)


if __name__ == "__main__":
    main()
