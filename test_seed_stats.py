"""
EP3 tests: the synthetic seed stat shape must mirror what api-sports returns
and must make the new scoring rules (DefCon + rating bonus + 60' threshold)
observable.

The seed's synthetic stat builder was extracted to the module-level
`build_team_raw_stats(team_id, players_list, events, conceded_map)` helper so it
can be exercised directly here without Firestore. It takes a list of player
dicts (keys: id, name, position, teamIso) and the match's goal/assist events,
returning the api-sports {"team": ..., "players": [...]} shape.
"""
import importlib

seed_league = importlib.import_module("fpl_predictor.seed.seed_league")
from fpl_predictor.game.wc_scoring import compute_player_points, compute_rating_bonus


def _sample_players():
    """A representative drafted-team roster: GK, several DEF/MID, FWDs."""
    return [
        {"id": 1001, "name": "GK One",   "position": 1, "teamIso": "POR"},
        {"id": 1002, "name": "Def Two",  "position": 2, "teamIso": "POR"},
        {"id": 1003, "name": "Def Three","position": 2, "teamIso": "POR"},
        {"id": 1004, "name": "Mid Four", "position": 3, "teamIso": "POR"},
        {"id": 1005, "name": "Mid Five", "position": 3, "teamIso": "POR"},
        {"id": 1006, "name": "Fwd Six",  "position": 4, "teamIso": "POR"},
        {"id": 1007, "name": "Fwd Seven","position": 4, "teamIso": "POR"},
    ]


def _build(players, events=None):
    """Invoke the module-level synthetic stat builder."""
    events = events or []
    return seed_league.build_team_raw_stats(team_id=1, players_list=players,
                                            events=events, conceded_map={})


def _stat_line(team_raw, pid):
    for entry in team_raw["players"]:
        if entry["player"]["id"] == pid:
            return entry["statistics"][0]
    raise AssertionError(f"player {pid} not present")


def test_no_injected_bps_has_tackles_rating():
    players = _sample_players()
    team_raw = _build(players)

    minutes_seen = set()
    for entry in team_raw["players"]:
        stat = entry["statistics"][0]
        pid = entry["player"]["id"]
        pos = next(p["position"] for p in players if p["id"] == pid)

        # No dead injected bonus input anywhere.
        assert "bps" not in stat, f"bps must not be emitted (player {pid})"

        games = stat["games"]
        minutes_seen.add(games["minutes"])
        assert "rating" in games

        # Outfield players carry the full DefCon tackle shape.
        if pos in (2, 3) and games["minutes"] > 0:
            tk = stat["tackles"]
            assert set(tk) == {"total", "interceptions", "blocks"}

    # Minutes must vary — not all 90 — so the 60' threshold is exercised.
    assert minutes_seen != {90}
    assert len(minutes_seen) > 1
    assert 0 in minutes_seen  # the minutes==0 => 0 path is reachable


def test_seed_exercises_defcon_and_bonus():
    players = _sample_players()
    team_raw = _build(players)

    pos_map = {p["id"]: p["position"] for p in players}

    # --- DefCon: at least one DEF and one MID must earn the +2 award ---
    def base_with_defcon(pid):
        stat = _stat_line(team_raw, pid)
        flat = {
            "minutes": stat["games"]["minutes"],
            "goals": stat["goals"]["total"],
            "assists": stat["goals"]["assists"],
            "tackles": stat["tackles"],
        }
        with_def, _ = compute_player_points(flat, pos_map[pid])
        flat_no_def = dict(flat, tackles={"total": 0, "interceptions": 0, "blocks": 0})
        without_def, _ = compute_player_points(flat_no_def, pos_map[pid])
        return with_def - without_def

    def_awarded = [pid for pid in pos_map if pos_map[pid] == 2 and base_with_defcon(pid) == 2]
    mid_awarded = [pid for pid in pos_map if pos_map[pid] == 3 and base_with_defcon(pid) == 2]
    assert def_awarded, "at least one DEF must receive the +2 DefCon award"
    assert mid_awarded, "at least one MID must receive the +2 DefCon award"

    # --- Rating bonus: a clean 3/2/1 distribution over the fixture ratings ---
    rating_list = []
    for entry in team_raw["players"]:
        stat = entry["statistics"][0]
        minutes = stat["games"]["minutes"]
        rating = stat["games"]["rating"]
        if rating and minutes > 0:
            rating_list.append((entry["player"]["id"], float(rating)))

    bonuses = compute_rating_bonus(rating_list)
    assert sorted(bonuses.values(), reverse=True) == [3, 2, 1]
