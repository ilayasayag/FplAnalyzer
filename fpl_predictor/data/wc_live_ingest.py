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


def _gw_points_map(db, gw: int) -> Dict[int, int]:
    """Build {pool_id -> OUR fantasyPoints} for a GW by reading each GW fixture's
    playerScores subcollection directly (avoids a collection-group index)."""
    out: Dict[int, int] = {}
    for fx in db.collection("wc_fixtures").where("gw", "==", gw).stream():
        for d in fx.reference.collection("playerScores").stream():
            r = d.to_dict() or {}
            out[int(d.id)] = r.get("fantasyPoints", 0) or 0
    return out


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


# --------------------------------------------------------------------------
# WhoScored: full Opta stat line incl. DEFENSIVE actions (the DefCon source)
# --------------------------------------------------------------------------
import gzip as _gzip
import re as _re

WS_BASE = "https://www.whoscored.com"


def _ws_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.whoscored.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = _gzip.decompress(body)
        return body.decode("utf-8", "ignore")


def _ws_match_centre(ws_match_id: int) -> Optional[dict]:
    """Pull the matchCentreData JSON embedded in WhoScored's /live/ page."""
    html = _ws_fetch(f"{WS_BASE}/matches/{ws_match_id}/live")
    m = _re.search(r"matchCentreData\s*[:=]\s*(\{.*?\})\s*[,;]\s*matchCentreEventTypeJSON", html, _re.S)
    if not m:
        m = _re.search(r"matchCentreData\s*[:=]\s*(\{.*?\})\s*,\s*\n", html, _re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def parse_whoscored_match(ws_match_id: int) -> Tuple[dict, List[Dict]]:
    """Return (meta, player_rows). meta has home/away iso+name+score; each row is
    {name, side, isStarter, stats:{...}} with goals/assists/minutes/cards/saves
    plus tackles{total,interceptions,blocks}+clearances (DefCon inputs)."""
    data = _ws_match_centre(ws_match_id)
    if not data:
        return {}, []
    idname = data.get("playerIdNameDictionary", {})
    max_min = data.get("maxMinute") or 90
    ft = (data.get("ftScore") or "0 : 0").replace(" ", "").split(":")
    home_goals, away_goals = (int(ft[0]), int(ft[1])) if len(ft) == 2 else (0, 0)
    home, away = data.get("home", {}), data.get("away", {})

    # per-player event aggregation
    from collections import Counter, defaultdict
    ev_goals, ev_assists = Counter(), Counter()
    ev_yellow, ev_red, ev_og, ev_pen_miss = Counter(), Counter(), Counter(), Counter()
    tk, interc, clear, blocks = Counter(), Counter(), Counter(), Counter()
    sub_off, sub_on = {}, {}
    for e in data.get("events", []):
        pid = e.get("playerId")
        if pid is None:
            continue
        tn = e.get("type", {}).get("displayName")
        ok = e.get("outcomeType", {}).get("displayName") == "Successful"
        quals = {q.get("type", {}).get("displayName") for q in e.get("qualifiers", [])}
        if tn == "Goal" and ok:
            (ev_og if "OwnGoal" in quals else ev_goals)[pid] += 1
        elif tn == "Pass" and "IntentionalGoalAssist" in quals:
            ev_assists[pid] += 1
        elif tn == "Card":
            if "Red" in quals or "SecondYellow" in quals:
                ev_red[pid] += 1
            elif "Yellow" in quals:
                ev_yellow[pid] += 1
        elif tn == "MissedShots" and "Penalty" in quals:
            ev_pen_miss[pid] += 1
        elif tn == "Tackle" and ok:
            tk[pid] += 1
        elif tn == "Interception":
            interc[pid] += 1
        elif tn == "Clearance":
            clear[pid] += 1
        elif tn in ("BlockedPass", "Save") and tn == "BlockedPass":
            blocks[pid] += 1
        if tn == "SubstitutionOff":
            sub_off[pid] = e.get("minute")
        elif tn == "SubstitutionOn":
            sub_on[pid] = e.get("minute")

    def minutes_for(pid, is_starter):
        if pid in sub_off:
            return sub_off[pid]
        if pid in sub_on:
            return max(0, max_min - sub_on[pid])
        return max_min if is_starter else 0

    rows = []
    for side, team, conceded in (("home", home, away_goals), ("away", away, home_goals)):
        for p in team.get("players", []):
            pid = p.get("playerId")
            starter = bool(p.get("isFirstEleven"))
            mins = minutes_for(pid, starter)
            if mins == 0 and pid not in sub_on and not starter:
                continue  # unused sub
            saves = int((p.get("stats", {}).get("totalSaves") or {}) and
                        sum((p["stats"]["totalSaves"]).values()) or 0)
            rows.append({
                "name": idname.get(str(pid)) or p.get("name"),
                "side": side,
                "isStarter": starter,
                "stats": {
                    "minutes": mins,
                    "goals": ev_goals.get(pid, 0),
                    "assists": ev_assists.get(pid, 0),
                    "yellowCards": ev_yellow.get(pid, 0),
                    "redCards": ev_red.get(pid, 0),
                    "ownGoal": ev_og.get(pid, 0),
                    "penaltyMissed": ev_pen_miss.get(pid, 0),
                    "saves": saves,
                    "goalsConceded": conceded,
                    "cleanSheet": conceded == 0 and mins >= 60,
                    "tackles": {
                        "total": tk.get(pid, 0),
                        "interceptions": interc.get(pid, 0),
                        "blocks": blocks.get(pid, 0),
                    },
                    "clearances": clear.get(pid, 0),
                    "defCon": tk.get(pid, 0) + interc.get(pid, 0) + clear.get(pid, 0) + blocks.get(pid, 0),
                },
            })
    meta = {
        "homeName": home.get("name"), "awayName": away.get("name"),
        "homeScore": home_goals, "awayScore": away_goals,
        "finished": (data.get("ftScore") is not None),
    }
    return meta, rows


def ingest_whoscored_fixture(db, ws_match_id: int, our_fixture_id: str, gw: int) -> dict:
    """Score ONE fixture from WhoScored: parse full stat lines, map to our pool,
    compute OUR league points + itemized breakdown (incl. DefCon), and write
    wc_fixtures/{fid}/playerScores/{pid}. FIFA points are stored as a reference.
    Non-destructive: never sets processedForFantasy."""
    from google.cloud import firestore as _fs
    from fpl_predictor.game.wc_scoring import compute_player_points, compute_breakdown

    meta, rows = parse_whoscored_match(ws_match_id)
    if not rows:
        return {"error": "no WhoScored data", "ws_match_id": ws_match_id}

    fref = db.collection("wc_fixtures").document(str(our_fixture_id))
    fdoc = fref.get().to_dict() or {}
    h_iso = (fdoc.get("homeTeam", {}).get("isoCode") or "").upper()
    a_iso = (fdoc.get("awayTeam", {}).get("isoCode") or "").upper()
    side_iso = {"home": h_iso, "away": a_iso}

    pool = build_pool_index(db)
    pos_map = {int(d.id): (d.to_dict() or {}).get("position", 3)
               for d in db.collection("wc_players").stream()}
    rules = (db.collection("wc_config").document("tournament").get().to_dict() or {}).get("rules", {})

    # FIFA reference points for this GW (by pool id)
    fifa = fetch_fifa_points()
    fifa_pts = {}
    for p in fifa:
        rp = p["roundPoints"].get(str(gw))
        if rp is None:
            continue
        pid = match_to_pool(p["name"], p["iso"], pool)
        if pid:
            fifa_pts[pid] = rp

    written = 0
    for row in rows:
        iso = side_iso.get(row["side"])
        pid = match_to_pool(row["name"], iso, pool)
        if pid is None:
            continue
        position = pos_map.get(pid, 3)
        stats = row["stats"]
        base, _ = compute_player_points(stats, position, rules)
        breakdown = compute_breakdown(stats, position, rules)
        fref.collection("playerScores").document(str(pid)).set({
            "playerId": pid, "gw": gw,
            "fantasyPoints": base,            # OUR league points (incl. DefCon)
            "bonusPoints": 0,
            "fifaPoints": fifa_pts.get(pid),  # reference
            "stats": stats,
            "breakdown": breakdown,
            "source": "whoscored",
            "live": not meta.get("finished"),
            "updatedAt": _fs.SERVER_TIMESTAMP,
        }, merge=True)
        db.collection("wc_players").document(str(pid)).set(
            {f"gwPoints.{gw}": base}, merge=True)
        written += 1

    fref.set({
        "status": "FT" if meta.get("finished") else "LIVE",
        "score": {"home": meta.get("homeScore"), "away": meta.get("awayScore")},
        "liveUpdatedAt": _fs.SERVER_TIMESTAMP,
    }, merge=True)

    leagues = _recompute_live_scores(db, gw, _gw_points_map(db, gw))
    return {"fixture": our_fixture_id, "wsMatchId": ws_match_id, "playerScoresWritten": written,
            "leaguesUpdated": leagues, "meta": meta}
