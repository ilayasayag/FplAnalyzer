#!/usr/bin/env python3
"""Tier-1 unit tests for WC 2026 deferred next-GW trades (PR 5).

Pure unit tests — no Firestore emulator, no prod. Reuses the same in-memory
fake-Firestore harness pattern as ``test_wc_wishlist.py`` (transaction-aware,
collection ``.get()`` iteration, ``.where("f","==",v)`` filtering, ``db.batch()``
deletes) and extends it only with what PR 5 touches: a ``leagues/{lid}`` league
doc (so ``wc_windows.current_window_from_db`` can read ``windowOverride``) and a
``leagues/{lid}/trades`` collection.

The NEXT_GW_BID window is forced deterministically via the league's
``windowOverride`` field (see wc_windows.current_window) so the tests need no
fixture clock.

Run:
    .venv/bin/python -m pytest test_wc_deferred_trades.py -v

Acceptance (WC2026_WINDOWS_DESIGN.md §6, PR 5):
  * a trade approved during NEXT_GW_BID becomes ``deferred_pending`` (squads
    unchanged, no swap yet);
  * ``process_deferred_trades`` executes a still-valid deferred trade
    atomically (squads swapped, status → accepted, audit txn written);
  * a deferred trade that became invalid is ``cancelled`` with a cancelReason
    and both squads are left untouched;
  * the orchestrator runs deferred trades BEFORE the auction (observable
    ordering) and returns the combined summary shape;
  * a deferred trade can still be cancelled by the proposer before execution.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_trades import WCTradeManager  # noqa: E402
from fpl_predictor.game.wc_wishlist import WCWishlistManager  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory fake Firestore (same contract as test_wc_wishlist.py)
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, doc_id, data, ref=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = ref

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
        return FakeSnapshot(self._id, data, ref=self)

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
        return FakeCollectionRef(self._store, f"{self._key}/{name}")


class FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, field, op, value):
        assert op in ("==", "in")
        if op == "in":
            keep = lambda v: v in value
        else:
            keep = lambda v: v == value
        return FakeQuery(
            [d for d in self._docs if keep((d.to_dict() or {}).get(field))]
        )

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
            if "/" in rest:  # only direct children
                continue
            docs.append(FakeSnapshot(
                rest, data, ref=FakeDocRef(self._store, key, rest)
            ))
        return docs

    def get(self):
        return self._all_docs()

    def where(self, field, op, value):
        return FakeQuery(self._all_docs()).where(field, op, value)


class FakeTransaction:
    def __init__(self, store):
        self._store = store
        self._writes = []

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


class FakeBatch:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def delete(self, ref):
        self._ops.append(ref)

    def commit(self):
        for ref in self._ops:
            ref.delete()
        self._ops = []


class _DocPathBuilder(FakeDocRef):
    def collection(self, name):
        return FakeCollectionRef(self._store, f"{self._key}/{name}")


class _PathBuilder:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def document(self, doc_id=None):
        if doc_id is None:
            raise NotImplementedError
        return _DocPathBuilder(self._store, f"{self._prefix}/{doc_id}", doc_id)

    def get(self):
        return FakeCollectionRef(self._store, self._prefix).get()

    def where(self, field, op, value):
        return FakeCollectionRef(self._store, self._prefix).where(field, op, value)


class FakeDB:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return _PathBuilder(self._store, name)

    def transaction(self):
        return FakeTransaction(self._store)

    def batch(self):
        return FakeBatch(self._store)


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
    yield


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _player(pid, pos, name="P", team=1):
    return {
        "playerId": pid,
        "position": pos,
        "positionName": POS[pos],
        "name": name,
        "teamId": team,
        "eliminated": False,
    }


def _seed_league(db, lid, *, window="next_gw_bid", gw=4, current_gw=4):
    """League doc whose windowOverride forces a transfer-window phase.

    ``current_window`` short-circuits on a valid ``windowOverride.phase`` so the
    tests don't need a fixture clock. ``window=None`` clears the override (the
    fixture-clock path returns NONE with no fixtures seeded → execute now).
    """
    doc = {
        "status": "group_phase",
        "tradeApproval": "instant",
        "adminUid": "admin",
        "currentGw": current_gw,
    }
    if window is not None:
        doc["windowOverride"] = {"phase": window, "gw": gw}
    db.collection("leagues").document(lid).set(doc)


def _seed_member(db, lid, uid, waiver_priority=1, draft_position=1):
    db.collection("leagues").document(lid).collection("members").document(uid).set({
        "displayName": uid,
        "waiverPriority": waiver_priority,
        "draftPosition": draft_position,
    })


def _seed_squad(db, lid, uid, players):
    db.collection("leagues").document(lid).collection("squads").document(uid).set(
        {"players": [dict(p) for p in players]}
    )


def _seed_wc_player(db, p):
    db.collection("wc_players").document(str(p["playerId"])).set({
        "id": p["playerId"],
        "position": p["position"],
        "positionName": p["positionName"],
        "name": p["name"],
        "teamId": p.get("teamId", 1),
        "eliminated": p.get("eliminated", False),
    })


def _seed_bid_doc(db, lid, uid, gw, bids):
    db.collection("leagues").document(lid).collection("wishlist_bids").document(
        f"{uid}_{gw}"
    ).set({"uid": uid, "gw": gw, "bids": bids})


def _seed_trade(db, lid, trade_id, trade):
    db.collection("leagues").document(lid).collection("trades").document(
        trade_id
    ).set(trade)


def _squad_ids(db, lid, uid):
    snap = (db.collection("leagues").document(lid)
            .collection("squads").document(uid).get())
    return {p["playerId"] for p in snap.to_dict()["players"]}


def _get_players(db, lid, uid):
    snap = (db.collection("leagues").document(lid)
            .collection("squads").document(uid).get())
    return snap.to_dict()["players"]


def _trade_doc(db, lid, trade_id):
    return (db.collection("leagues").document(lid)
            .collection("trades").document(trade_id).get()).to_dict()


def _legal_squad(base_id):
    """Quota-legal 15-man squad (2/5/5/3) with deterministic ids."""
    players = []
    for i in range(2):
        players.append(_player(base_id + i, 1, f"GK{i}"))
    for i in range(5):
        players.append(_player(base_id + 2 + i, 2, f"DEF{i}"))
    for i in range(5):
        players.append(_player(base_id + 7 + i, 3, f"MID{i}"))
    for i in range(3):
        players.append(_player(base_id + 12 + i, 4, f"FWD{i}"))
    return players


# Player payload as stored on a trade doc (proposerPlayers/targetPlayers).
def _trade_player(p):
    return {
        "playerId": p["playerId"],
        "position": p["position"],
        "positionName": p["positionName"],
        "name": p["name"],
        "teamId": p["teamId"],
    }


def _make_trade(prop_uid, tgt_uid, prop_players, tgt_players, **extra):
    doc = {
        "proposerUid": prop_uid,
        "targetUid": tgt_uid,
        "proposerPlayers": [_trade_player(p) for p in prop_players],
        "targetPlayers": [_trade_player(p) for p in tgt_players],
        "status": "deferred_pending",
        "vetoVotes": [],
        "approveVotes": [],
    }
    doc.update(extra)
    return doc


# Standard pair of small squads. Alice (proposer), Bob (target).
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
    return FakeDB()


@pytest.fixture
def mgr(db):
    return WCTradeManager(db)


@pytest.fixture
def wmgr(db):
    return WCWishlistManager(db)


# ---------------------------------------------------------------------------
# 1. A trade approved during NEXT_GW_BID is deferred, not executed
# ---------------------------------------------------------------------------

def test_instant_accept_during_next_gw_bid_defers(mgr, db):
    _seed_league(db, "lg1", window="next_gw_bid", gw=4, current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_member(db, "lg1", "alice")
    _seed_member(db, "lg1", "bob")
    _seed_trade(db, "lg1", "t1", {
        "proposerUid": "alice", "targetUid": "bob",
        "proposerPlayers": [_trade_player(ALICE[2])],   # MID 3
        "targetPlayers": [_trade_player(BOB[2])],        # MID 13
        "status": "pending",
    })

    result = mgr.respond_trade("lg1", "t1", "bob", "accept")

    assert result["status"] == "deferred_pending"
    assert result["targetGw"] == 4
    trade = _trade_doc(db, "lg1", "t1")
    assert trade["status"] == "deferred_pending"
    assert trade["targetGw"] == 4
    # No swap happened yet — squads unchanged.
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}
    assert _squad_ids(db, "lg1", "bob") == {11, 12, 13, 14}


def test_instant_accept_outside_next_gw_bid_executes(mgr, db):
    # No windowOverride → fixture clock with no fixtures → NONE → execute now.
    _seed_league(db, "lg1", window=None, current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_member(db, "lg1", "alice")
    _seed_member(db, "lg1", "bob")
    _seed_trade(db, "lg1", "t1", {
        "proposerUid": "alice", "targetUid": "bob",
        "proposerPlayers": [_trade_player(ALICE[2])],
        "targetPlayers": [_trade_player(BOB[2])],
        "status": "pending",
    })

    result = mgr.respond_trade("lg1", "t1", "bob", "accept")

    assert result["status"] == "accepted"
    # Swap executed immediately.
    assert 13 in _squad_ids(db, "lg1", "alice")
    assert 3 in _squad_ids(db, "lg1", "bob")


def test_simulated_league_finalizes_vote_trade_immediately(mgr, db):
    # A mock (simulated) league has no veto vote / admin to resolve an
    # awaiting_vote trade, so a both-sides-agree accept must execute now even
    # under the default "vote" approval mode — otherwise squads never swap.
    db.collection("leagues").document("lg1").set({
        "status": "group_phase", "tradeApproval": "vote",
        "adminUid": "admin", "currentGw": 4, "simulated": True,
    })
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_member(db, "lg1", "alice")
    _seed_member(db, "lg1", "bob")
    _seed_trade(db, "lg1", "t1", {
        "proposerUid": "alice", "targetUid": "bob",
        "proposerPlayers": [_trade_player(ALICE[2])],
        "targetPlayers": [_trade_player(BOB[2])],
        "status": "pending",
    })

    result = mgr.respond_trade("lg1", "t1", "bob", "accept")

    assert result["status"] == "accepted"          # NOT awaiting_vote
    assert 13 in _squad_ids(db, "lg1", "alice")
    assert 3 in _squad_ids(db, "lg1", "bob")


# ---------------------------------------------------------------------------
# 2. process_deferred_trades executes a still-valid deferred trade atomically
# ---------------------------------------------------------------------------

def test_process_executes_valid_deferred_trade(mgr, db):
    _seed_league(db, "lg1", current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=4))

    result = mgr.process_deferred_trades("lg1", 4)

    assert result == {"executed": [{"tradeId": "t1"}], "cancelled": [], "promoted": []}
    # Squads swapped.
    assert 13 in _squad_ids(db, "lg1", "alice") and 3 not in _squad_ids(db, "lg1", "alice")
    assert 3 in _squad_ids(db, "lg1", "bob") and 13 not in _squad_ids(db, "lg1", "bob")
    # Object metadata travelled with the player.
    moved = next(p for p in _get_players(db, "lg1", "alice") if p["playerId"] == 13)
    assert moved["name"] == "Bob MID"
    # Status flipped to accepted + resolvedAt stamped.
    trade = _trade_doc(db, "lg1", "t1")
    assert trade["status"] == "accepted"
    assert "resolvedAt" in trade
    # Audit transaction written.
    txns = [v for k, v in db._store.items()
            if k.startswith("leagues/lg1/transactions/")]
    assert any(t.get("type") == "trade_accepted" for t in txns)


def test_process_handles_trade_without_target_gw(mgr, db):
    # A deferred doc lacking targetGw is still picked up (graceful handling).
    _seed_league(db, "lg1", current_gw=7)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[0]], [BOB[0]]))  # GK swap, no targetGw

    result = mgr.process_deferred_trades("lg1", 7)

    assert result["executed"] == [{"tradeId": "t1"}]
    assert 11 in _squad_ids(db, "lg1", "alice")


def test_process_skips_other_target_gw(mgr, db):
    _seed_league(db, "lg1", current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=5))

    result = mgr.process_deferred_trades("lg1", 4)

    # targetGw 5 != requested gw 4 → left alone.
    assert result == {"executed": [], "cancelled": [], "promoted": []}
    assert _trade_doc(db, "lg1", "t1")["status"] == "deferred_pending"
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# 3. An invalid deferred trade is cancelled with a reason; squads untouched
# ---------------------------------------------------------------------------

def test_process_cancels_invalid_deferred_trade(mgr, db):
    _seed_league(db, "lg1", current_gw=4)
    # Alice no longer owns the MID (id 3) she promised — squad changed since
    # the trade was deferred.
    alice_changed = [ALICE[0], ALICE[1], _player(99, 3, "Replacement MID"), ALICE[3]]
    _seed_squad(db, "lg1", "alice", alice_changed)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=4))

    before_alice = _get_players(db, "lg1", "alice")
    before_bob = _get_players(db, "lg1", "bob")

    result = mgr.process_deferred_trades("lg1", 4)

    assert result["executed"] == []
    assert len(result["cancelled"]) == 1
    assert result["cancelled"][0]["tradeId"] == "t1"
    assert "PROPOSER_PLAYERS_NOT_OWNED" in result["cancelled"][0]["reason"]

    trade = _trade_doc(db, "lg1", "t1")
    assert trade["status"] == "cancelled"
    assert "PROPOSER_PLAYERS_NOT_OWNED" in trade["cancelReason"]
    assert "resolvedAt" in trade
    # Atomicity: BOTH squads untouched.
    assert _get_players(db, "lg1", "alice") == before_alice
    assert _get_players(db, "lg1", "bob") == before_bob
    # No audit transaction.
    txns = [v for k, v in db._store.items()
            if k.startswith("leagues/lg1/transactions/")]
    assert not any(t.get("type") == "trade_accepted" for t in txns)


# ---------------------------------------------------------------------------
# 4. Orchestrator: deferred trades run BEFORE the auction (observable order)
# ---------------------------------------------------------------------------

def test_orchestrator_runs_deferred_before_auction(mgr, wmgr, db):
    """A deferred trade moves a MID onto u_low's squad; u_low's wishlist bid
    then drops THAT just-acquired MID for a free agent. The bid only validates
    if the trade ran first (playerOut must be owned at auction time)."""
    _seed_league(db, "lg1", current_gw=4)
    _seed_member(db, "lg1", "u_low", waiver_priority=9, draft_position=1)
    _seed_member(db, "lg1", "u_high", waiver_priority=1, draft_position=2)

    low = _legal_squad(0)      # MIDs 7..11
    high = _legal_squad(100)   # MIDs 107..111
    _seed_squad(db, "lg1", "u_low", low)
    _seed_squad(db, "lg1", "u_high", high)

    # Free agent the auction will hand out.
    free_mid = _player(900, 3, "Free MID")
    _seed_wc_player(db, free_mid)

    # Deferred trade: u_low gives MID 7, u_high gives MID 107. After it runs,
    # u_low owns 107 (and no longer owns 7).
    mid7 = next(p for p in low if p["playerId"] == 7)
    mid107 = next(p for p in high if p["playerId"] == 107)
    _seed_trade(db, "lg1", "t1",
                _make_trade("u_low", "u_high", [mid7], [mid107], targetGw=4))

    # u_low's wishlist bid drops the JUST-TRADED-IN MID 107 for free MID 900.
    # Valid ONLY if the trade executed first.
    _seed_bid_doc(db, "lg1", "u_low", 4,
                  [{"playerIn": 900, "playerOut": 107, "position": "MID"}])

    deferred = mgr.process_deferred_trades("lg1", 4)
    auction = wmgr.run_auction("lg1", 4)

    # Trade ran: u_low now has 107 (then) swapped to 900; no longer has 7.
    assert deferred["executed"] == [{"tradeId": "t1"}]
    low_ids = _squad_ids(db, "lg1", "u_low")
    assert 7 not in low_ids
    assert 107 not in low_ids       # dropped by the auction bid
    assert 900 in low_ids           # claimed in the auction
    assert auction["claimsExecuted"] == 1

    # Combined summary shape (as the orchestrator endpoint returns it).
    combined = {"deferredTrades": deferred, "wishlistAuction": auction}
    assert set(combined) == {"deferredTrades", "wishlistAuction"}
    assert combined["deferredTrades"]["executed"] == [{"tradeId": "t1"}]
    assert combined["wishlistAuction"]["claimsExecuted"] == 1


# ---------------------------------------------------------------------------
# 5. A deferred trade can still be cancelled by the proposer before execution
# ---------------------------------------------------------------------------

def test_proposer_can_cancel_deferred_trade(mgr, db):
    _seed_league(db, "lg1", current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=4))

    result = mgr.cancel_trade("lg1", "t1", "alice")

    assert result["status"] == "cancelled"
    assert _trade_doc(db, "lg1", "t1")["status"] == "cancelled"
    # Not executed: it won't be picked up by process_deferred_trades anymore.
    after = mgr.process_deferred_trades("lg1", 4)
    assert after == {"executed": [], "cancelled": [], "promoted": []}
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}


def test_non_participant_cannot_cancel_deferred_bid(mgr, db):
    # The proposer or the target may cancel a deferred bid; an unrelated manager
    # cannot.
    _seed_league(db, "lg1", current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=4))

    with pytest.raises(ValueError, match="Only the proposer can cancel"):
        mgr.cancel_trade("lg1", "t1", "carol")


def test_target_can_cancel_deferred_bid(mgr, db):
    # No-acceptance bid: the target can back out before it executes.
    _seed_league(db, "lg1", current_gw=4)
    _seed_squad(db, "lg1", "alice", ALICE)
    _seed_squad(db, "lg1", "bob", BOB)
    _seed_trade(db, "lg1", "t1",
                _make_trade("alice", "bob", [ALICE[2]], [BOB[2]], targetGw=4))

    assert mgr.cancel_trade("lg1", "t1", "bob")["status"] == "cancelled"
    assert _trade_doc(db, "lg1", "t1")["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Bid-only model (no acceptance): propose in NEXT_GW_BID is born deferred
# ---------------------------------------------------------------------------

def _seed_pair(db, lid, window="next_gw_bid"):
    _seed_league(db, lid, window=window, gw=4, current_gw=4)
    _seed_member(db, lid, "alice")
    _seed_member(db, lid, "bob")
    _seed_squad(db, lid, "alice", ALICE)
    _seed_squad(db, lid, "bob", BOB)


def test_propose_in_gameweek_is_a_bid_no_acceptance(mgr, db):
    _seed_pair(db, "lg1", window="next_gw_bid")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])  # MID for MID
    assert res["status"] == "deferred_pending"
    assert res["isBid"] is True
    assert res["targetGw"] == 4
    # Born deferred — no pending state, squads untouched until window opens.
    assert _trade_doc(db, "lg1", res["tradeId"])["status"] == "deferred_pending"
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}


def test_propose_in_trade_window_is_normal_pending(mgr, db):
    _seed_pair(db, "lg1", window="trade")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])
    assert res["status"] == "pending"
    assert res["isBid"] is False
    assert res.get("targetGw") is None


def test_accept_on_a_bid_is_rejected(mgr, db):
    _seed_pair(db, "lg1", window="next_gw_bid")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])
    with pytest.raises(ValueError, match="gameweek bid"):
        mgr.respond_trade("lg1", res["tradeId"], "bob", "accept")


def test_cancelled_bid_cannot_be_accepted_or_executed(mgr, db):
    # The crux: cancel persists to the DB, and every execution path re-reads it.
    _seed_pair(db, "lg1", window="next_gw_bid")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])
    tid = res["tradeId"]

    mgr.cancel_trade("lg1", tid, "alice")
    assert _trade_doc(db, "lg1", tid)["status"] == "cancelled"

    # A stale cached "accept" by the other manager must NOT pass.
    with pytest.raises(ValueError, match="cancelled and can no longer be accepted"):
        mgr.respond_trade("lg1", tid, "bob", "accept")

    # And it is neither executed nor promoted when the trade window opens —
    # a cancelled doc is no longer deferred_pending, so it's skipped entirely.
    out = mgr.process_deferred_trades("lg1", 4)
    assert out == {"executed": [], "cancelled": [], "promoted": []}
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}
    assert _squad_ids(db, "lg1", "bob") == {11, 12, 13, 14}


def test_uncancelled_bid_becomes_pending_offer_at_window_open(mgr, db):
    # The bid must NEVER auto-execute (that would take a player without consent).
    # At window open it is PROMOTED to a normal pending offer; squads untouched.
    _seed_pair(db, "lg1", window="next_gw_bid")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])
    tid = res["tradeId"]

    out = mgr.process_deferred_trades("lg1", 4)
    assert out["promoted"] == [{"tradeId": tid}]
    assert out["executed"] == []

    doc = _trade_doc(db, "lg1", tid)
    assert doc["status"] == "pending"        # now awaiting the target's acceptance
    assert doc["isBid"] is False             # acceptable as a normal trade
    assert doc["openedFromBid"] is True      # provenance preserved
    # No theft: squads are exactly as before until the target accepts.
    assert _squad_ids(db, "lg1", "alice") == {1, 2, 3, 4}
    assert _squad_ids(db, "lg1", "bob") == {11, 12, 13, 14}


def test_promoted_bid_executes_only_after_target_accepts(mgr, db):
    # Full path: bid -> promoted to pending -> target accepts in the trade
    # window -> squads swap. Consent is required for the swap to happen.
    _seed_pair(db, "lg1", window="next_gw_bid")
    res = mgr.propose_trade("lg1", "alice", "bob", [3], [13])
    tid = res["tradeId"]
    mgr.process_deferred_trades("lg1", 4)  # promote to pending

    # Trade window is now open; the target (bob) accepts.
    db.collection("leagues").document("lg1").update(
        {"windowOverride": {"phase": "trade", "gw": 4}}
    )
    mgr.respond_trade("lg1", tid, "bob", "accept")

    assert 13 in _squad_ids(db, "lg1", "alice")
    assert 3 in _squad_ids(db, "lg1", "bob")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
