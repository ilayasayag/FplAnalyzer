#!/usr/bin/env python3
"""Tests for lineup↔squad reconciliation in ``WCSquadManager.get_lineup``.

Transfers (free-agent / trade) only mutate the SQUAD doc; the LINEUP doc is
left pointing at the dropped player and missing the new one. That is why a
transferred-in player never appears in the pick-team view. ``get_lineup`` now
reconciles the stored lineup against the current squad on read (and persists
the fix) so the new player takes the dropped player's slot.

PURE unit tests — a tiny in-memory path-keyed fake Firestore, no emulator.

Run:
    .venv/bin/python -m pytest test_wc_lineup_reconcile.py -q
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game import wc_gameweeks  # noqa: E402
from fpl_predictor.game.wc_squads import WCSquadManager  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal path-keyed fake Firestore (documents + nested collections)
# ---------------------------------------------------------------------------

class _Snap:
    def __init__(self, data):
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
        return _Snap(self.store.get(self.path))

    def set(self, data, merge=False):
        if merge and self.store.get(self.path):
            self.store[self.path] = {**self.store[self.path], **data}
        else:
            self.store[self.path] = dict(data)

    def update(self, data):
        self.store.setdefault(self.path, {}).update(data)


class _Coll:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, doc_id):
        return _Doc(self.store, f"{self.path}/{doc_id}")


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Coll(self.store, name)


LID, UID = "lg", "u1"

# 15-man squad: 2 GK, 5 DEF, 5 MID, 3 FWD (ids 1..15).
_POS = {1: 1, 2: 1,
        3: 2, 4: 2, 5: 2, 6: 2, 7: 2,
        8: 3, 9: 3, 10: 3, 11: 3, 12: 3,
        13: 4, 14: 4, 15: 4}

# A valid 1-4-4-2 lineup over that squad.
_STARTING = [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14]
_BENCH = [2, 7, 12, 15]


def _player(pid, pos):
    return {"playerId": pid, "position": pos, "name": f"P{pid}",
            "teamId": 0, "teamName": "", "teamIso": ""}


@pytest.fixture
def mgr(monkeypatch):
    # Current GW is always treated as open so reconciliation runs.
    monkeypatch.setattr(wc_gameweeks, "is_locked", lambda gw, now=None: False)
    db = FakeDB()
    # squad doc
    db.store[f"leagues/{LID}/squads/{UID}"] = {
        "players": [_player(p, _POS[p]) for p in _POS]
    }
    # lineup doc for GW1
    db.store[f"leagues/{LID}/lineups/{UID}_1"] = {
        "starting": list(_STARTING), "bench": list(_BENCH),
        "formation": [1, 4, 4, 2], "captain": None, "viceCaptain": None,
    }
    # player catalogue (so departed players' positions are resolvable)
    for pid, pos in _POS.items():
        db.store[f"wc_players/{pid}"] = _player(pid, pos)
    return WCSquadManager(db)


def _transfer(mgr, out_id, in_id, in_pos):
    """Simulate what sign_free_agent/trade do: mutate ONLY the squad doc."""
    sref = mgr.db.collection("leagues").document(LID).collection("squads").document(UID)
    players = [p for p in sref.get().to_dict()["players"] if p["playerId"] != out_id]
    players.append(_player(in_id, in_pos))
    sref.set({"players": players}, merge=True)
    mgr.db.store[f"wc_players/{in_id}"] = _player(in_id, in_pos)


def test_no_change_when_lineup_matches_squad(mgr):
    lu = mgr.get_lineup(LID, UID, 1)
    assert sorted(lu["starting"] + lu["bench"]) == sorted(_STARTING + _BENCH)
    assert lu["formation"] == [1, 4, 4, 2]


def test_starting_transfer_replaces_in_place(mgr):
    # Drop starting DEF #3, bring in DEF #16.
    _transfer(mgr, out_id=3, in_id=16, in_pos=2)
    lu = mgr.get_lineup(LID, UID, 1)
    all_ids = lu["starting"] + lu["bench"]
    assert 3 not in all_ids and 16 in all_ids        # swap happened
    assert 16 in lu["starting"]                       # took the starter slot
    assert tuple(lu["formation"]) == (1, 4, 4, 2)     # formation preserved


def test_bench_transfer_replaces_in_place(mgr):
    # Drop bench MID #12, bring in MID #17.
    _transfer(mgr, out_id=12, in_id=17, in_pos=3)
    lu = mgr.get_lineup(LID, UID, 1)
    assert 12 not in lu["starting"] + lu["bench"]
    assert 17 in lu["bench"]


def test_two_transfers_both_appear(mgr):
    # The reported bug: two transfers, neither new player shows.
    _transfer(mgr, out_id=4, in_id=20, in_pos=2)   # DEF→DEF (starter)
    _transfer(mgr, out_id=14, in_id=21, in_pos=4)  # FWD→FWD (starter)
    lu = mgr.get_lineup(LID, UID, 1)
    all_ids = set(lu["starting"] + lu["bench"])
    assert {20, 21} <= all_ids
    assert not ({4, 14} & all_ids)
    assert len(lu["starting"]) == 11
    assert tuple(lu["formation"]) in {(1, 4, 4, 2)}


def test_reconciliation_is_persisted(mgr):
    _transfer(mgr, out_id=3, in_id=16, in_pos=2)
    mgr.get_lineup(LID, UID, 1)  # triggers persist
    stored = mgr.db.store[f"leagues/{LID}/lineups/{UID}_1"]
    assert 16 in stored["starting"] and 3 not in stored["starting"]


def test_locked_gw_not_reconciled(mgr, monkeypatch):
    monkeypatch.setattr(wc_gameweeks, "is_locked", lambda gw, now=None: True)
    _transfer(mgr, out_id=3, in_id=16, in_pos=2)
    lu = mgr.get_lineup(LID, UID, 1)
    # Historical/locked lineup returned verbatim — stale id still present.
    assert 3 in lu["starting"] and 16 not in (lu["starting"] + lu["bench"])
