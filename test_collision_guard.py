"""Same-name collision guard: two distinct FIFA players sharing a normalized
name on one nation must not clobber the FIFA points/position of the player we
actually drafted. Regression for the GW2 Danilo (DEF/MID) and Ederson
(GK / Éderson MID) bugs."""
from fpl_predictor.data.wc_live_ingest import (
    _resolve_fifa_by_pid, build_pool_index,
)


class _FakeDoc:
    def __init__(self, _id, data):
        self.id = _id
        self._data = data

    def to_dict(self):
        return self._data


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


class _FakeDB:
    def __init__(self, players):
        self._players = players

    def collection(self, name):
        assert name == "wc_players"
        return _FakeColl([_FakeDoc(str(i), p) for i, p in self._players.items()])


# Our pool: ONE Danilo (DEF) and ONE Ederson (GK) — exactly what prod has.
POOL_DB = _FakeDB({
    900214: {"name": "Danilo", "teamIso": "BRA", "position": 2},
    900210: {"name": "Ederson", "teamIso": "BRA", "position": 1},
})

# FIFA feed lists TWO Danilos and an Ederson + an accent-twin Éderson on Brazil.
FIFA = [
    {"name": "Danilo", "iso": "BRA", "position": "DEF", "seasonTotal": 10,
     "roundPoints": {"1": 1, "2": 9}},
    {"name": "Danilo", "iso": "BRA", "position": "MID", "seasonTotal": 2,
     "roundPoints": {"1": 1, "2": 1}},
    {"name": "Ederson", "iso": "BRA", "position": "GK", "seasonTotal": 0,
     "roundPoints": {}},
    {"name": "Éderson", "iso": "BRA", "position": "MID", "seasonTotal": 1,
     "roundPoints": {"2": 1}},
]


def test_fifa_picks_position_matched_twin():
    pool = build_pool_index(POOL_DB)
    pts, pos, season = _resolve_fifa_by_pid(FIFA, pool, gw=2)
    # Danilo -> the DEF row (9 pts, DEF pos, season 10), NOT the MID's 1.
    assert pts[900214] == 9, pts
    assert pos[900214] == 2, pos
    assert season[900214] == 10
    # Ederson -> the GK row, which has no GW2 points -> absent from fifa_pts
    # (so the ingest write loop won't score him off the MID twin's 1).
    assert 900210 not in pts, pts
    assert pos[900210] == 1


def test_no_regression_for_single_match():
    # A normal, non-colliding player still resolves exactly as before.
    db = _FakeDB({900999: {"name": "Vinicius", "teamIso": "BRA", "position": 3}})
    fifa = [{"name": "Vinicius", "iso": "BRA", "position": "MID",
             "seasonTotal": 7, "roundPoints": {"2": 5}}]
    pts, pos, season = _resolve_fifa_by_pid(fifa, build_pool_index(db), gw=2)
    assert pts[900999] == 5 and pos[900999] == 3 and season[900999] == 7


if __name__ == "__main__":
    test_fifa_picks_position_matched_twin()
    test_no_regression_for_single_match()
    print("ok: collision guard tests pass")
