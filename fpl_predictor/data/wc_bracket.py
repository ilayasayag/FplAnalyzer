"""WC2026 tournament knockout bracket (national teams) — self-updating.

Scans the ESPN scoreboard for the knockout rounds (round identified by each
event's ``season.slug``), ingests/refreshes the fixtures per round, determines
winners (penalties handled via ESPN's ``competitor.winner`` flag), and writes a
single ``wc_config/wc_bracket`` doc the frontend renders. Idempotent — safe to
run on every daily scan; new rounds appear automatically as ESPN schedules them.
"""
from __future__ import annotations

import json
import urllib.request
import datetime
from datetime import timezone, timedelta
from typing import Dict, List, Optional

from fpl_predictor.data.wc_live_ingest import _norm_iso, _UA

ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}"

# espn season.slug -> (fantasy gw, display name, fixture-id base)
_ROUND_META = {
    "round-of-32":   (4, "Round of 32",   400),
    "round-of-16":   (5, "Round of 16",   500),
    "quarterfinals": (6, "Quarter-Final", 600),
    "semifinals":    (7, "Semi-Final",    700),
    "final":         (8, "Final",         800),
}
_ROUND_ORDER = ["round-of-32", "round-of-16", "quarterfinals", "semifinals", "final"]


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _winner_iso(home: dict, away: dict, hi: str, ai: str, completed: bool) -> Optional[str]:
    if not completed:
        return None
    if home.get("winner"):
        return hi
    if away.get("winner"):
        return ai
    hs, as_ = home.get("score"), away.get("score")
    if hs is not None and as_ is not None and int(hs) != int(as_):
        return hi if int(hs) > int(as_) else ai
    return None


def scan_and_build_bracket(db, days_back: int = 4, days_ahead: int = 16,
                           today: Optional[datetime.date] = None) -> dict:
    """Fetch ESPN across the knockout window, build the bracket doc + upsert the
    per-round fixtures. Returns a summary."""
    today = today or datetime.datetime.now(timezone.utc).date()
    valid_isos = {(d.to_dict() or {}).get("isoCode", "").upper()
                  for d in db.collection("wc_teams").stream()}

    # collect events per round across the date window
    by_round: Dict[str, list] = {}
    for i in range(-days_back, days_ahead + 1):
        date = (today + timedelta(days=i)).strftime("%Y%m%d")
        try:
            data = _get(ESPN_SB.format(date=date))
        except Exception:
            continue
        for ev in data.get("events", []):
            slug = (ev.get("season") or {}).get("slug")
            if slug in _ROUND_META:
                by_round.setdefault(slug, {})[ev.get("id")] = ev  # dedupe by event id

    bracket = {"rounds": {}, "qualified": {},
               "updatedAt": datetime.datetime.now(timezone.utc)}
    fixture_upserts: List[tuple] = []

    for slug in _ROUND_ORDER:
        evs = list((by_round.get(slug) or {}).values())
        if not evs:
            continue
        gw, disp, base = _ROUND_META[slug]
        evs.sort(key=lambda e: e.get("date") or "")
        matches, advanced = [], []
        for idx, ev in enumerate(evs, 1):
            comp = (ev.get("competitions") or [{}])[0]
            cs = comp.get("competitors") or []
            home = next((c for c in cs if c.get("homeAway") == "home"), {})
            away = next((c for c in cs if c.get("homeAway") == "away"), {})
            # Real iso once the team is decided; None + a placeholder label otherwise.
            hi = _norm_iso(home.get("team", {}).get("abbreviation") or "")
            ai = _norm_iso(away.get("team", {}).get("abbreviation") or "")
            h_real, a_real = hi in valid_isos, ai in valid_isos
            h_name = hi if h_real else (home.get("team", {}).get("displayName") or "TBD")
            a_name = ai if a_real else (away.get("team", {}).get("displayName") or "TBD")
            stype = (ev.get("status") or {}).get("type", {}) or {}
            completed = bool(stype.get("completed"))
            in_play = stype.get("state") == "in"
            hs, as_ = home.get("score"), away.get("score")
            winner = _winner_iso(home, away, hi if h_real else None, ai if a_real else None, completed)
            decided = None
            if completed and winner and hs is not None and as_ is not None and int(hs) == int(as_):
                decided = "penalties"
            if winner:
                advanced.append(winner)
            fid = base + idx
            matches.append({
                "id": fid, "round": disp, "gw": gw,
                "home": hi if h_real else None, "homeName": h_name,
                "away": ai if a_real else None, "awayName": a_name,
                "homeScore": int(hs) if hs is not None else None,
                "awayScore": int(as_) if as_ is not None else None,
                "status": "FT" if completed else ("LIVE" if in_play else "NS"),
                "winner": winner, "decidedBy": decided,
                "kickoff": ev.get("date"),
            })
            # Only seed a real scorable fixture once BOTH teams are decided.
            if h_real and a_real:
                fixture_upserts.append((fid, {
                    "id": fid, "gw": gw, "wcRound": disp,
                    "homeTeam": {"isoCode": hi, "name": hi},
                    "awayTeam": {"isoCode": ai, "name": ai},
                    "kickoff": ev.get("date"),
                }))
        bracket["rounds"][disp] = matches
        bracket["qualified"][disp] = advanced

    db.collection("wc_config").document("wc_bracket").set(bracket)
    # Upsert fixtures (merge — never clobbers playerScores/score/status the live
    # ingest owns); seeds R16+ docs so scoring can pick them up once scheduled.
    for fid, doc in fixture_upserts:
        snap = db.collection("wc_fixtures").document(str(fid)).get()
        if not snap.exists:
            db.collection("wc_fixtures").document(str(fid)).set(doc, merge=True)

    return {
        "rounds": {disp: len(m) for disp, m in bracket["rounds"].items()},
        "qualified": {disp: a for disp, a in bracket["qualified"].items() if a},
        "fixturesSeeded": len(fixture_upserts),
    }
