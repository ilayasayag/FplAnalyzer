#!/usr/bin/env python3
"""Tier-1 unit tests for the WC 2026 transfer system (PR 3: atomic trades).

These are PURE unit tests — no Firestore emulator and no prod access. They
exercise ``WCTradeManager._execute_trade`` directly against a lightweight
in-memory fake Firestore that honours the real ``@firestore.transactional``
contract (reads via ``snapshot.get(transaction=txn)``, writes via
``txn.update(ref, ...)`` applied only on commit).

Run:
    .venv/bin/python -m pytest test_wc_transfers.py -v

Acceptance criteria covered (WC2026_WINDOWS_DESIGN.md §13, PR 3):
  * a successful 1-for-1 trade swaps the correct player OBJECTS between squads;
  * position integrity is preserved (a GK-for-GK same-position swap keeps
    per-position counts unchanged);
  * the swap is ATOMIC — if one side is invalid (no longer owns the player it
    is giving), NEITHER squad is mutated;
  * data-model fidelity (§12): squads store full player objects with INT
    ``position`` codes, and the swapped objects carry their metadata.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_trades import WCTradeManager, _pos_counts  # noqa: E402


# ---------------------------------------------------------------------------
# Lightweight in-memory fake Firestore (transaction-aware)
# ---------------------------------------------------------------------------
#
# We model only what _execute_trade touches: leagues/{lid}/squads/{uid} docs
# and a leagues/{lid}/transactions collection (write-only audit log). The fake
# supports the real transactional protocol: the @firestore.transactional
# decorator threads a transaction object through; reads buffer nothing, and
# txn.update(...) is staged and applied atomically when the decorated function
# returns without raising. If it raises, staged writes are discarded.


class FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        # mimic Firestore: a copy so callers can't mutate stored state directly
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self, transaction=None):
        data = self._store.get(self._key)
        # deep-ish copy of the players list so mutation requires an explicit set
        if data is not None:
            data = {**data, "players": [dict(p) for p in data.get("players", [])]}
        return FakeSnapshot(data)

    def set(self, data):
        self._store[self._key] = data

    def update(self, patch):
        existing = self._store.setdefault(self._key, {})
        existing.update(patch)


class FakeCollectionRef:
    """Supports .document(id) and .document() (auto-id) for the audit log."""

    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix
        self._auto = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._auto += 1
            doc_id = f"auto-{self._auto}"
        return FakeDocRef(self._store, f"{self._prefix}/{doc_id}")


class FakeTransaction:
    def __init__(self, store):
        self._store = store
        self._writes = []

    # The real transactional decorator calls these lifecycle hooks.
    def _begin(self):
        self._writes = []

    def update(self, ref, patch):
        self._writes.append((ref, dict(patch)))

    def _commit(self):
        for ref, patch in self._writes:
            ref.update(patch)
        self._writes = []

    def _rollback(self):
        self._writes = []


class FakeDB:
    """Minimal Firestore surface: collection(...).document(...).collection(...)."""

    def __init__(self):
        # flat key/value store: "leagues/{lid}/squads/{uid}" -> doc dict
        self._store = {}

    # leagues -> squads / transactions live under path prefixes
    def collection(self, name):
        return _PathBuilder(self._store, name)

    def transaction(self):
        return FakeTransaction(self._store)


class _PathBuilder:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def document(self, doc_id=None):
        if doc_id is None:
            # only used for transactions audit doc; delegate via collection
            raise NotImplementedError
        return _DocPathBuilder(self._store, f"{self._prefix}/{doc_id}")


class _DocPathBuilder(FakeDocRef):
    def collection(self, name):
        return FakeCollectionRef(self._store, f"{self._key}/{name}")


# Patch the real @firestore.transactional usage: in production it wraps the
# inner function and drives txn lifecycle. We replicate that here so the SAME
# production code path runs against the fake.
import google.cloud.firestore_v1 as _fs  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_transactional(monkeypatch):
    def fake_transactional(fn):
        def wrapper(txn, *args, **kwargs):
            txn._begin()
            try:
                result = fn(txn, *args, **kwargs)
            except Exception:
                txn._rollback()
                raise
            txn._commit()
            return result
        return wrapper

    monkeypatch.setattr(_fs, "transactional", fake_transactional)
    # _execute_trade imports `transactional` locally from this module, so the
    # monkeypatch above (on the module attr) is what the local import resolves.
    yield


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _player(pid, pos, name, team=1):
    return {
        "playerId": pid,
        "position": pos,
        "positionName": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[pos],
        "name": name,
        "teamId": team,
        "eliminated": False,
    }


def _seed_squad(db, lid, uid, players):
    db.collection("leagues").document(lid).collection("squads").document(uid).set(
        {"players": [dict(p) for p in players]}
    )


def _get_players(db, lid, uid):
    snap = (db.collection("leagues").document(lid)
            .collection("squads").document(uid).get())
    return snap.to_dict()["players"]


def _trade(prop_uid, tgt_uid, prop_players, tgt_players):
    """Build a trade doc shaped like propose_trade writes."""
    return {
        "proposerUid": prop_uid,
        "targetUid": tgt_uid,
        "proposerPlayers": [
            {"playerId": p["playerId"], "position": p["position"],
             "positionName": p["positionName"], "name": p["name"],
             "teamId": p["teamId"]}
            for p in prop_players
        ],
        "targetPlayers": [
            {"playerId": p["playerId"], "position": p["position"],
             "positionName": p["positionName"], "name": p["name"],
             "teamId": p["teamId"]}
            for p in tgt_players
        ],
    }


# A standard pair of squads. Alice (proposer), Bob (target).
ALICE = [
    _player(1, 1, "Alice GK"),
    _player(2, 2, "Alice DEF"),
    _player(3, 3, "Alice MID"),
    _player(4, 4, "Alice FWD"),
]
BOB = [
    _player(11, 1, "Bob GK"),
    _player(12, 2, "Bob DEF"),
    _player(13, 3, "Bob MID"),
    _player(14, 4, "Bob FWD"),
]


@pytest.fixture
def db():
    d = FakeDB()
    _seed_squad(d, "lg1", "alice", ALICE)
    _seed_squad(d, "lg1", "bob", BOB)
    return d


@pytest.fixture
def mgr(db):
    return WCTradeManager(db)


# ---------------------------------------------------------------------------
# 1. Successful 1-for-1 trade swaps the correct player OBJECTS
# ---------------------------------------------------------------------------

def test_one_for_one_swaps_player_objects(mgr, db):
    # Alice gives her MID (id 3), Bob gives his MID (id 13).
    trade = _trade("alice", "bob",
                   [ALICE[2]],   # Alice MID id=3
                   [BOB[2]])     # Bob MID id=13
    mgr._execute_trade("lg1", trade)

    alice_ids = {p["playerId"] for p in _get_players(db, "lg1", "alice")}
    bob_ids = {p["playerId"] for p in _get_players(db, "lg1", "bob")}

    # id 3 left Alice, id 13 arrived; mirror for Bob.
    assert 3 not in alice_ids and 13 in alice_ids
    assert 13 not in bob_ids and 3 in bob_ids
    # Untouched players stay put.
    assert {1, 2, 4} <= alice_ids
    assert {11, 12, 14} <= bob_ids

    # The OBJECT moved with its metadata intact (name carried across).
    moved = next(p for p in _get_players(db, "lg1", "alice") if p["playerId"] == 13)
    assert moved["name"] == "Bob MID"
    assert moved["positionName"] == "MID"


def test_one_for_one_writes_audit_transaction(mgr, db):
    trade = _trade("alice", "bob", [ALICE[2]], [BOB[2]])
    mgr._execute_trade("lg1", trade)
    # transactions audit doc written under the league
    txn_doc = db._store.get("leagues/lg1/transactions/auto-1")
    assert txn_doc is not None
    assert txn_doc["type"] == "trade_accepted"
    assert txn_doc["proposerUid"] == "alice"
    assert txn_doc["targetUid"] == "bob"
    # gw is stamped (None when the league doc has no currentGw) so the per-GW
    # transfer history can group the trade with that window's wishlist auction.
    assert "gw" in txn_doc


def test_audit_transaction_stamps_current_gw(mgr, db):
    db.collection("leagues").document("lg1").set({"currentGw": 4})
    trade = _trade("alice", "bob", [ALICE[2]], [BOB[2]])
    mgr._execute_trade("lg1", trade)
    txn_doc = db._store.get("leagues/lg1/transactions/auto-1")
    assert txn_doc["gw"] == 4


def test_squad_sizes_preserved(mgr, db):
    trade = _trade("alice", "bob", [ALICE[1]], [BOB[1]])  # DEF for DEF
    mgr._execute_trade("lg1", trade)
    assert len(_get_players(db, "lg1", "alice")) == 4
    assert len(_get_players(db, "lg1", "bob")) == 4


# ---------------------------------------------------------------------------
# 2. Position integrity preserved (same-position swap keeps quotas valid)
# ---------------------------------------------------------------------------

def test_gk_for_gk_keeps_position_counts(mgr, db):
    before_alice = _pos_counts(_get_players(db, "lg1", "alice"))
    before_bob = _pos_counts(_get_players(db, "lg1", "bob"))

    trade = _trade("alice", "bob", [ALICE[0]], [BOB[0]])  # GK (pos 1) for GK
    mgr._execute_trade("lg1", trade)

    assert _pos_counts(_get_players(db, "lg1", "alice")) == before_alice
    assert _pos_counts(_get_players(db, "lg1", "bob")) == before_bob


def test_multi_player_balanced_swap_keeps_counts(mgr, db):
    # 2-for-2: DEF+MID for DEF+MID (balanced, different ids).
    trade = _trade("alice", "bob",
                   [ALICE[1], ALICE[2]],   # DEF id2, MID id3
                   [BOB[1], BOB[2]])       # DEF id12, MID id13
    before_alice = _pos_counts(_get_players(db, "lg1", "alice"))
    mgr._execute_trade("lg1", trade)
    assert _pos_counts(_get_players(db, "lg1", "alice")) == before_alice
    alice_ids = {p["playerId"] for p in _get_players(db, "lg1", "alice")}
    assert {1, 4, 12, 13} == alice_ids


# ---------------------------------------------------------------------------
# 3. Atomicity — invalid side leaves BOTH squads untouched
# ---------------------------------------------------------------------------

def test_proposer_no_longer_owns_player_aborts_both(mgr, db):
    # Build a trade for a player Alice does NOT own (id 999).
    phantom = _player(999, 3, "Phantom MID")
    trade = _trade("alice", "bob", [phantom], [BOB[2]])

    before_alice = _get_players(db, "lg1", "alice")
    before_bob = _get_players(db, "lg1", "bob")

    with pytest.raises(ValueError, match="PROPOSER_PLAYERS_NOT_OWNED"):
        mgr._execute_trade("lg1", trade)

    # Neither squad mutated.
    assert _get_players(db, "lg1", "alice") == before_alice
    assert _get_players(db, "lg1", "bob") == before_bob
    # No audit transaction written.
    assert db._store.get("leagues/lg1/transactions/auto-1") is None


def test_target_no_longer_owns_player_aborts_both(mgr, db):
    phantom = _player(888, 3, "Phantom MID")
    trade = _trade("alice", "bob", [ALICE[2]], [phantom])

    before_alice = _get_players(db, "lg1", "alice")
    before_bob = _get_players(db, "lg1", "bob")

    with pytest.raises(ValueError, match="TARGET_PLAYERS_NOT_OWNED"):
        mgr._execute_trade("lg1", trade)

    assert _get_players(db, "lg1", "alice") == before_alice
    assert _get_players(db, "lg1", "bob") == before_bob


def test_missing_target_squad_aborts(mgr, db):
    trade = _trade("alice", "nobody", [ALICE[2]], [BOB[2]])
    before_alice = _get_players(db, "lg1", "alice")
    with pytest.raises(ValueError, match="No squad found"):
        mgr._execute_trade("lg1", trade)
    # Proposer untouched.
    assert _get_players(db, "lg1", "alice") == before_alice


# ---------------------------------------------------------------------------
# 4. Data-model fidelity (§12): INT position codes on objects
# ---------------------------------------------------------------------------

def test_positions_are_int_codes_after_swap(mgr, db):
    trade = _trade("alice", "bob", [ALICE[3]], [BOB[3]])  # FWD (pos 4) for FWD
    mgr._execute_trade("lg1", trade)
    for p in _get_players(db, "lg1", "alice") + _get_players(db, "lg1", "bob"):
        assert isinstance(p["position"], int)
        assert p["position"] in (1, 2, 3, 4)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
