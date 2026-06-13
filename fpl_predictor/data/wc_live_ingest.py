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

# Feed abbr (FIFA + ESPN both use FIFA-style codes) can differ from our
# isoCode (api-sports style). Verified against ALL 48 teams on 2026-06-12 by
# diffing both feeds' team lists vs wc_teams — these are the only divergences.
# An unmapped code (e.g. BIH) silently drops the whole match from fixture
# matching AND every player of that nation from points matching, so keep this
# table complete.
ISO_ALIASES = {
    "BIH": "BOS",   # Bosnia & Herzegovina
    "ESP": "SPA",   # Spain
    "IRN": "IRA",   # Iran
    "JPN": "JAP",   # Japan
    "KSA": "SAU",   # Saudi Arabia
    "MAR": "MOR",   # Morocco
    "SUI": "SWI",   # Switzerland
}


def _norm_iso(abbr: str) -> str:
    """Normalize a feed team code to our isoCode (identity when not aliased)."""
    code = (abbr or "").upper()
    return ISO_ALIASES.get(code, code)


def _get_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------
# FIFA: per-player round points, keyed by (nation_iso, name)
# --------------------------------------------------------------------------
def fetch_fifa_points() -> Dict[int, Dict]:
    """Return a flat list of FIFA player entries:
    ``{name, iso, position, roundPoints, seasonTotal, percentSelected,
    fifaPrice, fifaForm}``.

    ``percentSelected`` / ``fifaPrice`` / ``fifaForm`` come straight from the
    FIFA fantasy feed (verified live 2026-06-12: top-level ``percentSelected`` +
    ``price``, ``stats.form``) and are surfaced for the Transfers sort/columns +
    Compare tab. Absent fields stay ``None`` so a feed-shape change degrades
    gracefully rather than crashing the ingest."""
    players = _get_json(FIFA_PLAYERS_URL)
    players = players if isinstance(players, list) else players.get("players", [])
    squads = _get_json(FIFA_SQUADS_URL)
    squads = squads if isinstance(squads, list) else squads.get("squads", [])
    sq_iso = {s["id"]: (s.get("abbr") or "").upper() for s in squads}

    out = []
    for p in players:
        iso = _norm_iso(sq_iso.get(p.get("squadId"), ""))
        name = p.get("knownName") or " ".join(
            x for x in (p.get("firstName"), p.get("lastName")) if x).strip()
        st = p.get("stats") or {}
        out.append({
            "name": name,
            "iso": iso,
            "position": p.get("position"),
            "roundPoints": {str(k): v for k, v in (st.get("roundPoints") or {}).items()},
            "seasonTotal": st.get("totalPoints") or 0,
            "percentSelected": p.get("percentSelected"),
            "fifaPrice": p.get("price"),
            "fifaForm": st.get("form"),
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
            return _norm_iso(t.get("abbreviation") or t.get("name") or "")

        hg = int(home.get("score") or 0)
        ag = int(away.get("score") or 0)
        fixtures.append({
            "eid": ev.get("id"),
            "homeIso": _iso(home), "awayIso": _iso(away),
            "homeName": home.get("team", {}).get("displayName"),
            "awayName": away.get("team", {}).get("displayName"),
            "homeScore": hg, "awayScore": ag,
            "statusShort": status.get("name"),
            # ESPN soccer uses granular names (STATUS_FIRST_HALF, _SECOND_HALF,
            # overtime/shootout variants in knockouts) — `state` is the stable
            # signal: "pre" | "in" | "post". Match liveness on it, not on names.
            "state": status.get("state"),
            "finished": finished,
        })

        if not finished and status.get("state") != "in":
            continue  # not started; no player stats yet

        try:
            summary = _get_json(ESPN_SUMMARY.format(eid=ev.get("id")))
        except Exception:
            continue
        for roster in summary.get("rosters", []) or []:
            iso = _norm_iso(roster.get("team", {}).get("abbreviation")
                            or roster.get("team", {}).get("name") or "")
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
        idx.setdefault(iso, []).append({"id": int(d.id), "name": p.get("name", ""),
                                        "pos": p.get("position", 3)})
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
        started = fx["finished"] or fx.get("state") == "in"
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
            pos = next((c.get("pos") for c in pool.get(piso, []) if c["id"] == pid), 3) or 3
            # Preserve any DefCon bonus a residential WhoScored run already
            # computed (cloud can't reach WhoScored), so this FIFA pass never
            # clobbers it. Total = FIFA + preserved DefCon; breakdown stays itemized.
            existing = scores_coll.document(str(pid)).get().to_dict() or {}
            dcb = existing.get("defConBonus", 0) or 0
            dca = existing.get("defConActions")
            bd = fifa_breakdown(stats, pos, pts)
            if dca is not None:
                thr = 10 if pos == 2 else (12 if pos == 3 else None)
                if thr is not None:
                    bd.append({"label": f"Defensive contribution ({dca}/{thr})",
                               "value": dca, "pts": dcb})
            scores_coll.document(str(pid)).set({
                "playerId": pid,
                "gw": gw,
                "fantasyPoints": pts + dcb,     # FIFA + preserved DefCon
                "fifaPoints": pts,
                "bonusPoints": 0,
                "stats": stats,
                "breakdown": bd,
                "source": "fifa+espn",
                "live": not fx["finished"],
                "updatedAt": _fs.SERVER_TIMESTAMP,
            }, merge=True)
            written += 1

    # season totals on the pool (for Players tab / popup "Total"); season total
    # is FIFA's own all-rounds figure so re-running a single GW never clobbers it.
    # (FIFA ownership/price/form + the season-stat aggregates are stamped once
    # per scan by refresh_pool_aggregates, not here, so every scoring path —
    # WhoScored or this fallback — gets them.)
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


def _batch_set_players(db, updates: Dict[int, dict]) -> int:
    """Merge-write ``{pid: data}`` to wc_players in batched commits.

    The whole-pool refreshers touch 100s–1000s of docs each scan; one ``.set()``
    per doc is ~1 RPC each (the 281s prod backfill was almost entirely write
    latency). Batching to Firestore's 500-op limit collapses that to a handful of
    commits. Returns the number of docs written."""
    items = list(updates.items())
    coll = db.collection("wc_players")
    for i in range(0, len(items), 450):
        batch = db.batch()
        for pid, data in items[i:i + 450]:
            batch.set(coll.document(str(pid)), data, merge=True)
        batch.commit()
    return len(items)


# Stat-line keys (from the ESPN mapping in playerScores.stats) that the season
# aggregate sums. cleanSheets/appearances are derived, not summed directly.
def recompute_season_stats(db) -> int:
    """Recompute ``wc_players/{pid}.seasonStats`` from EVERY playerScore doc.

    Idempotent by construction: it always does a full recompute from the durable
    per-fixture ``playerScores`` (never an increment), so re-running an ingest
    tick — or the same GW twice — leaves the figures unchanged. Aggregates the
    ESPN stat line (goals/assists/shots-on-target/shots/minutes), counts
    clean-sheet matches + appearances, and sums the WhoScored DefCon fields.

    Mirrors ``_gw_points_map``'s fixture→playerScores walk (no collection-group
    index needed). Returns the number of players written.
    """
    agg: Dict[int, Dict[str, float]] = {}
    for fx in db.collection("wc_fixtures").stream():
        for d in fx.reference.collection("playerScores").stream():
            r = d.to_dict() or {}
            try:
                pid = int(d.id)
            except (TypeError, ValueError):
                continue
            a = agg.setdefault(pid, {
                "goals": 0, "assists": 0, "shotsOnTarget": 0, "shots": 0,
                "cleanSheets": 0, "minutes": 0, "appearances": 0,
                "defconActions": 0, "defconBonus": 0,
            })
            st = r.get("stats") or {}
            a["goals"] += st.get("goals", 0) or 0
            a["assists"] += st.get("assists", 0) or 0
            a["shotsOnTarget"] += st.get("shotsOnTarget", 0) or 0
            a["shots"] += st.get("shots", 0) or 0
            mins = st.get("minutes", 0) or 0
            a["minutes"] += mins
            if st.get("cleanSheet"):
                a["cleanSheets"] += 1
            if mins > 0:
                a["appearances"] += 1
            a["defconActions"] += r.get("defConActions", 0) or 0
            a["defconBonus"] += r.get("defConBonus", 0) or 0

    return _batch_set_players(db, {pid: {"seasonStats": a} for pid, a in agg.items()})


def stamp_fifa_meta(db) -> int:
    """Stamp FIFA ownership / price / form (+ season total) onto wc_players for
    every resolvable player.

    Independent of fixtures — it's a snapshot of the live FIFA fantasy feed — so
    it must run once per scan REGARDLESS of which scoring path each fixture used
    (WhoScored or the FIFA/ESPN fallback). Returns the count of players stamped;
    0 if the feed is unreachable (a feed blip must never break a scan)."""
    try:
        fifa = fetch_fifa_points()
    except Exception as exc:
        print(f"[wc_ingest] stamp_fifa_meta: FIFA feed unavailable: {exc!r}")
        return 0
    pool = build_pool_index(db)
    cache: Dict[Tuple[str, str], Optional[int]] = {}

    def resolve(name, iso):
        key = (iso, (name or "").lower())
        if key not in cache:
            cache[key] = match_to_pool(name, iso, pool)
        return cache[key]

    updates: Dict[int, dict] = {}
    for p in fifa:
        pid = resolve(p["name"], p["iso"])
        if pid is None:
            continue
        meta = {}
        if p.get("percentSelected") is not None:
            meta["percentSelected"] = p["percentSelected"]
        if p.get("fifaPrice") is not None:
            meta["fifaPrice"] = p["fifaPrice"]
        if p.get("fifaForm") is not None:
            meta["fifaForm"] = p["fifaForm"]
        if p.get("seasonTotal"):
            meta["totalPoints"] = p["seasonTotal"]
        if meta:
            updates[pid] = meta  # one entry per pid (last feed row wins)
    return _batch_set_players(db, updates)


def refresh_pool_aggregates(db) -> dict:
    """Recompute season stats + stamp FIFA ownership/price/form for the whole
    pool. Called at the END of every scan (``catch_up_scan`` /
    ``run_scheduled_ingest``) so the Transfers sort/columns + Compare tab are
    populated no matter which scoring path ran — both operations are full,
    idempotent recomputes/snapshots, safe to repeat."""
    return {
        "seasonStatsPlayers": recompute_season_stats(db),
        "fifaMetaPlayers": stamp_fifa_meta(db),
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
    # Mid-match the matchCentre carries the RUNNING score in `score` and an
    # EMPTY-STRING `ftScore`; ftScore only fills at full time. Prefer it when
    # set, else the live score — never default a live match to 0:0.
    ft = ((data.get("ftScore") or "").strip() or (data.get("score") or "0 : 0")) \
        .replace(" ", "").split(":")
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
            pst = p.get("stats", {}) or {}
            saves = int((pst.get("totalSaves") or {}) and sum((pst["totalSaves"]).values()) or 0)
            sot = int(sum((pst.get("shotsOnTarget") or {}).values())) if pst.get("shotsOnTarget") else 0
            rows.append({
                "name": idname.get(str(pid)) or p.get("name"),
                "side": side,
                "isStarter": starter,
                "stats": {
                    "minutes": min(mins, 90),
                    "shotsOnTarget": sot,
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
        # ftScore exists as '' DURING the match (so `is not None` called every
        # live game finished, stamping FT/0-0 at minute 35). Finished = elapsed
        # says FT, or a real full-time score string is present.
        "finished": (str(data.get("elapsed") or "").strip().upper() == "FT"
                     or bool((data.get("ftScore") or "").strip())),
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

    sr = rules.get("scoring", {})
    defcon_pts = sr.get("defConPoints", 2)
    thr_def = sr.get("defConThresholdDef", 10)
    thr_mid = sr.get("defConThresholdMid", 12)

    written = 0
    for row in rows:
        iso = side_iso.get(row["side"])
        pid = match_to_pool(row["name"], iso, pool)
        if pid is None:
            continue
        position = pos_map.get(pid, 3)
        stats = row["stats"]

        # SCORING MODEL = FIFA official total + our DefCon bonus.
        fifa = fifa_pts.get(pid)
        defcon = stats.get("defCon", 0) or 0
        thr = thr_def if position == 2 else (thr_mid if position == 3 else None)
        defcon_bonus = defcon_pts if (thr is not None and defcon >= thr) else 0

        if fifa is not None:
            base = fifa
            # itemized FIFA-rules breakdown reconstructed from our stats, with a
            # reconciling line so it sums to FIFA's authoritative total
            breakdown = fifa_breakdown(stats, position, fifa)
        else:
            # player not in FIFA's scored list (rare) -> fall back to our engine
            base, _ = compute_player_points(stats, position, rules)
            breakdown = compute_breakdown(stats, position, rules)
        if thr is not None:
            breakdown.append({"label": f"Defensive contribution ({defcon}/{thr})",
                              "value": defcon, "pts": defcon_bonus})
        total = base + defcon_bonus

        fref.collection("playerScores").document(str(pid)).set({
            "playerId": pid, "gw": gw,
            "fantasyPoints": total,           # FIFA total + our DefCon
            "bonusPoints": 0,
            "fifaPoints": fifa,               # FIFA base (reference)
            "defConActions": defcon,
            "defConBonus": defcon_bonus,
            "stats": stats,
            "breakdown": breakdown,
            "source": "whoscored+fifa",
            "live": not meta.get("finished"),
            "updatedAt": _fs.SERVER_TIMESTAMP,
        }, merge=True)
        db.collection("wc_players").document(str(pid)).set(
            {f"gwPoints.{gw}": total}, merge=True)
        written += 1

    fref.set({
        "status": "FT" if meta.get("finished") else "LIVE",
        "score": {"home": meta.get("homeScore"), "away": meta.get("awayScore")},
        "liveUpdatedAt": _fs.SERVER_TIMESTAMP,
    }, merge=True)

    leagues = _recompute_live_scores(db, gw, _gw_points_map(db, gw))
    return {"fixture": our_fixture_id, "wsMatchId": ws_match_id, "playerScoresWritten": written,
            "leaguesUpdated": leagues, "meta": meta}


# --------------------------------------------------------------------------
# Reconstruct FIFA's itemized scoring from our stats (FIFA's published rules),
# with a reconciling "FIFA bonus" line so the panel always sums to FIFA's
# authoritative total (scouting bonus / long-range / chances-created etc. that
# FIFA computes internally land in that line).
# https://sports.yahoo.com/articles/fifa-world-cup-fantasy-2026-054141309.html
# --------------------------------------------------------------------------
def fifa_breakdown(stats: dict, position: int, fifa_total: Optional[int]) -> list:
    if fifa_total is None:
        return []
    mins = stats.get("minutes") or 0
    lines = []
    known = 0

    def add(label, value, pts):
        nonlocal known
        if pts or value:
            lines.append({"label": label, "value": value, "pts": pts})
            known += pts

    if mins > 0:
        p = 2 if mins >= 60 else 1
        add("Minutes played", mins, p)
    goals = stats.get("goals", 0) or 0
    if goals:
        gp = {1: 6, 2: 6, 3: 5, 4: 4}.get(position, 4)
        add("Goal scored", goals, goals * gp)
    assists = stats.get("assists", 0) or 0
    if assists:
        add("Assist", assists, assists * 3)
    if position in (1, 2) and mins >= 60 and stats.get("cleanSheet"):
        add("Clean sheet", 1, 5)
    gc = stats.get("goalsConceded", 0) or 0
    if position in (1, 2) and not stats.get("cleanSheet") and gc >= 2:
        add("Goals conceded", gc, -(gc - 1))
    sot = stats.get("shotsOnTarget", 0) or 0
    if sot >= 2:
        add("Shots on target", sot, sot // 2)
    if position == 1:
        saves = stats.get("saves", 0) or 0
        if saves >= 3:
            add("Saves", saves, saves // 3)
    yc = stats.get("yellowCards", 0) or 0
    if yc:
        add("Yellow card", yc, -yc)
    rc = stats.get("redCards", 0) or 0
    if rc:
        add("Red card", rc, -2 * rc)
    og = stats.get("ownGoals", 0) or stats.get("ownGoal", 0) or 0
    if og:
        add("Own goal", og, -2 * og)

    # Reconcile to FIFA's authoritative total. The remainder is FIFA's internal
    # extras (scouting bonus, long-range goal bonus, chances created, ball
    # recoveries) we can't itemize from this feed.
    remainder = fifa_total - known
    if remainder:
        lines.append({"label": "FIFA bonus (scouting / extras)", "value": None, "pts": remainder})
    return lines


# --------------------------------------------------------------------------
# Automation: discover WhoScored match ids for our fixtures, then a single
# scheduled pass that scores every live / recently-finished match.
# --------------------------------------------------------------------------
WS_TOURNAMENT_URL = "https://www.whoscored.com/regions/247/tournaments/36/fifa-world-cup"


# WhoScored slug spellings that differ from our team names.
_SLUG_ALIASES = {
    "republic": "", "of": "", "korea": "korea", "turkiye": "turkey",
    "czechia": "czech", "republic-of-korea": "korea",
}

def _slug_tokens(slug: str) -> set:
    from fpl_predictor.fuzzy import translit
    raw = translit(slug.replace("-", " "))
    out = set()
    for t in raw.split():
        a = _SLUG_ALIASES.get(t, t)
        if a:
            out.add(a)
    return out


def _name_tokens(name: str) -> set:
    from fpl_predictor.fuzzy import translit
    out = set()
    for t in translit(name or "").split():
        a = _SLUG_ALIASES.get(t, t)
        if a:
            out.add(a)
    return out


def discover_whoscored_ids(db) -> dict:
    """Scrape WhoScored's WC2026 fixtures page, map each (home,away) slug pair to
    one of our fixture docs by team-name tokens, and persist
    wc_config/whoscored_map = {our_fixture_id: ws_match_id}. Idempotent; safe to
    run daily as the calendar fills in."""
    html = _ws_fetch(WS_TOURNAMENT_URL)
    pairs = _re.findall(
        r'/matches/(\d+)/[a-z]+/international-fifa-world-cup-2026-([a-z0-9-]+)', html)
    seen = {}
    for mid, slug in pairs:
        seen.setdefault(slug, mid)  # first id per slug

    # our fixtures: build token sets from team names/isos
    teams = {}  # iso -> name tokens
    for d in db.collection("wc_teams").stream():
        t = d.to_dict() or {}
        iso = (t.get("isoCode") or d.id or "").upper()
        teams[iso] = _name_tokens(t.get("name") or "")

    fixtures = []
    for d in db.collection("wc_fixtures").stream():
        f = d.to_dict() or {}
        fixtures.append((d.id, (f.get("homeTeam", {}).get("isoCode") or "").upper(),
                         (f.get("awayTeam", {}).get("isoCode") or "").upper()))

    mapping = {}
    unmatched = []
    for slug, mid in seen.items():
        toks = _slug_tokens(slug)
        # split the combined slug into home/away by finding the best fixture whose
        # two team token-sets together cover the slug tokens
        best = None
        for fid, hiso, aiso in fixtures:
            ht, at = teams.get(hiso, set()), teams.get(aiso, set())
            if not ht or not at:
                continue
            # both teams must have >=1 token in the slug; rank by total covered
            if (ht & toks) and (at & toks):
                covered = len((ht | at) & toks)
                if best is None or covered > best[1]:
                    best = (fid, covered)
        if best:
            mapping[best[0]] = int(mid)
        else:
            unmatched.append(slug)

    db.collection("wc_config").document("whoscored_map").set(
        {"map": {str(k): v for k, v in mapping.items()}, "unmatched": unmatched}, merge=True)
    return {"matched": len(mapping), "unmatched": unmatched, "wsMatchesSeen": len(seen)}


def run_scheduled_ingest(db, date: Optional[str] = None) -> dict:
    """ONE scheduled pass (call from cron every ~10 min during match windows):
    ESPN says which of today's fixtures are live/finished; for each we score from
    WhoScored (DefCon + FIFA points) using the discovered id, else ESPN-only.
    Free, no LLM. Idempotent + non-finalizing, so the 'while live' + '1h after'
    cadence is just the cron firing repeatedly."""
    from datetime import datetime, timezone
    date = date or datetime.now(timezone.utc).strftime("%Y%m%d")
    lg = db.collection("leagues").document("lg_mock_draft").get()
    gw = (lg.to_dict() or {}).get("currentGw", 1) if lg.exists else 1

    espn_fixtures, _ = fetch_espn_match_stats(date)
    ws_map = (db.collection("wc_config").document("whoscored_map").get().to_dict() or {}).get("map", {})
    fx_index = _fixture_index(db, None)  # (homeIso,awayIso)->ref across all gws

    done, skipped = [], []
    for fx in espn_fixtures:
        if not (fx["finished"] or fx.get("state") == "in"):
            skipped.append(f"{fx['homeIso']}-{fx['awayIso']}:{fx['statusShort']}")
            continue
        ref = fx_index.get((fx["homeIso"], fx["awayIso"]))
        if ref is None:
            continue
        ws_id = ws_map.get(str(ref.id))
        try:
            r = None
            if ws_id:
                try:
                    r = ingest_whoscored_fixture(db, int(ws_id), ref.id, gw)
                except Exception:
                    r = None  # raise (e.g. 403 from datacenter IP) -> fallback
            # WhoScored unreachable (e.g. blocks datacenter IPs from cloud) or no
            # id yet -> fall back to FIFA points + ESPN stats (no DefCon bonus) so
            # scoring still flows. Full DefCon comes from a residential-IP run.
            if not ws_id or not r or r.get("error") or not r.get("playerScoresWritten"):
                ingest_live(db, gw, date)
                done.append({"fixture": ref.id, "via": "fifa-espn-fallback"})
            else:
                done.append({"fixture": ref.id, "via": "whoscored",
                             "n": r.get("playerScoresWritten")})
        except Exception as exc:
            done.append({"fixture": ref.id, "error": str(exc)})
    # Whole-pool aggregates once per pass (see catch_up_scan).
    aggregates = refresh_pool_aggregates(db)
    return {"date": date, "gw": gw, "scored": done, "skipped": skipped,
            **aggregates}


# --------------------------------------------------------------------------
# Catch-up watermark: heal any matches missed while nothing was scanning.
# Each fixture carries a `scoredFinal` bookmark once its FINISHED result is
# locked in; catch_up_scan walks recent dates and scores every FT fixture that
# isn't bookmarked yet (then sets the bookmark), so a redeploy / downtime never
# loses a game. In-progress fixtures are scored too but NOT bookmarked.
# --------------------------------------------------------------------------
def catch_up_scan(db, days_back: int = 3, date: Optional[str] = None) -> dict:
    from datetime import datetime, timezone, timedelta
    from google.cloud import firestore as _fs

    today = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc) \
        if date else datetime.now(timezone.utc)
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days_back + 1)]

    lg = db.collection("leagues").document("lg_mock_draft").get()
    gw = (lg.to_dict() or {}).get("currentGw", 1) if lg.exists else 1
    ws_map = (db.collection("wc_config").document("whoscored_map").get().to_dict() or {}).get("map", {})
    fx_index = _fixture_index(db, None)

    scored_final, scored_live, already = [], [], 0
    seen = set()
    for d in dates:
        try:
            espn_fixtures, _ = fetch_espn_match_stats(d)
        except Exception:
            continue
        for fx in espn_fixtures:
            ref = fx_index.get((fx["homeIso"], fx["awayIso"]))
            if ref is None or ref.id in seen:
                continue
            seen.add(ref.id)
            fdoc = ref.get().to_dict() or {}
            finished = fx["finished"]
            in_play = fx.get("state") == "in"
            if not finished and not in_play:
                continue
            if finished and fdoc.get("scoredFinal"):
                already += 1
                continue  # bookmarked — skip (idempotent optimization)

            ws_id = ws_map.get(str(ref.id))
            try:
                r = None
                if ws_id:
                    try:
                        r = ingest_whoscored_fixture(db, int(ws_id), ref.id, gw)
                    except Exception:
                        # WhoScored RAISES from datacenter IPs (403) — a raise
                        # must mean fallback, never a dropped fixture.
                        r = None
                if not r or r.get("error") or not r.get("playerScoresWritten"):
                    ingest_live(db, gw, d)  # FIFA+ESPN fallback
                    via = "fifa-espn"
                else:
                    via = "whoscored"
            except Exception as exc:
                (scored_final if finished else scored_live).append(
                    {"fixture": ref.id, "error": str(exc)})
                continue

            if finished:
                ref.set({"scoredFinal": True, "scoredAt": _fs.SERVER_TIMESTAMP,
                         "status": "FT"}, merge=True)
                scored_final.append({"fixture": ref.id, "date": d, "via": via})
            else:
                scored_live.append({"fixture": ref.id, "date": d, "via": via})

    # Refresh whole-pool aggregates (season stats + FIFA ownership/price/form)
    # once, after all fixtures — path-independent, so the new Transfers/Compare
    # fields populate whether scoring went via WhoScored or the FIFA fallback.
    aggregates = refresh_pool_aggregates(db)

    db.collection("wc_config").document("scan_state").set(
        {"lastScanAt": _fs.SERVER_TIMESTAMP, "datesScanned": dates,
         "lastFinalScored": [s["fixture"] for s in scored_final]}, merge=True)
    return {"gw": gw, "datesScanned": dates, "newlyFinalized": scored_final,
            "liveUpdated": scored_live, "alreadyBookmarked": already,
            **aggregates}
