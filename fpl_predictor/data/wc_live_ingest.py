"""Live World Cup scoring ingestion from FREE public sources.

Two sources, merged:
  * FIFA fantasy JSON (play.fifa.com/json/fantasy/players.json) — the AUTHORITATIVE
    per-player per-round fantasy points (``roundPoints[gw]``). Free, no key.
  * ESPN public API (site.api.espn.com .../fifa.world/...) — the per-player STAT
    LINE (goals, assists, saves, cards, goals-conceded, minutes) plus live
    fixture status/score. Free, no key.

FIFA points become each player's ``fantasyPoints``; ESPN supplies the ``stats``
breakdown the player pop-up renders. Both are mapped onto our synthetic player
pool (ids 900xxx) by normalized name + nation iso, reusing the same fuzzy
matcher that built the FIFA squad alignment.

The ingester writes ``wc_fixtures/{fid}/playerScores/{pid}`` (the docs the
pop-up's collection-group query and the GW-finalize join already read) and
updates each fixture's status/score. It is deliberately NON-destructive to the
finalize path: it never sets ``processedForFantasy``, so it can re-run every few
minutes during a match, and the real post-FT ``finalize_gw`` still runs once.

Run via the ``/admin/ingest-live-scores`` endpoint or the standalone
``scripts/ingest_live_scores.py`` cron.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Dict, List, Optional, Tuple

from fpl_predictor.fuzzy import score as _name_score  # see note in fuzzy.py

FIFA_PLAYERS_URL = "https://play.fifa.com/json/fantasy/players.json"
FIFA_SQUADS_URL = "https://play.fifa.com/json/fantasy/squads.json"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={eid}"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# FIFA squad abbr can differ from our iso; normalize the known divergences.
ISO_ALIASES = {
    "POR": "POR", "MEX": "MEX", "RSA": "RSA", "KOR": "KOR", "CZE": "CZE",
    # add as discovered; identity by default
}


def _get_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------
# FIFA: per-player round points, keyed by (nation_iso, name)
# --------------------------------------------------------------------------
def fetch_fifa_points() -> Dict[int, Dict]:
    """Return {squadId: {abbr, players: [{name, position, roundPoints}]}} merged
    into a flat list of {name, iso, position, roundPoints} entries."""
    players = _get_json(FIFA_PLAYERS_URL)
    players = players if isinstance(players, list) else players.get("players", [])
    squads = _get_json(FIFA_SQUADS_URL)
    squads = squads if isinstance(squads, list) else squads.get("squads", [])
    sq_iso = {s["id"]: (s.get("abbr") or "").upper() for s in squads}

    out = []
    for p in players:
        iso = ISO_ALIASES.get(sq_iso.get(p.get("squadId"), ""), sq_iso.get(p.get("squadId"), ""))
        name = p.get("knownName") or " ".join(
            x for x in (p.get("firstName"), p.get("lastName")) if x).strip()
        st = p.get("stats") or {}
        out.append({
            "name": name,
            "iso": iso,
            "position": p.get("position"),
            "roundPoints": {str(k): v for k, v in (st.get("roundPoints") or {}).items()},
            "seasonTotal": st.get("totalPoints") or 0,
        })
    return out


# --------------------------------------------------------------------------
# ESPN: per-player stat line for a given date's fixtures
# --------------------------------------------------------------------------
# ESPN roster stat name -> our stats key
_ESPN_STAT_MAP = {
    "totalGoals": "goals",
    "goalAssists": "assists",
    "saves": "saves",
    "goalsConceded": "goalsConceded",
    "yellowCards": "yellowCards",
    "redCards": "redCards",
    "ownGoals": "ownGoals",
    "shotsOnTarget": "shotsOnTarget",
    "totalShots": "shots",
    "foulsCommitted": "foulsCommitted",
    "foulsSuffered": "foulsSuffered",
    "appearances": "appeared",
    "subIns": "subIns",
}


def fetch_espn_match_stats(date: str) -> Tuple[List[Dict], List[Dict]]:
    """Return (fixtures, player_stats) for a YYYYMMDD date.

    fixtures: [{eid, homeIso, awayIso, homeName, awayName, homeScore, awayScore,
                statusShort, finished}]
    player_stats: [{name, iso, stats:{...}, cleanSheet}]
    """
    sb = _get_json(ESPN_SCOREBOARD.format(date=date))
    fixtures, stats = [], []
    for ev in sb.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        status = ev.get("status", {}).get("type", {})
        finished = bool(status.get("completed"))
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})

        def _iso(c):
            t = c.get("team", {})
            return (t.get("abbreviation") or t.get("name") or "").upper()

        hg = int(home.get("score") or 0)
        ag = int(away.get("score") or 0)
        fixtures.append({
            "eid": ev.get("id"),
            "homeIso": _iso(home), "awayIso": _iso(away),
            "homeName": home.get("team", {}).get("displayName"),
            "awayName": away.get("team", {}).get("displayName"),
            "homeScore": hg, "awayScore": ag,
            "statusShort": status.get("name"),
            "finished": finished,
        })

        if not finished and status.get("name") not in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME"):
            continue  # not started; no player stats yet

        try:
            summary = _get_json(ESPN_SUMMARY.format(eid=ev.get("id")))
        except Exception:
            continue
        for roster in summary.get("rosters", []) or []:
            iso = (roster.get("team", {}).get("abbreviation")
                   or roster.get("team", {}).get("name") or "").upper()
            conceded = ag if roster.get("homeAway") == "home" else hg
            for entry in roster.get("roster", []) or []:
                ath = entry.get("athlete", {})
                raw = {s.get("name"): s.get("value") for s in (entry.get("stats") or [])}
                if not raw:
                    continue
                mapped = {}
                for ek, ours in _ESPN_STAT_MAP.items():
                    if ek in raw and raw[ek] is not None:
                        mapped[ours] = int(raw[ek]) if float(raw[ek]).is_integer() else raw[ek]
                # minutes: ESPN gives appearances/subIns, not minutes; approximate
                appeared = (raw.get("appearances") or 0) > 0
                mapped["minutes"] = 90 if appeared and not raw.get("subIns") else (30 if appeared else 0)
                mapped["cleanSheet"] = bool(appeared and conceded == 0 and mapped.get("minutes", 0) >= 60)
                stats.append({
                    "name": ath.get("displayName") or ath.get("fullName"),
                    "iso": iso,
                    "starter": bool(entry.get("starter")),
                    "stats": mapped,
                })
    return fixtures, stats


# --------------------------------------------------------------------------
# Map external rows onto our pool by (iso, fuzzy name)
# --------------------------------------------------------------------------
def build_pool_index(db) -> Dict[str, List[Dict]]:
    """{iso -> [{id, name}]} for our 900xxx player pool."""
    idx: Dict[str, List[Dict]] = {}
    for d in db.collection("wc_players").stream():
        p = d.to_dict() or {}
        iso = (p.get("teamIso") or "").upper()
        idx.setdefault(iso, []).append({"id": int(d.id), "name": p.get("name", "")})
    return idx


def match_to_pool(name: str, iso: str, pool_index: Dict[str, List[Dict]],
                  threshold: float = 0.80) -> Optional[int]:
    cands = pool_index.get(iso, [])
    best_id, best = None, 0.0
    for c in cands:
        s = _name_score(name, c["name"])
        if s > best:
            best, best_id = s, c["id"]
    return best_id if best >= threshold else None


# --------------------------------------------------------------------------
# Orchestrator: write playerScores + fixture status + live league totals
# --------------------------------------------------------------------------
def _fixture_index(db, gw: Optional[int]) -> Dict[Tuple[str, str], object]:
    """{(homeIso, awayIso) -> fixture_ref} for the target GW (or all)."""
    q = db.collection("wc_fixtures")
    docs = q.where("gw", "==", gw).stream() if gw else q.stream()
    out = {}
    for d in docs:
        f = d.to_dict() or {}
        h = (f.get("homeTeam", {}).get("isoCode") or "").upper()
        a = (f.get("awayTeam", {}).get("isoCode") or "").upper()
        if h and a:
            out[(h, a)] = d.reference
    return out


def ingest_live(db, gw: int, date: str) -> dict:
    """Single ingestion pass for one GW / one calendar date.

    Writes per-player playerScores (FIFA points + ESPN stats) under each started
    fixture, updates fixture status/score, recomputes per-manager live totals for
    every active league. Idempotent + non-destructive: never sets
    processedForFantasy, so the post-FT finalize still runs once.
    """
    from google.cloud import firestore as _fs

    fifa = fetch_fifa_points()
    fixtures, espn = fetch_espn_match_stats(date)
    pool = build_pool_index(db)
    fx_index = _fixture_index(db, gw)

    # name+iso -> our pool id (cache so each player resolves once)
    _cache: Dict[Tuple[str, str], Optional[int]] = {}

    def resolve(name, iso):
        key = (iso, (name or "").lower())
        if key not in _cache:
            _cache[key] = match_to_pool(name, iso, pool)
        return _cache[key]

    # FIFA points indexed by pool id (authoritative fantasyPoints)
    fifa_pts: Dict[int, int] = {}        # this GW's round points
    fifa_season: Dict[int, int] = {}     # season total (all rounds)
    for p in fifa:
        rp = p["roundPoints"].get(str(gw))
        pid = resolve(p["name"], p["iso"])
        if pid is None:
            continue
        if rp is not None:
            fifa_pts[pid] = rp
        if p.get("seasonTotal"):
            fifa_season[pid] = p["seasonTotal"]

    # ESPN stat line indexed by pool id
    espn_stats: Dict[int, dict] = {}
    for e in espn:
        pid = resolve(e["name"], e["iso"])
        if pid is not None:
            espn_stats[pid] = e["stats"]

    written = 0
    fixtures_touched = []
    # Map ESPN fixtures to our fixture docs and write playerScores
    for fx in fixtures:
        ref = fx_index.get((fx["homeIso"], fx["awayIso"]))
        if ref is None:
            continue
        started = fx["finished"] or fx["statusShort"] in (
            "STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_FULL_TIME")
        ref.set({
            "status": "FT" if fx["finished"] else ("LIVE" if started else "NS"),
            "score": {"home": fx["homeScore"], "away": fx["awayScore"]},
            "liveUpdatedAt": _fs.SERVER_TIMESTAMP,
        }, merge=True)
        if not started:
            continue
        fixtures_touched.append(ref.id)
        fdata = ref.get().to_dict() or {}
        h_iso = (fdata.get("homeTeam", {}).get("isoCode") or "").upper()
        a_iso = (fdata.get("awayTeam", {}).get("isoCode") or "").upper()
        # which pool players belong to this fixture's two nations
        fixture_isos = {h_iso, a_iso}
        scores_coll = ref.collection("playerScores")
        for pid, pts in fifa_pts.items():
            # only write players whose nation is in this fixture
            piso = None
            for iso, lst in pool.items():
                if any(c["id"] == pid for c in lst):
                    piso = iso
                    break
            if piso not in fixture_isos:
                continue
            stats = espn_stats.get(pid, {})
            scores_coll.document(str(pid)).set({
                "playerId": pid,
                "gw": gw,
                "fantasyPoints": pts,          # FIFA authoritative
                "bonusPoints": 0,
                "stats": stats,
                "source": "fifa+espn",
                "live": not fx["finished"],
                "updatedAt": _fs.SERVER_TIMESTAMP,
            }, merge=True)
            written += 1

    # season totals on the pool (for Players tab / popup "Total"); season total
    # is FIFA's own all-rounds figure so re-running a single GW never clobbers it.
    for pid in set(fifa_pts) | set(fifa_season):
        upd = {}
        if pid in fifa_season:
            upd["totalPoints"] = fifa_season[pid]
        if pid in fifa_pts:
            upd[f"gwPoints.{gw}"] = fifa_pts[pid]
        if upd:
            db.collection("wc_players").document(str(pid)).set(upd, merge=True)

    # per-manager LIVE totals for every active league (no finalize, no lock flip)
    leagues_updated = _recompute_live_scores(db, gw, fifa_pts)

    return {
        "gw": gw, "date": date,
        "fixturesTouched": fixtures_touched,
        "playerScoresWritten": written,
        "fifaScorers": len(fifa_pts),
        "espnStatRows": len(espn_stats),
        "leaguesUpdated": leagues_updated,
    }


def _recompute_live_scores(db, gw: int, pts_by_pid: Dict[int, int]) -> List[str]:
    """Write leagues/{lid}/scores/{gw}.results.{uid}.points = live Σ starters
    (+captain x2) from the locked lineup. Marked live=True; the post-FT finalize
    overwrites with the official, auto-subbed total."""
    from google.cloud import firestore as _fs
    updated = []
    for ldoc in db.collection("leagues").stream():
        league = ldoc.to_dict() or {}
        if league.get("status") not in ("group_phase", "knockout"):
            continue
        lref = ldoc.reference
        results = {}
        for mref in lref.collection("members").stream():
            uid = mref.id
            lu = lref.collection("lineups").document(f"{uid}_{gw}").get()
            if not lu.exists:
                continue
            lin = lu.to_dict() or {}
            starting = lin.get("starting", []) or []
            cap = lin.get("captain")
            total = sum(pts_by_pid.get(int(p), 0) for p in starting)
            if cap is not None and int(cap) in [int(p) for p in starting]:
                total += pts_by_pid.get(int(cap), 0)  # captain doubles
            results[uid] = {"points": total}
        if results:
            lref.collection("scores").document(str(gw)).set(
                {"results": results, "live": True, "updatedAt": _fs.SERVER_TIMESTAMP},
                merge=True)
            updated.append(ldoc.id)
    return updated
