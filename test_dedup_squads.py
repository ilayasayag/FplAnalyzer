#!/usr/bin/env python3
"""Tests for ``dedup_squads_migration.dedup_league``.

The mock-draft seed used to clone one manager's squad onto every preserved
real user, leaving several managers sharing an identical 15-man squad. This
migration walks every squad (fewest-shared first, so the originals keep their
picks) and swaps each already-claimed player for an unowned, same-position
player so the squads become pairwise-disjoint while staying 2/5/5/3.

PURE unit tests — a tiny in-memory path-keyed fake Firestore with .stream(),
no emulator.

Run:
    .venv/bin/python -m pytest test_dedup_squads.py -q
"""

import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import dedup_squads_migration as mig  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal path-keyed fake Firestore with .stream() on collections
# ---------------------------------------------------------------------------

class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, name):
        return _Coll(self.store, f"{self.path}/{name}")

    def get(self):
        return _Snap(self.path.rsplit("/", 1)[-1], self.store.get(self.path))

    def set(self, data, merge=False):
        if merge and self.store.get(self.path):
            self.store[self.path] = {**self.store[self.path], **data}
        else:
            self.store[self.path] = dict(data)


class _Coll:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, doc_id):
        return _Doc(self.store, f"{self.path}/{doc_id}")

    def stream(self):
        # Direct children only (one path segment past this collection).
        depth = self.path.count("/") + 1
        for key, data in list(self.store.items()):
            if key.startswith(self.path + "/") and key.count("/") == depth:
                yield _Snap(key.rsplit("/", 1)[-1], data)

    # the migration only ever calls .stream(); .get() unused here


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Coll(self.store, name)


LID = "lg_test"
_POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _squad_player(pid, pos):
    return {"playerId": pid, "position": pos, "positionName": _POS_NAME[pos],
            "name": f"P{pid}", "teamId": 0, "teamName": "", "teamIso": "",
            "eliminated": False}


def _make_db(squads):
    """squads: {uid: [(pid,pos), ...]}. Also seeds a big disjoint catalogue."""
    db = FakeDB()
    for uid, picks in squads.items():
        db.store[f"leagues/{LID}/squads/{uid}"] = {
            "players": [_squad_player(pid, pos) for pid, pos in picks]
        }
    # Catalogue: ids 1000..1000+N per position, all unowned/non-eliminated.
    # 60 per position is plenty for refills.
    pid = 1000
    for pos in (1, 2, 3, 4):
        for _ in range(80):
            db.store[f"wc_players/{pid}"] = {
                "id": pid, "position": pos, "positionName": _POS_NAME[pos],
                "name": f"Pool{pid}", "teamId": 0, "teamName": "", "teamIso": "",
                "draftRank": 999, "eliminated": False,
            }
            pid += 1
    return db


def _valid_squad(players):
    counts = Counter(p["position"] for p in players)
    return len(players) == 15 and counts == Counter({1: 2, 2: 5, 3: 5, 4: 3})


# A valid 2/5/5/3 squad template over a given id offset.
def _squad(base):
    picks = []
    picks += [(base + 0, 1), (base + 1, 1)]
    picks += [(base + 2 + i, 2) for i in range(5)]
    picks += [(base + 7 + i, 3) for i in range(5)]
    picks += [(base + 12 + i, 4) for i in range(3)]
    return picks


def _all_ids(db, uid):
    return sorted(p["playerId"] for p in
                  db.store[f"leagues/{LID}/squads/{uid}"]["players"])


def test_disjoint_squads_untouched():
    a, b = _squad(0), _squad(100)
    db = _make_db({"u_a": a, "u_b": b})
    changed = mig.dedup_league(db, LID, apply=True)
    assert changed is False
    assert _all_ids(db, "u_a") == sorted(p for p, _ in a)
    assert _all_ids(db, "u_b") == sorted(p for p, _ in b)


def test_identical_clones_become_disjoint():
    sq = _squad(0)
    db = _make_db({"u_orig": list(sq), "u_clone": list(sq)})
    changed = mig.dedup_league(db, LID, apply=True)
    assert changed is True
    orig = db.store[f"leagues/{LID}/squads/u_orig"]["players"]
    clone = db.store[f"leagues/{LID}/squads/u_clone"]["players"]
    assert _valid_squad(orig) and _valid_squad(clone)
    # Pairwise disjoint now.
    assert not (set(p["playerId"] for p in orig) & set(p["playerId"] for p in clone))
    # One of them keeps the original picks intact (fewest-shared / tie-break).
    keep = sorted(p for p, _ in sq)
    assert _all_ids(db, "u_orig") == keep or _all_ids(db, "u_clone") == keep


def test_unique_players_are_preserved():
    # Two managers share 13 players but each has 2 unique; the unique ones
    # must survive for whichever manager gets reassigned.
    shared = _squad(0)
    # u_y replaces its 2 GK ids (0,1) with unique 900,901 (still GKs).
    y = [(900, 1), (901, 1)] + shared[2:]
    db = _make_db({"u_x": list(shared), "u_y": list(y)})
    mig.dedup_league(db, LID, apply=True)
    x_ids = set(_all_ids(db, "u_x"))
    y_ids = set(_all_ids(db, "u_y"))
    assert not (x_ids & y_ids)              # disjoint
    # u_y has fewer shared (13 vs 15) -> processed first -> keeps everything.
    assert {900, 901} <= y_ids
    assert _valid_squad(db.store[f"leagues/{LID}/squads/u_x"]["players"])
    assert _valid_squad(db.store[f"leagues/{LID}/squads/u_y"]["players"])


def test_idempotent():
    sq = _squad(0)
    db = _make_db({"u_a": list(sq), "u_b": list(sq)})
    mig.dedup_league(db, LID, apply=True)
    # Second run is a no-op.
    assert mig.dedup_league(db, LID, apply=True) is False


def test_dry_run_does_not_write():
    sq = _squad(0)
    db = _make_db({"u_a": list(sq), "u_b": list(sq)})
    before_a = _all_ids(db, "u_a")
    before_b = _all_ids(db, "u_b")
    changed = mig.dedup_league(db, LID, apply=False)
    assert changed is True                  # detected work to do
    assert _all_ids(db, "u_a") == before_a  # but wrote nothing
    assert _all_ids(db, "u_b") == before_b
