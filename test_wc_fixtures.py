"""GAP-301 — per-team fixtures iso resolution.

Stored WC fixtures carry team ids but an empty isoCode (see
WC2026Client.sync_fixtures). The /fixtures endpoint resolves the iso from the
team map so the client can key fixtures by the same iso it uses for players.
These tests pin the pure resolution helpers (no Flask client / db needed).
"""

from fpl_predictor.api_wc import _team_display_iso, _enrich_fixtures_with_iso


def test_team_display_iso_prefers_isocode():
    assert _team_display_iso({"id": 10, "isoCode": "esp", "name": "Spain"}) == "ESP"


def test_team_display_iso_falls_back_to_short_name_then_id():
    assert _team_display_iso({"id": 10, "isoCode": "", "short_name": "ger"}) == "GER"
    assert _team_display_iso({"id": 42, "isoCode": "", "short_name": ""}) == "42"
    assert _team_display_iso({}) == ""
    assert _team_display_iso(None) == ""


def test_enrich_fills_empty_isocode_from_team_map():
    team_map = {
        1: {"id": 1, "isoCode": "ESP", "name": "Spain"},
        2: {"id": 2, "isoCode": "JPN", "name": "Japan"},
    }
    fixtures = [{
        "id": 900, "gw": 4,
        "homeTeam": {"id": 1, "isoCode": "", "name": "Spain"},
        "awayTeam": {"id": 2, "isoCode": "", "name": "Japan"},
    }]
    out = _enrich_fixtures_with_iso(fixtures, team_map)
    assert out[0]["homeTeam"]["isoCode"] == "ESP"
    assert out[0]["awayTeam"]["isoCode"] == "JPN"


def test_enrich_falls_back_to_id_when_team_missing_iso():
    # Team exists but its own isoCode is also empty → use the numeric id.
    team_map = {7: {"id": 7, "isoCode": "", "short_name": ""}}
    fixtures = [{
        "homeTeam": {"id": 7, "isoCode": ""},
        "awayTeam": {"id": 99, "isoCode": ""},  # not in map → left empty
    }]
    out = _enrich_fixtures_with_iso(fixtures, team_map)
    assert out[0]["homeTeam"]["isoCode"] == "7"
    assert out[0]["awayTeam"]["isoCode"] == ""


def test_enrich_preserves_existing_isocode():
    # Mock-seed fixtures already carry isoCode; don't clobber them.
    fixtures = [{
        "homeTeam": {"id": 1, "isoCode": "BRA"},
        "awayTeam": {"id": 2, "isoCode": "USA"},
    }]
    out = _enrich_fixtures_with_iso(fixtures, {1: {"id": 1, "isoCode": "XXX"}})
    assert out[0]["homeTeam"]["isoCode"] == "BRA"
    assert out[0]["awayTeam"]["isoCode"] == "USA"


def test_enrich_tolerates_missing_team_blocks():
    fixtures = [{"id": 1, "gw": 4}, {"homeTeam": None, "awayTeam": "x"}]
    # Should not raise.
    assert _enrich_fixtures_with_iso(fixtures, {}) is fixtures
    assert _enrich_fixtures_with_iso(None, {}) is None
