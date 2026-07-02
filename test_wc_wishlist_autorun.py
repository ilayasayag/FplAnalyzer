#!/usr/bin/env python3
"""Tier-1 unit tests for the wishlist AUTO-RUN pipeline (sprint: wishlist bid
run, part 1) — the orchestrator that fires the auction when the FREE_AGENTS
window opens (cron window-tick / admin phase switch / schedule save).

Reuses the in-memory fake Firestore from ``test_wc_wishlist``.

Run:
    .venv/bin/python -m pytest test_wc_wishlist_autorun.py -v

Covers:
  * happy path: lease created, snapshot written BEFORE mutations, deferred
    trades processed, auction resolved, league.wishlistAutoRun = done;
  * idempotency: second trigger skips (already resolved / lease held);
  * guards: wrong phase, simulated league, currentGw mismatch (previous GW
    not finalized), earlier-GW auction never ran — all block/skip cleanly;
  * concurrency: a held ``running`` lease skips; ``failed`` and
    ``rolled_back`` leases block (never silently re-run);
  * stale-tab sweep: pending bids left in an already-resolved earlier gw are
    merged into the target gw (current bucket first, deduped) and auctioned;
  * rollback parks the lease as rolled_back → auto-run refuses to re-fire;
  * submit_bids hard gate: no writes (including clears) into a closed or
    currently-resolving bucket; get_my_bids reports a closed bucket as
    resolved even for a manager who never bid in it.
"""

import os
import sys
from datetime import datetime, timezone

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_wishlist import WCWishlistManager  # noqa: E402
from fpl_predictor.game.wc_wishlist_autorun import WishlistAutoRunner  # noqa: E402

from test_wc_wishlist import (  # noqa: E402
    FakeDB, FREE_MIDS, _bid, _legal_squad, _seed_bid_doc, _seed_member,
    _seed_squad, _seed_wc_player, _squad_ids,
)

import google.cloud.firestore_v1 as _fs  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_transactional(monkeypatch):
    # Same contract shim as test_wc_wishlist (fixtures don't cross modules).
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


NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
LID = "lg"


class StubTradeMgr:
    def __init__(self):
        self.calls = []

    def process_deferred_trades(self, lid, gw):
        self.calls.append((lid, gw))
        return {"executed": 0}


def _seed_league(db, current_gw=2, phase="free_agents", override_gw=2,
                 simulated=False):
    doc = {"currentGw": current_gw,
           "windowOverride": {"phase": phase, "gw": override_gw}}
    if simulated:
        doc["simulated"] = True
    db.collection("leagues").document(LID).set(doc)


def _league_ref(db):
    return db.collection("leagues").document(LID)


@pytest.fixture
def db():
    d = FakeDB()
    for p in FREE_MIDS:
        _seed_wc_player(d, p)
    # Two managers; u_low picks first (worst team → waiverPriority 1).
    _seed_member(d, LID, "u_low", 1, 1)
    _seed_member(d, LID, "u_high", 2, 2)
    squad_low, squad_high = _legal_squad(100), _legal_squad(200)
    for p in squad_low + squad_high:
        _seed_wc_player(d, p)
    _seed_squad(d, LID, "u_low", squad_low)
    _seed_squad(d, LID, "u_high", squad_high)
    return d


@pytest.fixture
def wishlist_mgr(db):
    return WCWishlistManager(db)


@pytest.fixture
def trade_mgr():
    return StubTradeMgr()


@pytest.fixture
def runner(db, wishlist_mgr, trade_mgr):
    return WishlistAutoRunner(db, wishlist_mgr, trade_mgr)


def _seed_contested_bids(db):
    # Both want free MID 900; u_low picks first, u_high falls back to 901.
    _seed_bid_doc(db, LID, "u_low", 2, [_bid(900, 107)])
    _seed_bid_doc(db, LID, "u_high", 2, [_bid(900, 207), _bid(901, 208)])


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------

def test_happy_path_runs_auction_with_lease_and_snapshot(runner, db, trade_mgr):
    _seed_league(db)
    _seed_contested_bids(db)

    res = runner.run_if_due(LID, source="cron", now=NOW)

    assert res["status"] == "done"
    assert res["gw"] == 2
    assert res["claims"] == 2
    # Contested 900 → u_low (last place, picks first); u_high got fallback 901.
    assert 900 in _squad_ids(db, LID, "u_low")
    assert 901 in _squad_ids(db, LID, "u_high")
    # Deferred trades processed for the same gw, BEFORE the auction resolved.
    assert trade_mgr.calls == [(LID, 2)]
    # Results + lease.
    assert _league_ref(db).collection("wishlist_results").document("2").get().exists
    lease = _league_ref(db).collection("wishlist_runs").document("2").get().to_dict()
    assert lease["status"] == "done" and lease["claims"] == 2
    # Snapshot captured the PRE-auction state (bids still unresolved, squads
    # still without the claimed free agents).
    snap = (_league_ref(db).collection("wishlist_snapshots")
            .document(res["snapshotId"]).get().to_dict())
    assert snap["gw"] == 2 and snap["source"] == "cron"
    assert snap["capturedAtUtc"] == NOW.isoformat()
    assert "+03:00" in snap["capturedAtIsrael"]
    assert not snap["bids"]["u_low_2"].get("resolved")
    assert 900 not in {p["playerId"] for p in snap["squads"]["u_low"]}
    # Surfaced on the league doc for the admin banner.
    status = (_league_ref(db).get().to_dict() or {}).get("wishlistAutoRun")
    assert status["status"] == "done" and status["gw"] == 2


def test_second_trigger_is_a_noop(runner, db):
    _seed_league(db)
    _seed_contested_bids(db)
    assert runner.run_if_due(LID, source="cron", now=NOW)["status"] == "done"

    res = runner.run_if_due(LID, source="manual_override", now=NOW)
    assert res["status"] == "skipped"
    assert res["reason"] == "already_resolved"


# ---------------------------------------------------------------------------
# 2. Phase / league gating
# ---------------------------------------------------------------------------

def test_skips_outside_free_agents_phase(runner, db):
    _seed_league(db, phase="trade")
    _seed_contested_bids(db)

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "skipped"
    assert res["reason"] == "phase_trade"
    assert not _league_ref(db).collection("wishlist_results").document("2").get().exists


def test_skips_simulated_league(runner, db):
    _seed_league(db, simulated=True)
    _seed_contested_bids(db)

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res == {"lid": LID, "status": "skipped", "reason": "simulated_league"}


# ---------------------------------------------------------------------------
# 3. Blocking guards (surfaced on league.wishlistAutoRun)
# ---------------------------------------------------------------------------

def test_blocks_when_previous_gw_not_finalized(runner, db):
    # finalize_gw would have advanced currentGw to 2; it didn't.
    _seed_league(db, current_gw=1, override_gw=2)
    _seed_contested_bids(db)

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "blocked"
    assert "finalize" in res["reason"]
    assert not _league_ref(db).collection("wishlist_runs").document("2").get().exists
    assert not _league_ref(db).collection("wishlist_results").document("2").get().exists
    status = (_league_ref(db).get().to_dict() or {}).get("wishlistAutoRun")
    assert status["status"] == "blocked" and status["gw"] == 2


def test_blocks_when_an_earlier_auction_never_ran(runner, db):
    _seed_league(db)
    _seed_contested_bids(db)
    # gw1 has pending bids but NO wishlist_results/1 → a whole auction was
    # skipped; needs a human, not a silent sweep.
    _seed_bid_doc(db, LID, "u_low", 1, [_bid(901, 108)])

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "blocked"
    assert "gw 1" in res["reason"]
    assert not _league_ref(db).collection("wishlist_results").document("2").get().exists


# ---------------------------------------------------------------------------
# 4. Lease semantics
# ---------------------------------------------------------------------------

def test_running_lease_skips(runner, db):
    _seed_league(db)
    _seed_contested_bids(db)
    _league_ref(db).collection("wishlist_runs").document("2").set(
        {"gw": 2, "status": "running"})

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "skipped" and res["reason"] == "lease_running"
    assert not _league_ref(db).collection("wishlist_results").document("2").get().exists


def test_failed_lease_blocks_until_cleared(runner, db):
    _seed_league(db)
    _seed_contested_bids(db)
    _league_ref(db).collection("wishlist_runs").document("2").set(
        {"gw": 2, "status": "failed", "error": "boom"})

    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "blocked"
    assert "FAILED" in res["reason"]

    # Deleting the lease (the documented operator action) unblocks the retry.
    _league_ref(db).collection("wishlist_runs").document("2").delete()
    assert runner.run_if_due(LID, source="cron", now=NOW)["status"] == "done"


def test_rollback_parks_lease_and_autorun_refuses(runner, db, wishlist_mgr):
    _seed_league(db)
    _seed_contested_bids(db)
    assert runner.run_if_due(LID, source="cron", now=NOW)["status"] == "done"

    wishlist_mgr.rollback_auction(LID, 2)
    lease = _league_ref(db).collection("wishlist_runs").document("2").get().to_dict()
    assert lease["status"] == "rolled_back"

    # The very next tick must NOT silently re-run the auction the admin just
    # rolled back — it blocks until the lease doc is deleted on purpose.
    res = runner.run_if_due(LID, source="cron", now=NOW)
    assert res["status"] == "blocked"
    assert "rolled back" in res["reason"]
    assert not _league_ref(db).collection("wishlist_results").document("2").get().exists


# ---------------------------------------------------------------------------
# 5. Stale-tab sweep
# ---------------------------------------------------------------------------

def test_stale_bucket_bids_are_swept_forward_and_auctioned(runner, db):
    _seed_league(db)
    # gw1 already resolved (results doc exists) but a stale tab left u_low's
    # pending bids in the gw1 bucket; u_high bid normally for gw2.
    _league_ref(db).collection("wishlist_results").document("1").set(
        {"gw": 1, "claimsExecuted": 0})
    _seed_bid_doc(db, LID, "u_low", 1, [_bid(900, 107)])
    _seed_bid_doc(db, LID, "u_high", 2, [_bid(900, 207), _bid(901, 208)])

    res = runner.run_if_due(LID, source="cron", now=NOW)

    assert res["status"] == "done"
    assert res["swept"] == [{"from": "u_low_1", "to": "u_low_2", "moved": 1}]
    # The stray doc is gone (its copy lives in the snapshot) and the swept bid
    # took part in the auction: u_low still picks first → wins contested 900.
    assert not _league_ref(db).collection("wishlist_bids").document("u_low_1").get().exists
    assert 900 in _squad_ids(db, LID, "u_low")
    assert 901 in _squad_ids(db, LID, "u_high")


def test_sweep_appends_after_current_bucket_and_dedupes(runner, db):
    _seed_league(db)
    _league_ref(db).collection("wishlist_results").document("1").set({"gw": 1})
    # u_low has BOTH a current gw2 list and a stale gw1 list sharing one bid.
    _seed_bid_doc(db, LID, "u_low", 1, [_bid(900, 107), _bid(901, 108)])
    _seed_bid_doc(db, LID, "u_low", 2, [_bid(900, 107)])

    res = runner.run_if_due(LID, source="cron", now=NOW)

    assert res["status"] == "done"
    assert res["swept"] == [{"from": "u_low_1", "to": "u_low_2", "moved": 1}]
    # Current bucket kept priority; the non-duplicate stale bid appended after.
    resolved = (_league_ref(db).collection("wishlist_bids")
                .document("u_low_2").get().to_dict())
    assert [(b["playerIn"], b["playerOut"]) for b in resolved["bids"]] == [
        (900, 107), (901, 108)]


# ---------------------------------------------------------------------------
# 6. submit_bids hard gate + get_my_bids bucket closure
# ---------------------------------------------------------------------------

def test_submit_rejected_into_resolved_bucket(runner, db, wishlist_mgr):
    _seed_league(db)
    _seed_contested_bids(db)
    assert runner.run_if_due(LID, source="cron", now=NOW)["status"] == "done"

    # A stale tab re-submits into the resolved gw2 bucket → refused, and the
    # resolved audit doc is untouched.
    with pytest.raises(ValueError, match="WISHLIST_LOCKED"):
        wishlist_mgr.submit_bids(LID, "u_low", 2, [_bid(902, 108)])
    # The clear path (empty list = delete) is just as destructive → refused.
    with pytest.raises(ValueError, match="WISHLIST_LOCKED"):
        wishlist_mgr.submit_bids(LID, "u_low", 2, [])
    doc = (_league_ref(db).collection("wishlist_bids")
           .document("u_low_2").get().to_dict())
    assert doc["resolved"] is True
    assert doc["bids"][0]["status"] == "done-completed"


def test_submit_rejected_while_auction_running(db, wishlist_mgr):
    _seed_league(db)
    _league_ref(db).collection("wishlist_runs").document("2").set(
        {"gw": 2, "status": "running"})

    with pytest.raises(ValueError, match="AUCTION_RUNNING"):
        wishlist_mgr.submit_bids(LID, "u_low", 2, [_bid(900, 107)])


def test_get_my_bids_reports_closed_bucket_for_non_bidder(runner, db, wishlist_mgr):
    _seed_league(db)
    # Only u_high bids; u_low never had a gw2 doc.
    _seed_bid_doc(db, LID, "u_high", 2, [_bid(900, 207)])
    assert runner.run_if_due(LID, source="cron", now=NOW)["status"] == "done"

    # Without this, u_low's client would bucket new bids into the CLOSED gw2
    # (own doc missing → looked unresolved) and then be rejected by the gate.
    mine = wishlist_mgr.get_my_bids(LID, "u_low", 2)
    assert mine["resolved"] is True
    assert mine["bids"] == []
