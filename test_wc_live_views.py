"""Route-level tests for the LIVE mid-GW views (Slice C).

Two endpoints learn to compose a live answer instead of returning empty/404
while a GW is in progress (standings docs and gw_history snapshots are only
written by finalize_gw AFTER a GW completes):

  * GET /leagues/<lid>/standings — when no finalized standings doc exists for
    the requested/current GW of an ACTIVE league, composes a live overlay:
    every member baselined at zero, the last finalized ``standings/current``
    overlaid (H2H record/points FROZEN), and the live GW's points from
    ``scores/{currentGw}`` added to total fantasy points. Marked ``live: true``
    with an ``updatedAt``.

  * GET /leagues/<lid>/gw-history/<uid> — when the snapshot doesn't exist but
    the GW's lineups are locked, composes a live snapshot from the frozen
    lineup joined to the GW fixtures' playerScores (captain doubled). Pre-lock,
    an opponent's lineup is private (403); your own stays a 404 so the client
    falls back to the squad list.

Pure unit tests against the shared in-memory FakeDB (test_helpers), with
``_require_auth`` / ``is_lineup_locked`` monkeypatched at the api_wc module.
"""

import os
import sys
from datetime import datetime, timezone

import flask
import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import fpl_predictor.api_wc as api_wc  # noqa: E402
from test_helpers import FakeDB  # noqa: E402

LID = "L1"
ME = "u_me"


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    """All requests authenticated as ME unless a test overrides."""
    monkeypatch.setattr(api_wc, "_require_auth", lambda: (ME, None))


def _call(db, path, view, *args, query=None):
    api_wc.init_wc(db)
    app = flask.Flask(__name__)
    with app.test_request_context(path, query_string=query or {}):
        resp, status = view(*args)
        return status, resp.get_json()["data"]


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_league(db, status="group_phase", current_gw=1, qualifiers=2):
    db.store[f"leagues/{LID}"] = {
        "status": status, "currentGw": current_gw,
        "knockoutQualifiers": qualifiers,
    }
    for uid, team in [(ME, "Me XI"), ("u_a", "Alpha"), ("u_b", "Bravo")]:
        db.store[f"leagues/{LID}/members/{uid}"] = {
            "displayName": uid, "teamName": team,
        }


def _seed_live_scores(db, gw, points_by_uid):
    db.store[f"leagues/{LID}/scores/{gw}"] = {
        "results": {uid: {"points": pts} for uid, pts in points_by_uid.items()},
        "live": True,
        "updatedAt": datetime(2026, 6, 12, 18, 30, tzinfo=timezone.utc),
    }


def _seed_finalized_standings(db, managers, qualifiers=2):
    db.store[f"leagues/{LID}/standings/current"] = {
        "managers": managers, "qualifiers": qualifiers,
    }


def _seed_player_scores(db, gw, pts_by_pid):
    fid = 9000 + gw
    db.store[f"wc_fixtures/{fid}"] = {"id": fid, "gw": gw}
    for pid, pts in pts_by_pid.items():
        db.store[f"wc_fixtures/{fid}/playerScores/{pid}"] = {
            "playerId": pid, "gw": gw, "fantasyPoints": pts,
            "stats": {"minutes": 90},
        }


# ---------------------------------------------------------------------------
# Standings — live overlay
# ---------------------------------------------------------------------------

def _get_standings(db, query=None):
    return _call(db, f"/leagues/{LID}/standings", api_wc.get_standings, LID,
                 query=query)


def test_standings_live_compose_no_docs_at_all(db):
    """Mid-GW1 (nothing finalized yet): every member appears, zeros baseline,
    live GW points overlaid onto fpts, H2H all zero, live:true + updatedAt."""
    _seed_league(db, current_gw=1)
    _seed_live_scores(db, 1, {ME: 30, "u_a": 41})

    status, data = _get_standings(db)
    assert status == 200
    assert data["live"] is True
    assert data["gw"] == 1
    assert data["updatedAt"]  # serialized timestamp from the scores doc
    managers = data["managers"]
    assert len(managers) == 3  # u_b has no live points but still has a row
    by_uid = {m["uid"]: m for m in managers}
    assert by_uid[ME]["fpts"] == 30
    assert by_uid["u_a"]["fpts"] == 41
    assert by_uid["u_b"]["fpts"] == 0
    # No provisional H2H mid-GW.
    for m in managers:
        assert (m["hw"], m["hd"], m["hl"], m["hpts"]) == (0, 0, 0, 0)
    # Ranked by (hpts, fpts): u_a > ME > u_b; qualifiers=2 flags the cut.
    assert [m["uid"] for m in managers] == ["u_a", ME, "u_b"]
    assert [m["rank"] for m in managers] == [1, 2, 3]
    assert by_uid["u_b"]["knockedOut"] is True
    assert by_uid[ME]["qualified"] is True


def test_standings_live_overlay_keeps_h2h_frozen(db):
    """After GW1 finalize, mid-GW2: fpts = finalized total + live GW2 points;
    W/D/L + H2H pts stay exactly as the last finalized standings."""
    _seed_league(db, current_gw=2)
    _seed_finalized_standings(db, [
        {"uid": ME, "displayName": ME, "teamName": "Me XI",
         "hw": 1, "hd": 0, "hl": 0, "hpts": 3, "fpts": 50,
         "bonusPoints": 0, "gwPoints": {"1": 50}, "rank": 1},
        {"uid": "u_a", "displayName": "u_a", "teamName": "Alpha",
         "hw": 0, "hd": 0, "hl": 1, "hpts": 0, "fpts": 45,
         "bonusPoints": 0, "gwPoints": {"1": 45}, "rank": 2},
        {"uid": "u_b", "displayName": "u_b", "teamName": "Bravo",
         "hw": 0, "hd": 0, "hl": 0, "hpts": 1, "fpts": 40,
         "bonusPoints": 0, "gwPoints": {"1": 40}, "rank": 3},
    ])
    _seed_live_scores(db, 2, {ME: 10, "u_a": 25})

    status, data = _get_standings(db)
    assert status == 200
    assert data["live"] is True
    by_uid = {m["uid"]: m for m in data["managers"]}
    assert by_uid[ME]["fpts"] == 60       # 50 + 10 live
    assert by_uid["u_a"]["fpts"] == 70    # 45 + 25 live
    assert by_uid["u_b"]["fpts"] == 40    # no live points yet
    # H2H frozen as finalized — no provisional results from the live GW.
    assert by_uid[ME]["hpts"] == 3 and by_uid[ME]["hw"] == 1
    assert by_uid["u_a"]["hpts"] == 0 and by_uid["u_a"]["hl"] == 1
    assert by_uid["u_b"]["hpts"] == 1
    # Live GW points exposed per-GW too.
    assert by_uid[ME]["gwPoints"]["2"] == 10
    # Rank still H2H-first: ME(3) > u_b(1) > u_a(0) despite u_a's fpts lead.
    assert [m["uid"] for m in data["managers"]] == [ME, "u_b", "u_a"]


def test_standings_finalized_snapshot_unchanged(db):
    """?gw=N with a finalized snapshot returns it verbatim — no live flag."""
    _seed_league(db, current_gw=3)
    snapshot = {"managers": [{"uid": ME, "rank": 1, "hpts": 6, "fpts": 99}],
                "qualifiers": 2}
    db.store[f"leagues/{LID}/standings/2"] = snapshot

    status, data = _get_standings(db, query={"gw": "2"})
    assert status == 200
    assert "live" not in data
    assert data["managers"] == snapshot["managers"]


def test_standings_inactive_league_keeps_legacy_behaviour(db):
    """A non-active league must not get a live overlay: 'current' doc when it
    exists, else empty managers."""
    _seed_league(db, status="pre_draft")
    status, data = _get_standings(db)
    assert status == 200
    assert data["managers"] == [] and "live" not in data

    _seed_finalized_standings(db, [{"uid": ME, "rank": 1, "hpts": 0, "fpts": 1}])
    status, data = _get_standings(db)
    assert status == 200
    assert data["managers"][0]["uid"] == ME
    assert "live" not in data


def test_standings_past_gw_without_snapshot_stays_empty(db):
    """?gw=N for a non-current GW with no snapshot keeps the legacy empty
    response (the live overlay only applies to the current GW)."""
    _seed_league(db, current_gw=3)
    _seed_live_scores(db, 3, {ME: 12})
    status, data = _get_standings(db, query={"gw": "1"})
    assert status == 200
    assert data["managers"] == [] and "live" not in data


# ---------------------------------------------------------------------------
# gw-history — live fallback + pre-lock privacy
# ---------------------------------------------------------------------------

def _get_history(db, uid, gw):
    return _call(db, f"/leagues/{LID}/gw-history/{uid}",
                 api_wc.get_gw_history, LID, uid, query={"gw": str(gw)})


def _lock(monkeypatch, locked):
    monkeypatch.setattr(api_wc, "is_lineup_locked",
                        lambda _db, _gw, now=None: locked)


def test_gw_history_existing_snapshot_unchanged(db, monkeypatch):
    _lock(monkeypatch, True)
    snap = {"uid": "u_a", "gw": 1, "players": [{"id": 11, "points": 7, "stats": {}}],
            "starting": [11], "bench": [], "autoSubs": [],
            "totalPoints": 7, "opponent": ME, "opponentPoints": 3, "result": "W"}
    db.store[f"leagues/{LID}/gw_history/u_a_1"] = snap

    status, data = _get_history(db, "u_a", 1)
    assert status == 200
    assert "live" not in data
    assert data["totalPoints"] == 7 and data["result"] == "W"


def test_gw_history_prelock_other_uid_403(db, monkeypatch):
    _lock(monkeypatch, False)
    api_wc.init_wc(db)
    app = flask.Flask(__name__)
    with app.test_request_context(f"/leagues/{LID}/gw-history/u_a",
                                  query_string={"gw": "1"}):
        resp, status = api_wc.get_gw_history(LID, "u_a")
        body = resp.get_json()
    assert status == 403
    assert "hidden until they lock" in body["error"]


def test_gw_history_prelock_own_uid_404(db, monkeypatch):
    """Your own missing snapshot pre-lock stays a 404 (the client falls back
    to the current-squad list)."""
    _lock(monkeypatch, False)
    status, _ = _call(db, f"/leagues/{LID}/gw-history/{ME}",
                      api_wc.get_gw_history, LID, ME, query={"gw": "1"})
    assert status == 404


def test_gw_history_locked_composes_live_snapshot(db, monkeypatch):
    _lock(monkeypatch, True)
    db.store[f"leagues/{LID}/lineups/u_a_1"] = {
        "starting": [11, 12], "bench": [13],
        "captain": 11, "viceCaptain": 12, "locked": True,
    }
    _seed_player_scores(db, 1, {11: 6, 12: 2, 13: 1})

    status, data = _get_history(db, "u_a", 1)
    assert status == 200
    assert data["live"] is True
    assert data["starting"] == [11, 12] and data["bench"] == [13]
    assert data["players"] == [
        {"id": 11, "points": 6, "stats": {"minutes": 90}},
        {"id": 12, "points": 2, "stats": {"minutes": 90}},
        {"id": 13, "points": 1, "stats": {"minutes": 90}},
    ]
    # Total = starters (6+2) + captain doubled (6); bench excluded.
    assert data["totalPoints"] == 14
    # Pre-finalize: no auto-subs / H2H result yet.
    assert data["autoSubs"] == []
    assert data["result"] is None and data["opponent"] is None


def test_gw_history_locked_no_lineup_404(db, monkeypatch):
    _lock(monkeypatch, True)
    status, _ = _call(db, f"/leagues/{LID}/gw-history/u_a",
                      api_wc.get_gw_history, LID, "u_a", query={"gw": "1"})
    assert status == 404


def test_gw_history_locked_player_without_scores_zero(db, monkeypatch):
    """A starter with no playerScores doc yet (match not started) shows 0."""
    _lock(monkeypatch, True)
    db.store[f"leagues/{LID}/lineups/{ME}_1"] = {
        "starting": [21, 22], "bench": [], "captain": 22, "locked": True,
    }
    _seed_player_scores(db, 1, {21: 5})

    status, data = _get_history(db, ME, 1)
    assert status == 200
    by_id = {p["id"]: p for p in data["players"]}
    assert by_id[22]["points"] == 0 and by_id[22]["stats"] == {}
    # Captain (22) doubled on 0 is still 0 → total is just 21's 5.
    assert data["totalPoints"] == 5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
