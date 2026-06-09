#!/usr/bin/env python3
"""Tier-1 unit tests for the WC 2026 wishlist auction (PR 4).

Pure unit tests — no Firestore emulator, no prod. A lightweight in-memory fake
Firestore models exactly what ``WCWishlistManager`` touches:
``leagues/{lid}/members/{uid}``, ``leagues/{lid}/squads/{uid}``,
``leagues/{lid}/wishlist_bids/{uid}_{gw}``, ``leagues/{lid}/transactions``, and
the top-level ``wc_players/{id}`` collection. It honours the real
``@firestore.transactional`` contract used by ``_execute_swap``, supports
collection ``.get()`` iteration + ``.where("gw","==",n)`` filtering, and
``db.batch()`` deletes.

Run:
    .venv/bin/python -m pytest test_wc_wishlist.py -v

Acceptance (WC2026_WINDOWS_DESIGN.md §4, §13 PR 4):
  * ordering + deterministic tie-break (waiverPriority DESC, draftPosition DESC,
    uid ASC) under duplicate waiverPriority;
  * auto-skip an invalid first bid, take the next valid one;
  * no double-claim of a contested free agent (higher priority wins);
  * quota safety (2/5/5/3) — a quota-breaking swap is skipped;
  * multi-round round-robin (a manager who claimed in round 1 can claim in
    round 2);
  * wishlist_bids batch-deleted after the auction.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_wishlist import WCWishlistManager  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory fake Firestore
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        if self._data is None:
            return None
        # deep-ish copy so callers mutate only via set/update
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
            if "/" in rest:  # only direct children
                continue
            docs.append(FakeSnapshot(rest, data))
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

    # top-level collection iteration (wc_players)
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


def _legal_squad(base_id, *, extra=None):
    """A quota-legal 15-man squad (2/5/5/3) with deterministic ids.

    ids: base_id+0,1 = GK ; +2..6 = DEF ; +7..11 = MID ; +12..14 = FWD.
    """
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


def _seed_member(db, lid, uid, waiver_priority, draft_position):
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


def _squad_ids(db, lid, uid):
    snap = (db.collection("leagues").document(lid)
            .collection("squads").document(uid).get())
    return {p["playerId"] for p in snap.to_dict()["players"]}


def _bid(player_in, player_out):
    return {"playerIn": player_in, "playerOut": player_out, "position": "MID"}


# Free-agent MIDs available for the auction (not on any squad).
FREE_MIDS = [_player(900, 3, "Free A"), _player(901, 3, "Free B"),
             _player(902, 3, "Free C")]
FREE_GK = _player(950, 1, "Free GK")


@pytest.fixture
def db():
    d = FakeDB()
    for p in FREE_MIDS:
        _seed_wc_player(d, p)
    _seed_wc_player(d, FREE_GK)
    return d


@pytest.fixture
def mgr(db):
    return WCWishlistManager(db)


# ---------------------------------------------------------------------------
# 1. Ordering + deterministic tie-break
# ---------------------------------------------------------------------------

def test_ordering_tiebreak_under_duplicate_priority(mgr, db):
    # Three managers; A and B share waiverPriority=5 (dup). Last-pick-first is
    # waiverPriority DESC, then draftPosition DESC, then uid ASC.
    _seed_member(db, "lg", "u_b", 5, 2)
    _seed_member(db, "lg", "u_a", 5, 4)   # same priority, higher draftPos → first
    _seed_member(db, "lg", "u_c", 7, 1)   # highest priority → very first

    order = mgr._ordered_managers("lg")
    # u_c (7) first; then among the 5s, higher draftPosition first → u_a (4)
    # before u_b (2).
    assert order == ["u_c", "u_a", "u_b"]


def test_ordering_uid_breaks_full_tie(mgr, db):
    _seed_member(db, "lg", "u_z", 5, 3)
    _seed_member(db, "lg", "u_a", 5, 3)   # identical priority+draftPos → uid ASC
    order = mgr._ordered_managers("lg")
    assert order == ["u_a", "u_z"]


# ---------------------------------------------------------------------------
# 2. Auto-skip an invalid first bid, take the next valid one
# ---------------------------------------------------------------------------

def test_autoskip_invalid_first_bid(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))  # MIDs 7..11
    # First bid drops a MID the manager does NOT own (id 999) → skipped.
    # Second bid is valid: drop MID 7, bring free MID 900.
    _seed_bid_doc(db, "lg", "u1", 4, [_bid(900, 999), _bid(900, 7)])

    summary = mgr.run_auction("lg", 4)

    assert summary["claimsExecuted"] == 1
    assert summary["executed"][0] == {"uid": "u1", "playerIn": 900, "playerOut": 7}
    ids = _squad_ids(db, "lg", "u1")
    assert 900 in ids and 7 not in ids
    # The bad bid was recorded as skipped.
    assert any(s["reason"] == "PLAYER_OUT_NOT_OWNED" for s in summary["skipped"])


# ---------------------------------------------------------------------------
# 3. No double-claim of a contested free agent
# ---------------------------------------------------------------------------

def test_contested_free_agent_goes_to_higher_priority(mgr, db):
    # u_low has higher waiverPriority (picks first, last-pick-first). Both bid
    # for free MID 900. u_low wins; u_high falls through to MID 901.
    _seed_member(db, "lg", "u_low", 9, 1)   # last pick → first dibs
    _seed_member(db, "lg", "u_high", 1, 2)
    _seed_squad(db, "lg", "u_low", _legal_squad(0))     # MIDs 7..11
    _seed_squad(db, "lg", "u_high", _legal_squad(100))  # MIDs 107..111
    _seed_bid_doc(db, "lg", "u_low", 4, [_bid(900, 7)])
    _seed_bid_doc(db, "lg", "u_high", 4, [_bid(900, 107), _bid(901, 107)])

    summary = mgr.run_auction("lg", 4)

    low_ids = _squad_ids(db, "lg", "u_low")
    high_ids = _squad_ids(db, "lg", "u_high")
    assert 900 in low_ids                       # contested player to higher prio
    assert 900 not in high_ids
    assert 901 in high_ids                       # loser falls through to next bid
    execs = {(e["uid"], e["playerIn"]) for e in summary["executed"]}
    assert ("u_low", 900) in execs
    assert ("u_high", 901) in execs


# ---------------------------------------------------------------------------
# 4. Quota safety: a swap that would break 2/5/5/3 is skipped
# ---------------------------------------------------------------------------

def test_quota_violation_is_skipped(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    # Drop a MID (id 7) but bring in a GK (950) → would be 3 GK / 4 MID → illegal.
    # Second bid is a clean same-position MID swap.
    _seed_bid_doc(db, "lg", "u1", 4, [_bid(950, 7), _bid(900, 7)])

    summary = mgr.run_auction("lg", 4)

    assert any(s["reason"] == "QUOTA_VIOLATION" for s in summary["skipped"])
    ids = _squad_ids(db, "lg", "u1")
    assert 950 not in ids          # quota-breaking GK never added
    assert 900 in ids and 7 not in ids


# ---------------------------------------------------------------------------
# 5. Multi-round round-robin
# ---------------------------------------------------------------------------

def test_multi_round_same_manager_claims_twice(mgr, db):
    # Single manager with two independent valid bids. Round 1 takes the first;
    # round 2 takes the second (one claim per manager per round).
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))  # MIDs 7,8,9,10,11
    _seed_bid_doc(db, "lg", "u1", 4, [_bid(900, 7), _bid(901, 8)])

    summary = mgr.run_auction("lg", 4)

    assert summary["claimsExecuted"] == 2
    ids = _squad_ids(db, "lg", "u1")
    assert {900, 901} <= ids
    assert 7 not in ids and 8 not in ids
    # Quota still legal: still exactly 5 MIDs (dropped 7,8; added 900,901).
    snap = (db.collection("leagues").document("lg")
            .collection("squads").document("u1").get())
    mids = [p for p in snap.to_dict()["players"] if p["position"] == 3]
    assert len(mids) == 5


def test_round_robin_alternates_between_managers(mgr, db):
    # Two managers each want two free MIDs; with one claim per round each, the
    # auction must cycle twice. Distinct targets so no contention.
    _seed_member(db, "lg", "u_first", 9, 1)   # first dibs
    _seed_member(db, "lg", "u_second", 1, 2)
    _seed_squad(db, "lg", "u_first", _legal_squad(0))
    _seed_squad(db, "lg", "u_second", _legal_squad(100))
    _seed_bid_doc(db, "lg", "u_first", 4, [_bid(900, 7), _bid(901, 8)])
    _seed_bid_doc(db, "lg", "u_second", 4, [_bid(902, 107)])

    summary = mgr.run_auction("lg", 4)

    assert _squad_ids(db, "lg", "u_first") >= {900, 901}
    assert 902 in _squad_ids(db, "lg", "u_second")
    assert summary["claimsExecuted"] == 3


# ---------------------------------------------------------------------------
# 6. wishlist_bids batch-deleted after the auction
# ---------------------------------------------------------------------------

def test_bids_deleted_after_auction(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    _seed_bid_doc(db, "lg", "u1", 4, [_bid(900, 7)])
    # A bid for a DIFFERENT gw must survive.
    _seed_bid_doc(db, "lg", "u1", 5, [_bid(901, 8)])

    mgr.run_auction("lg", 4)

    coll = (db.collection("leagues").document("lg")
            .collection("wishlist_bids"))
    remaining = {d.id for d in coll.get()}
    assert "u1_4" not in remaining        # gw 4 wiped
    assert "u1_5" in remaining            # gw 5 untouched


def test_audit_transaction_written_per_claim(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    _seed_bid_doc(db, "lg", "u1", 4, [_bid(900, 7)])

    mgr.run_auction("lg", 4)

    txns = [v for k, v in db._store.items()
            if k.startswith("leagues/lg/transactions/")]
    claim_txns = [t for t in txns if t.get("type") == "wishlist_claim"]
    assert len(claim_txns) == 1
    assert claim_txns[0]["playerIn"] == 900 and claim_txns[0]["playerOut"] == 7


# ---------------------------------------------------------------------------
# 7. submit_bids validation
# ---------------------------------------------------------------------------

def test_submit_bids_rejects_cross_position(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    # Drop MID 7, claim GK 950 → cross-position, rejected on write.
    with pytest.raises(ValueError, match="POSITION_MISMATCH"):
        mgr.submit_bids("lg", "u1", 4, [{"playerIn": 950, "playerOut": 7}])


def test_submit_bids_rejects_owned_player_in(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    _seed_wc_player(db, _player(8, 3, "MID1"))  # exists in wc_players...
    # ...but playerIn id 8 is already on the squad → not a free agent.
    with pytest.raises(ValueError, match="PLAYER_ALREADY_OWNED"):
        mgr.submit_bids("lg", "u1", 4, [{"playerIn": 8, "playerOut": 7}])


def test_submit_bids_persists_and_reads_back(mgr, db):
    _seed_member(db, "lg", "u1", 1, 1)
    _seed_squad(db, "lg", "u1", _legal_squad(0))
    mgr.submit_bids("lg", "u1", 4, [{"playerIn": 900, "playerOut": 7}])
    doc = mgr.get_my_bids("lg", "u1", 4)
    assert doc["bids"] == [{"playerIn": 900, "playerOut": 7, "position": "MID"}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------------------
# Mock auto-bid generator (generate_mock_bids) — demo helper
# ---------------------------------------------------------------------------

def test_generate_mock_bids_skips_runner_and_auction_applies(mgr, db):
    lid = "L"
    _seed_member(db, lid, "A", 5, 1)   # the runner — excluded, keeps own bids
    _seed_member(db, lid, "B", 3, 2)
    _seed_member(db, lid, "C", 1, 3)
    _seed_squad(db, lid, "A", _legal_squad(100))
    _seed_squad(db, lid, "B", _legal_squad(200))
    _seed_squad(db, lid, "C", _legal_squad(300))
    gw = 3

    summary = mgr.generate_mock_bids(lid, gw, exclude_uid="A")
    uids = {s["uid"] for s in summary}
    assert "A" not in uids                      # runner skipped
    assert {"B", "C"}.issubset(uids)

    # Each generated bid is a valid same-position swap (FA in, own player out).
    free_ids = {900, 901, 902, 950}
    for who, base in (("B", 200), ("C", 300)):
        bids = mgr.get_my_bids(lid, who, gw)["bids"]
        assert 1 <= len(bids) <= 3
        own = set(range(base, base + 15))
        for bd in bids:
            assert bd["playerIn"] in free_ids
            assert bd["playerOut"] in own
    assert mgr.get_my_bids(lid, "A", gw)["bids"] == []   # runner untouched

    # Auction applies them: claimants' squads change but stay 15-man legal.
    before_b = _squad_ids(db, lid, "B")
    res = mgr.run_auction(lid, gw)
    assert res["claimsExecuted"] >= 1
    after_b = _squad_ids(db, lid, "B")
    assert len(after_b) == 15 and before_b != after_b
    assert _squad_ids(db, lid, "A") == set(range(100, 115))  # runner unchanged


# ---------------------------------------------------------------------------
# Durable auction history (wishlist_results) + failed-bid tracking
# ---------------------------------------------------------------------------

def test_auction_persists_results_with_claimed_and_cancelled(mgr, db):
    lid = "L"
    _seed_member(db, lid, "A", 5, 1)   # higher waiver priority → picks first
    _seed_member(db, lid, "B", 3, 2)
    _seed_squad(db, lid, "A", _legal_squad(100))
    _seed_squad(db, lid, "B", _legal_squad(200))
    gw = 3
    # Both contest the same free MID (900); A drops own MID 107, B drops 207.
    _seed_bid_doc(db, lid, "A", gw, [_bid(900, 107)])
    _seed_bid_doc(db, lid, "B", gw, [_bid(900, 207)])

    res = mgr.run_auction(lid, gw)

    # One claim executed (A by priority), the other cancelled.
    assert res["claimsExecuted"] == 1
    assert res["executed"] == [{"uid": "A", "playerIn": 900, "playerOut": 107}]
    assert len(res["failed"]) == 1 and res["failed"][0]["uid"] == "B"

    # Durable record persisted (survives bid deletion), ordered per manager.
    doc = (db.collection("leagues").document(lid)
           .collection("wishlist_results").document(str(gw)).get()).to_dict()
    assert doc["gw"] == gw and doc["claimsExecuted"] == 1
    by_uid = {r["uid"]: r["bids"] for r in doc["results"]}
    assert by_uid["A"][0]["status"] == "claimed"
    assert by_uid["B"][0]["status"] == "cancelled"
    # Bids themselves are gone, but the history remains.
    assert mgr.get_my_bids(lid, "A", gw)["bids"] == []
