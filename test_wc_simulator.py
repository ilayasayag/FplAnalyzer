"""Tests for the WC 2026 random tournament simulator.

Two layers, matching the module:
  * PURE generation — deterministic given a seeded RNG, no Firestore.
  * DB DRIVER — drives the REAL scoring engine over a FakeDB and asserts the
    simulator's output reconciles with engine rules (manager GW points == sum of
    fielded starters, standings ranked, knockout eliminations applied).
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_helpers as H  # noqa: E402
from fpl_predictor.seed import wc_simulator as S  # noqa: E402

GK, DEF, MID, FWD = 1, 2, 3, 4


# ---------------------------------------------------------------------------
# PURE: scoreline
# ---------------------------------------------------------------------------
def test_knockout_scoreline_never_draws():
    rng = random.Random(1)
    for _ in range(500):
        h, a = S.simulate_scoreline(rng, knockout=True)
        assert h != a


def test_group_scoreline_can_draw_and_is_bounded():
    rng = random.Random(2)
    saw_draw = False
    for _ in range(500):
        h, a = S.simulate_scoreline(rng, knockout=False)
        assert 0 <= h <= 5 and 0 <= a <= 5
        saw_draw = saw_draw or (h == a)
    assert saw_draw, "group games should sometimes draw"


# ---------------------------------------------------------------------------
# PURE: per-team player stats
# ---------------------------------------------------------------------------
def _team(prefix, n_per_pos=(2, 5, 5, 4)):
    """Build a team roster: n GK/DEF/MID/FWD."""
    players, pid = [], prefix
    for pos, n in zip((GK, DEF, MID, FWD), n_per_pos):
        for _ in range(n):
            players.append({"id": pid, "name": f"P{pid}", "position": pos})
            pid += 1
    return players


def test_goals_reconcile_with_scoreline():
    rng = random.Random(3)
    players = _team(1000)
    for goals_for in range(0, 6):
        rows = S.simulate_team_player_stats(players, goals_for, rng)
        total = sum(r["statistics"][0]["goals"]["total"] for r in rows)
        assert total == goals_for, f"scorers must sum to scoreline ({goals_for})"


def test_assists_never_exceed_goals_and_benched_players_are_blank():
    rng = random.Random(4)
    players = _team(2000)
    rows = S.simulate_team_player_stats(players, 4, rng)
    total_assists = sum(r["statistics"][0]["goals"]["assists"] for r in rows)
    total_goals = sum(r["statistics"][0]["goals"]["total"] for r in rows)
    assert total_assists <= total_goals
    # Any player with 0 minutes scored/assisted nothing and has a 0 rating.
    for r in rows:
        st = r["statistics"][0]
        if st["games"]["minutes"] == 0:
            assert st["goals"]["total"] == 0
            assert st["goals"]["assists"] == 0
            assert st["games"]["rating"] == 0.0


def test_defcon_weighted_to_def_and_mid():
    """DEF/MID should clear their DefCon threshold far more often than FWD/GK."""
    rng = random.Random(5)
    threshold = {GK: 99, DEF: 10, MID: 12, FWD: 99}
    clears = {GK: 0, DEF: 0, MID: 0, FWD: 0}
    trials = 4000
    for _ in range(trials):
        for pos in (GK, DEF, MID, FWD):
            t = S._roll_defcon(pos, 90, rng)
            if t["total"] + t["interceptions"] + t["blocks"] >= threshold[pos]:
                clears[pos] += 1
    # DEF and MID clear meaningfully often; FWD/GK essentially never.
    assert clears[DEF] > trials * 0.35
    assert clears[MID] > trials * 0.25
    assert clears[FWD] == 0
    assert clears[GK] == 0


def test_scorers_skew_to_attackers():
    """Across many matches, forwards+mids should score the lion's share."""
    rng = random.Random(6)
    players = _team(3000)
    pos_by_id = {p["id"]: p["position"] for p in players}
    goals_by_pos = {GK: 0, DEF: 0, MID: 0, FWD: 0}
    for _ in range(300):
        rows = S.simulate_team_player_stats(players, 3, rng)
        for r in rows:
            g = r["statistics"][0]["goals"]["total"]
            goals_by_pos[pos_by_id[r["player"]["id"]]] += g
    attacking = goals_by_pos[MID] + goals_by_pos[FWD]
    defending = goals_by_pos[GK] + goals_by_pos[DEF]
    assert attacking > defending * 2


# ---------------------------------------------------------------------------
# PURE: schedule helpers
# ---------------------------------------------------------------------------
def test_round_robin_group_of_four():
    rounds = S.round_robin([10, 20, 30, 40])
    assert len(rounds) == 3
    assert all(len(r) == 2 for r in rounds)
    # Every team plays every other exactly once.
    seen = set()
    for r in rounds:
        for h, a in r:
            seen.add(frozenset((h, a)))
    assert len(seen) == 6  # C(4,2)


def test_knockout_pairs_halves_field():
    rng = random.Random(7)
    pairs = S.knockout_pairs(list(range(32)), rng)
    assert len(pairs) == 16
    flat = [t for pr in pairs for t in pr]
    assert len(set(flat)) == 32  # no team appears twice


# ---------------------------------------------------------------------------
# DB DRIVER — integration against the real engine over FakeDB
# ---------------------------------------------------------------------------
def _seed_mini_league(db, lid="L1"):
    """Two national teams (10, 20), 16 players each, in the same group; two
    managers whose 15-man squads are drawn entirely from one team each, so
    fixture 10-v-20 maps cleanly onto manager-A-vs-manager-B."""
    # Teams
    for tid, iso, name in [(10, "AAA", "Team A"), (20, "BBB", "Team B")]:
        db.collection("wc_teams").document(str(tid)).set({
            "id": tid, "isoCode": iso, "name": name, "group": "A",
            "eliminated": False,
        })
    # Players (2 GK, 5 DEF, 5 MID, 4 FWD per team)
    rosters = {}
    for tid in (10, 20):
        roster = []
        pid = tid * 100
        for pos, n in zip((GK, DEF, MID, FWD), (2, 5, 5, 4)):
            for _ in range(n):
                p = {"id": pid, "name": f"P{pid}", "position": pos,
                     "positionName": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[pos],
                     "teamId": tid, "teamName": f"Team {tid}", "teamIso": "",
                     "totalPoints": 0, "eliminated": False}
                db.collection("wc_players").document(str(pid)).set(p)
                roster.append(p)
                pid += 1
        rosters[tid] = roster

    # League + members + squads (squad = 2GK,5DEF,5MID,3FWD from one team)
    db.collection("leagues").document(lid).set({
        "leagueId": lid, "currentGw": 1, "status": "group_phase",
        "leaguePhaseGws": [1, 2, 3], "knockoutStartGw": 4,
        "knockoutQualifiers": 2,
    })
    members = {"u_a": 10, "u_b": 20}
    for uid, tid in members.items():
        db.collection("leagues").document(lid).collection("members").document(uid).set({
            "displayName": uid, "teamName": f"{uid} FC",
        })
        squad = []
        roster = rosters[tid]
        take = {GK: 2, DEF: 5, MID: 5, FWD: 3}
        for pos in (GK, DEF, MID, FWD):
            for p in [r for r in roster if r["position"] == pos][:take[pos]]:
                squad.append({
                    "playerId": p["id"], "position": pos, "name": p["name"],
                    "positionName": p["positionName"], "teamIso": "",
                    "eliminated": False, "teamId": tid, "teamName": p["teamName"],
                    "draftedRound": 1,
                })
        db.collection("leagues").document(lid).collection("squads").document(uid).set(
            {"players": squad})

    # H2H schedule for GW1
    db.collection("leagues").document(lid).collection("schedule").document("1").set({
        "gw": 1, "matches": [{"home": "u_a", "away": "u_b"}],
    })
    return lid


def test_simulate_group_gw_reconciles_with_engine():
    db = H.FakeDB()
    lid = _seed_mini_league(db)
    teams = S._load_teams(db)
    players_by_team = S._load_players_by_team(db)
    pos_map, rules = S._pos_map_and_rules(db)
    schedule = S.build_group_schedule(teams)
    assert schedule[1] and not schedule[2] and not schedule[3]

    res = S.simulate_gw(db, lid, 1, random.Random(42), teams=teams,
                        players_by_team=players_by_team, pos_map=pos_map,
                        rules=rules, wc_client=None, group_schedule=schedule)
    assert res["knockout"] is False
    assert res["matches"] == 1

    # Fixture processed
    fixtures = db.collection("wc_fixtures").get()
    assert len(fixtures) == 1
    assert fixtures[0].to_dict()["processedForFantasy"] is True

    # Scores exist for both managers
    scores = db.collection("leagues").document(lid).collection("scores").document("1").get()
    results = scores.to_dict()["results"]
    assert set(results) == {"u_a", "u_b"}

    # Manager GW points == sum of their fielded starters' fantasy points
    # (captain bonus is disabled, so the totals must match exactly).
    fid = fixtures[0].id
    pscores = {int(p.id): p.to_dict().get("fantasyPoints", 0)
               for p in db.collection("wc_fixtures").document(fid)
               .collection("playerScores").get()}
    for uid in ("u_a", "u_b"):
        lineup = db.collection("leagues").document(lid).collection("lineups") \
            .document(f"{uid}_1").get().to_dict()
        expected = sum(pscores.get(pid, 0) for pid in lineup["starting"])
        assert results[uid]["points"] == expected

    # Standings ranked 1..2
    standings = db.collection("leagues").document(lid).collection("standings") \
        .document("current").get().to_dict()
    ranks = sorted(m["rank"] for m in standings["managers"])
    assert ranks == [1, 2]


class _StubWCClient:
    """Minimal wc_client for the knockout path: only mark_knockout_elimination
    is exercised by simulate_gw's knockout branch."""
    def mark_knockout_elimination(self, team_id, gw, db=None):
        db.collection("wc_teams").document(str(team_id)).update(
            {"eliminated": True, "eliminatedAfterGw": gw, "status": "eliminated"})


def test_simulate_knockout_gw_eliminates_losers():
    db = H.FakeDB()
    lid = _seed_mini_league(db)
    # Push knockout start out of the way so finalize treats GW4 as a plain,
    # non-bracket GW (isolates the WC-team knockout/elimination logic).
    db.collection("leagues").document(lid).update({"knockoutStartGw": 99})

    teams = S._load_teams(db)
    players_by_team = S._load_players_by_team(db)
    pos_map, rules = S._pos_map_and_rules(db)

    # No group_schedule for GW4 -> knockout branch. Two teams -> one tie.
    res = S.simulate_gw(db, lid, 4, random.Random(99), teams=teams,
                        players_by_team=players_by_team, pos_map=pos_map,
                        rules=rules, wc_client=_StubWCClient(),
                        group_schedule={1: [], 2: [], 3: []})
    assert res["knockout"] is True
    assert res["matches"] == 1
    assert len(res["eliminated"]) == 1

    loser = res["eliminated"][0]
    # Losing team marked eliminated
    assert db.collection("wc_teams").document(str(loser)).get().to_dict()["eliminated"] is True
    # Its players marked eliminated too
    loser_players = [p for p in db.collection("wc_players").get()
                     if p.to_dict()["teamId"] == loser]
    assert loser_players and all(p.to_dict()["eliminated"] for p in loser_players)


def test_process_fixture_cache_matches_uncached():
    """The new pos_map/rules cache params must produce identical scoring to the
    DB-read path."""
    from fpl_predictor.game.wc_scoring import process_fixture
    # Build two identical seeded DBs.
    db1 = H.build_seeded_db()
    db2 = H.build_seeded_db()
    raw = H._fixture_a_raw()
    fid = 9001  # fixture A present in build_seeded_db (team 10 beats 20, 2-0)
    out_uncached = process_fixture(fid, raw, None, db1)
    pos_map = {int(d.id): (d.to_dict() or {}).get("position", 3)
               for d in db2.collection("wc_players").get()}
    cfg = db2.collection("wc_config").document("tournament").get()
    rules = (cfg.to_dict() or {}).get("rules", {}) if cfg.exists else {}
    out_cached = process_fixture(fid, raw, None, db2, pos_map=pos_map, rules=rules)
    assert {pid: v["fantasyPoints"] for pid, v in out_cached.items()} == \
           {pid: v["fantasyPoints"] for pid, v in out_uncached.items()}


# ---------------------------------------------------------------------------
# FULL TOURNAMENT — 12 groups of 4, GW1-8 start to finish, real engine + the
# real WC2026Client driving group-stage + knockout eliminations.
# ---------------------------------------------------------------------------
def _seed_full_tournament(db, lid="LFULL"):
    """Seed a complete WC field: 48 teams in 12 groups (A-L) of 4, each with a
    16-man roster (2GK/5DEF/5MID/4FWD), plus two managers whose 15-man squads
    are drawn from the first two teams of group A. Returns the league id.

    This is the substrate for the full start-to-finish simulation: the engine's
    detect_group_stage_eliminations needs all 12 groups present (it eliminates
    the 12 group-fourths + the 4 worst thirds = 16, leaving exactly 32), and the
    simulator's knockout branch halves that field across GW4-8."""
    groups = [chr(ord("A") + i) for i in range(12)]  # A..L
    rosters = {}
    team_id = 0
    for grp in groups:
        for _ in range(4):
            team_id += 1
            tid = team_id
            iso = f"T{tid:02d}"
            db.collection("wc_teams").document(str(tid)).set({
                "id": tid, "isoCode": iso, "name": f"Team {tid}",
                "group": grp, "eliminated": False, "status": "active",
            })
            roster = []
            pid = tid * 100
            for pos, n in zip((GK, DEF, MID, FWD), (2, 5, 5, 4)):
                for _ in range(n):
                    p = {"id": pid, "name": f"P{pid}", "position": pos,
                         "positionName": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[pos],
                         "teamId": tid, "teamName": f"Team {tid}", "teamIso": iso,
                         "totalPoints": 0, "eliminated": False}
                    db.collection("wc_players").document(str(pid)).set(p)
                    roster.append(p)
                    pid += 1
            rosters[tid] = roster

    # League: GW1-3 league phase, knockout from GW4 (aligns with the WC field's
    # group->knockout transition the engine drives at GW3 finalize).
    db.collection("leagues").document(lid).set({
        "leagueId": lid, "currentGw": 1, "status": "group_phase",
        "leaguePhaseGws": [1, 2, 3], "knockoutStartGw": 4,
        "knockoutQualifiers": 2,
    })
    members = {"u_a": 1, "u_b": 2}  # both in group A
    for uid, tid in members.items():
        db.collection("leagues").document(lid).collection("members").document(uid).set(
            {"displayName": uid, "teamName": f"{uid} FC", "draftPosition": tid})
        roster = rosters[tid]
        take = {GK: 2, DEF: 5, MID: 5, FWD: 3}  # 15-man squad
        squad = []
        for pos in (GK, DEF, MID, FWD):
            for p in [r for r in roster if r["position"] == pos][:take[pos]]:
                squad.append({
                    "playerId": p["id"], "position": pos, "name": p["name"],
                    "positionName": p["positionName"], "teamIso": p["teamIso"],
                    "eliminated": False, "teamId": tid, "teamName": p["teamName"],
                    "draftedRound": 1,
                })
        db.collection("leagues").document(lid).collection("squads").document(uid).set(
            {"players": squad})

    # H2H schedule for the league-phase GWs (u_a vs u_b each matchday).
    for gw in (1, 2, 3):
        db.collection("leagues").document(lid).collection("schedule").document(str(gw)).set(
            {"gw": gw, "matches": [{"home": "u_a", "away": "u_b"}]})
    return lid


def test_simulate_full_tournament_start_to_finish():
    """End-to-end: drive the entire World Cup (GW1-8) through the real engine and
    the real WC2026Client, asserting the field narrows correctly at every stage."""
    from fpl_predictor.data.wc_api import WC2026Client

    db = H.FakeDB()
    lid = _seed_full_tournament(db)
    client = WC2026Client(db=db)

    result = S.simulate_tournament(db, lid, seed=2026, start_gw=1, end_gw=8,
                                   reset=False, wc_client=client)

    per_gw = {r["gw"]: r for r in result["gws"]}

    # Group stage: 12 groups x 6 round-robin games = 72 fixtures over GW1-3
    # (24 per matchday), none knockout.
    for gw in (1, 2, 3):
        assert per_gw[gw]["knockout"] is False
        assert per_gw[gw]["matches"] == 24

    # At GW3 finalize the engine eliminates exactly 16 teams (12 group-fourths +
    # the 4 worst thirds), stamping eliminatedAfterGw=3. That leaves 32 teams to
    # enter the knockout — which GW4's 16 matches independently confirms.
    group_eliminated = [t for t in db.collection("wc_teams").get()
                        if t.to_dict().get("eliminatedAfterGw") == 3]
    assert len(group_eliminated) == 16

    # Knockout rounds halve the field each GW: 32->16->8->4->2->1.
    assert per_gw[4]["knockout"] is True and per_gw[4]["matches"] == 16
    assert per_gw[5]["matches"] == 8
    assert per_gw[6]["matches"] == 4
    assert per_gw[7]["matches"] == 2
    assert per_gw[8]["matches"] == 1

    # One champion: exactly 47 of 48 teams eliminated after the final.
    eliminated = [t for t in db.collection("wc_teams").get()
                  if t.to_dict().get("eliminated")]
    assert len(eliminated) == 47

    # Each knockout GW eliminated exactly the losers (sums to 16+8+4+2+1 = 31).
    ko_eliminated = sum(len(per_gw[gw]["eliminated"]) for gw in (4, 5, 6, 7, 8))
    assert ko_eliminated == 31

    # Export is navigable: both managers carry per-GW points for all 8 GWs.
    export = result["export"]
    assert set(export["managers"]) == {"u_a", "u_b"}
    for uid in ("u_a", "u_b"):
        gw_points = export["managers"][uid]["gwPoints"]
        assert set(gw_points) >= {str(gw) for gw in range(1, 9)}
    # Every GW has a recorded winner (highest fantasy scorer that GW).
    assert all(export["gws"][str(gw)]["winner"] for gw in range(1, 9))
