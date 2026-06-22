"""Scouting-bonus headroom cap: FIFA's discretionary +2 is excluded ONLY to the
extent FIFA's round total exceeds what our itemized stats already explain.
Regression for the Salah GW2 undercount (goal+assist game where the bonus was
never awarded but we subtracted it anyway)."""
from fpl_predictor.data.wc_live_ingest import fifa_breakdown, _excluded_pts


def _total(bd):  # league total = sum of non-excluded lines
    return sum((b.get("pts") or 0) for b in bd if not b.get("excluded"))


def test_no_phantom_bonus_when_stats_explain_total():
    # Salah GW2: MID, 84', 1 goal (+6), 1 assist (+3) -> itemized 11 == FIFA 11.
    # 4.9% owned (eligible) but NO headroom -> exclude 0 -> league total 11.
    bd = fifa_breakdown({"minutes": 84, "goals": 1, "assists": 1},
                        position=3, fifa_total=11, percent_selected=4.9,
                        fifa_position=3)
    assert _excluded_pts(bd) == 0, bd
    assert _total(bd) == 11, bd
    assert not any(b["label"] == "FIFA adjustment" for b in bd), bd


def test_genuine_bonus_still_excluded():
    # Eligible player whose FIFA total exceeds itemized by >=2 -> the +2 has
    # headroom to live in, so it's still excluded (league total = total - 2).
    bd = fifa_breakdown({"minutes": 75},  # itemized 2; FIFA total 9 -> headroom 7
                        position=3, fifa_total=9, percent_selected=1.0,
                        fifa_position=3)
    assert _excluded_pts(bd) == 2, bd
    assert _total(bd) == 7, bd


def test_partial_headroom_caps_exclusion():
    # Only 1 unexplained point -> exclude at most 1 (not a full phantom 2).
    bd = fifa_breakdown({"minutes": 84, "goals": 1},  # itemized 2+6=8; FIFA 9
                        position=3, fifa_total=9, percent_selected=2.0,
                        fifa_position=3)
    assert _excluded_pts(bd) == 1, bd
    assert _total(bd) == 8, bd


def test_not_eligible_when_owned_5pct_or_more():
    bd = fifa_breakdown({"minutes": 75}, position=3, fifa_total=9,
                        percent_selected=5.1, fifa_position=3)
    assert _excluded_pts(bd) == 0, bd


if __name__ == "__main__":
    test_no_phantom_bonus_when_stats_explain_total()
    test_genuine_bonus_still_excluded()
    test_partial_headroom_caps_exclusion()
    test_not_eligible_when_owned_5pct_or_more()
    print("ok: scouting headroom-cap tests pass")
