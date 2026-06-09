#!/usr/bin/env python3
"""Tier-1 unit tests for the WC 2026 gw_history snapshot (PR 6).

Pure unit tests — no Firestore emulator, no prod. A lightweight in-memory fake
Firestore (copied from ``test_wc_wishlist.py``) models the docs that
``_snapshot_gw_history`` touches: ``leagues/{lid}/lineups/{uid}_{gw}``,
``leagues/{lid}/scores/{gw}``, ``leagues/{lid}/knockout/bracket``, and the
output ``leagues/{lid}/gw_history/{uid}_{gw}``.

The full ``finalize_gw`` flow is too heavy to drive with the fake DB (it reads
``wc_fixtures``, ``wc_players``, runs auto-subs, knockout seeding, etc.), so we
test the extracted ``_snapshot_gw_history`` helper directly by seeding the
lineups + scores (+ bracket) docs it reads.

Run:
    .venv/bin/python -m pytest test_wc_gw_history.py -v
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_scoring import _snapshot_gw_history  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory fake Firestore (mirrors test_wc_wishlist.py)
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        if self._data is None:
            return None
        d = dict(self._data)
        if "players" in d:
            d["players"] = [dict(p) for p in d["players"]]
        return d


class FakeDocRef:
    def __init__(self, store, key, doc_id):
        self._store = store
        self._key = key
        self._id = doc_id

    @property
    def id(self):
        return self._id

    def get(self, transaction=None):
        data = self._store.get(self._key)
        if data is not None:
            data = dict(data)
            if "players" in data:
                data["players"] = [dict(p) for p in data["players"]]
        return FakeSnapshot(self._id, data)

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)

    def update(self, patch):
        self._store.setdefault(self._key, {}).update(patch)

    def delete(self):
        self._store.pop(self._key, None)

    def collection(self, name):
        return _PathBuilder(self._store, f"{self._key}/{name}")


class FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, field, op, value):
        assert op == "=="
        return FakeQuery([d for d in self._docs if (d.to_dict() or {}).get(field) == value])

    def get(self):
        return list(self._docs)


class FakeCollectionRef:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix
        self._auto = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._auto += 1
            doc_id = f"auto-{self._auto}"
        return FakeDocRef(self._store, f"{self._prefix}/{doc_id}", doc_id)

    def _all_docs(self):
        docs = []
        plen = len(self._prefix) + 1
        for key, data in self._store.items():
            if not key.startswith(self._prefix + "/"):
                continue
            rest = key[plen:]
            if "/" in rest:
                continue
            docs.append(FakeSnapshot(rest, data))
        return docs

    def get(self):
        return self._all_docs()

    def where(self, field, op, value):
        return FakeQuery(self._all_docs()).where(field, op, value)


class _PathBuilder:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def document(self, doc_id=None):
        if doc_id is None:
            raise NotImplementedError
        return FakeDocRef(self._store, f"{self._prefix}/{doc_id}", doc_id)

    def get(self):
        return FakeCollectionRef(self._store, self._prefix).get()

    def where(self, field, op, value):
        return FakeCollectionRef(self._store, self._prefix).where(field, op, value)


class FakeDB:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return _PathBuilder(self._store, name)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

LID = "lg"


@pytest.fixture
def db():
    return FakeDB()


def _league_ref(db):
    return db.collection("leagues").document(LID)


def _seed_lineup(db, uid, gw, starting, bench):
    _league_ref(db).collection("lineups").document(f"{uid}_{gw}").set(
        {"starting": list(starting), "bench": list(bench), "locked": True}
    )


def _seed_scores(db, gw, results, h2h_results=None):
    payload = {"results": results}
    if h2h_results is not None:
        payload["h2hResults"] = h2h_results
    _league_ref(db).collection("scores").document(str(gw)).set(payload)


def _seed_bracket(db, rounds):
    _league_ref(db).collection("knockout").document("bracket").set({"rounds": rounds})


def _read_history(db, uid, gw):
    return (_league_ref(db).collection("gw_history")
            .document(f"{uid}_{gw}").get().to_dict())


# ---------------------------------------------------------------------------
# 1. players array joins fielded IDs -> points; totalPoints from results
# ---------------------------------------------------------------------------

def test_players_join_and_total_points(db):
    gw = 1
    starting = [11, 12, 13]
    bench = [14, 15]
    _seed_lineup(db, "u_a", gw, starting, bench)
    all_player_points = {11: 6, 12: 2, 13: 0, 14: 1, 15: 3, 99: 100}
    results = {"u_a": {"points": 54}}

    _snapshot_gw_history(
        _league_ref(db), gw, ["u_a"], all_player_points, results,
        league_phase_gws=[1, 2, 3], knockout_start_gw=4, db=db,
    )

    hist = _read_history(db, "u_a", gw)
    assert hist["uid"] == "u_a"
    assert hist["gw"] == gw
    # all 15 fielded (here 5) IDs joined, in starting+bench order
    assert hist["players"] == [
        {"id": 11, "points": 6, "stats": {}},
        {"id": 12, "points": 2, "stats": {}},
        {"id": 13, "points": 0, "stats": {}},
        {"id": 14, "points": 1, "stats": {}},
        {"id": 15, "points": 3, "stats": {}},
    ]
    # missing player id defaults to 0; player 99 not on lineup excluded
    assert hist["totalPoints"] == 54


def test_missing_player_points_default_zero(db):
    gw = 1
    _seed_lineup(db, "u_a", gw, [11], [12])
    all_player_points = {11: 5}  # 12 absent
    results = {"u_a": {"points": 5}}

    _snapshot_gw_history(_league_ref(db), gw, ["u_a"], all_player_points,
                         results, [1, 2, 3], 4, db)

    hist = _read_history(db, "u_a", gw)
    assert hist["players"] == [{"id": 11, "points": 5, "stats": {}},
                               {"id": 12, "points": 0, "stats": {}}]


# ---------------------------------------------------------------------------
# 2. league-phase opponent/result/opponentPoints from h2hResults
# ---------------------------------------------------------------------------

def test_league_phase_h2h_resolution(db):
    gw = 2
    _seed_lineup(db, "u_a", gw, [11], [12])
    _seed_lineup(db, "u_b", gw, [21], [22])
    all_pts = {11: 5, 12: 1, 21: 3, 22: 0}
    results = {"u_a": {"points": 6}, "u_b": {"points": 3}}
    h2h = {
        "u_a": {"opponent": "u_b", "result": "W", "pointsFor": 6, "pointsAgainst": 3},
        "u_b": {"opponent": "u_a", "result": "L", "pointsFor": 3, "pointsAgainst": 6},
    }
    _seed_scores(db, gw, results, h2h_results=h2h)

    _snapshot_gw_history(_league_ref(db), gw, ["u_a", "u_b"], all_pts,
                         results, [1, 2, 3], 4, db)

    ha = _read_history(db, "u_a", gw)
    assert ha["opponent"] == "u_b"
    assert ha["result"] == "W"
    assert ha["opponentPoints"] == 3
    hb = _read_history(db, "u_b", gw)
    assert hb["opponent"] == "u_a"
    assert hb["result"] == "L"
    assert hb["opponentPoints"] == 6


# ---------------------------------------------------------------------------
# 3. AAA GW6 case: result kept, opponent/opponentPoints nulled
# ---------------------------------------------------------------------------

def test_aaa_gw6_opponent_nulled(db):
    gw = 6
    _seed_lineup(db, "u_a", gw, [11], [12])
    all_pts = {11: 9, 12: 1}
    results = {"u_a": {"points": 10}}
    h2h = {"u_a": {"result": "AAA", "h2hPoints": 4, "pointsFor": 10}}
    _seed_scores(db, gw, results, h2h_results=h2h)

    _snapshot_gw_history(_league_ref(db), gw, ["u_a"], all_pts,
                         results, [1, 2, 3, 6], 4, db)

    hist = _read_history(db, "u_a", gw)
    assert hist["result"] == "AAA"
    assert hist["opponent"] is None
    assert hist["opponentPoints"] is None


# ---------------------------------------------------------------------------
# 4. knockout-GW opponent/result resolved from bracket match
# ---------------------------------------------------------------------------

def test_knockout_resolution(db):
    gw = 4
    _seed_lineup(db, "u_a", gw, [11], [12])
    _seed_lineup(db, "u_b", gw, [21], [22])
    all_pts = {11: 8, 12: 2, 21: 4, 22: 1}
    results = {"u_a": {"points": 10}, "u_b": {"points": 5}}
    rounds = {
        "qf": [
            {"id": "qf_1v2", "home": "u_a", "away": "u_b",
             "homePoints": 10, "awayPoints": 5, "winner": "u_a", "gw": 4},
        ]
    }
    _seed_bracket(db, rounds)

    _snapshot_gw_history(_league_ref(db), gw, ["u_a", "u_b"], all_pts,
                         results, [1, 2, 3], 4, db)

    ha = _read_history(db, "u_a", gw)
    assert ha["opponent"] == "u_b"
    assert ha["opponentPoints"] == 5
    assert ha["result"] == "W"
    hb = _read_history(db, "u_b", gw)
    assert hb["opponent"] == "u_a"
    assert hb["opponentPoints"] == 10
    assert hb["result"] == "L"


def test_knockout_bye_null_winner(db):
    gw = 5
    _seed_lineup(db, "u_a", gw, [11], [])
    all_pts = {11: 7}
    results = {"u_a": {"points": 7}}
    rounds = {
        "sf": [
            {"id": "sf_bye", "home": "u_a", "away": "u_b",
             "homePoints": 7, "awayPoints": 7, "winner": None, "gw": 5},
        ]
    }
    _seed_bracket(db, rounds)

    _snapshot_gw_history(_league_ref(db), gw, ["u_a"], all_pts,
                         results, [1, 2, 3], 4, db)

    hist = _read_history(db, "u_a", gw)
    assert hist["opponent"] == "u_b"
    assert hist["result"] is None  # None winner -> null result


# ---------------------------------------------------------------------------
# 5. manager with no lineup is skipped
# ---------------------------------------------------------------------------

def test_no_lineup_skipped(db):
    gw = 1
    _seed_lineup(db, "u_a", gw, [11], [12])
    all_pts = {11: 3, 12: 1}
    results = {"u_a": {"points": 4}, "u_b": {"points": 0}}

    _snapshot_gw_history(_league_ref(db), gw, ["u_a", "u_b"], all_pts,
                         results, [1, 2, 3], 4, db)

    assert _read_history(db, "u_a", gw) is not None
    # u_b had no lineup doc -> no gw_history written
    assert _read_history(db, "u_b", gw) is None


# ---------------------------------------------------------------------------
# 6. re-running overwrites cleanly (idempotent)
# ---------------------------------------------------------------------------

def test_idempotent_overwrite(db):
    gw = 1
    _seed_lineup(db, "u_a", gw, [11, 12], [])
    results = {"u_a": {"points": 8}}

    _snapshot_gw_history(_league_ref(db), gw, ["u_a"], {11: 5, 12: 3},
                         results, [1, 2, 3], 4, db)
    first = _read_history(db, "u_a", gw)
    assert first["players"] == [{"id": 11, "points": 5, "stats": {}},
                                {"id": 12, "points": 3, "stats": {}}]

    # Re-finalize with changed lineup + points; full overwrite expected.
    _seed_lineup(db, "u_a", gw, [11], [99])
    results2 = {"u_a": {"points": 9}}
    _snapshot_gw_history(_league_ref(db), gw, ["u_a"], {11: 6, 99: 3},
                         results2, [1, 2, 3], 4, db)
    second = _read_history(db, "u_a", gw)
    assert second["players"] == [{"id": 11, "points": 6, "stats": {}},
                                 {"id": 99, "points": 3, "stats": {}}]
    assert second["totalPoints"] == 9
    # no stale keys / leftover entries
    assert len(second["players"]) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
