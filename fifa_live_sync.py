"""FIFA World Cup fantasy live points + stats ingester.

Free-data pipeline (no paid API):
  * play.fifa.com/json/fantasy/players.json  -> authoritative fantasy POINTS per
    player per round (FIFA's scoring incl. ball recoveries), season totals.
  * ESPN site API                            -> fixture status/scores + per-player
    stat lines (goals, assists, cards, saves, GC) + sub minutes, for the popup.

Writes (idempotent, safe to re-run any time):
  * wc_fixtures/{fid}: status, score, processedForFantasy (fixing pass only)
  * wc_fixtures/{fid}/playerScores/{pid}: {playerId, gw, fantasyPoints, stats{...}}
  * wc_players/{pid}: totalPoints (FIFA season total — includes free agents)
  * leagues/{lid}/gw_history/{uid}_{gw}: LIVE provisional snapshot (players,
    starting, bench, total). finalize_gw() later overwrites with the
    authoritative version via full .set — by design.
  * leagues/{lid}/scores/{gw}: provisional results.{uid}.points (same shape the
    finalizer writes, which fully overwrites per-uid at GW end).

Run:  FS_TOKEN=$(gcloud auth print-access-token) .venv/bin/python fifa_live_sync.py [--force]
Cron: every 10 minutes; exits in <2s (two HEADless reads) when no match is in
the active window (kickoff-15m .. kickoff+3h) and nothing awaits a fixing pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT = "fpl-analyzer-792eb"
DATABASE = "gamedb"
LEAGUES = ["lg_mock_draft"]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

FIFA_PLAYERS = "https://play.fifa.com/json/fantasy/players.json"
FIFA_SQUADS = "https://play.fifa.com/json/fantasy/squads.json"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={eid}"

# ESPN status.type.state: 'pre' | 'in' | 'post'
LIVE_WINDOW_BEFORE = timedelta(minutes=15)
LIVE_WINDOW_AFTER = timedelta(hours=3)
FIXING_DELAY = timedelta(minutes=60)   # mark processedForFantasy this long after FT

# country-name aliases: ESPN/FIFA display name -> our wc_teams name
NAME_ALIASES = {
    "czechia": "czech republic",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "cote d'ivoire": "ivory coast",
    "côte d'ivoire": "ivory coast",
    "cabo verde": "cape verde",
    "cape verde islands": "cape verde",
    "dr congo": "congo dr",
    "democratic republic of the congo": "congo dr",
    "congo dr": "congo dr",
    "usa": "united states",
    "ir iran": "iran",
    "china pr": "china",
    "bosnia-herzegovina": "bosnia and herzegovina",
    "curacao": "curaçao",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def fetch_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def db_client() -> firestore.Client:
    token = os.environ.get("FS_TOKEN")
    if not token:
        sys.exit("FS_TOKEN env var required (gcloud auth print-access-token)")
    return firestore.Client(project=PROJECT, credentials=Credentials(token=token), database=DATABASE)


# ---------------------------------------------------------------- mapping ---

def build_team_name_to_iso(db) -> dict:
    """our team display name (normalized) -> our isoCode."""
    out = {}
    for d in db.collection("wc_teams").stream():
        t = d.to_dict() or {}
        iso = (t.get("isoCode") or t.get("abbr") or d.id or "").upper()
        for key in ("name", "displayName", "teamName"):
            if t.get(key):
                out[norm(t[key])] = iso
    return out


def resolve_iso(display_name: str, name_to_iso: dict) -> str | None:
    n = norm(display_name)
    n = NAME_ALIASES.get(n, n)
    if n in name_to_iso:
        return name_to_iso[n]
    # try alias target normalization round-trip
    for cand, iso in name_to_iso.items():
        if n == cand or n in cand or cand in n:
            return iso
    return None


def build_fifa_player_map(db, fifa_players, fifa_squads, name_to_iso):
    """FIFA player id -> our wc_players id. Match by team + normalized name."""
    squad_iso = {}
    for s in fifa_squads:
        iso = resolve_iso(s.get("name", ""), name_to_iso)
        if iso:
            squad_iso[s["id"]] = iso

    pool_by_team: dict[str, list] = {}
    for d in db.collection("wc_players").stream():
        p = d.to_dict() or {}
        pool_by_team.setdefault((p.get("teamIso") or "").upper(), []).append(
            {"id": int(d.id), "n": norm(p.get("name", ""))})

    fifa_map, unmatched = {}, []
    for fp in fifa_players:
        iso = squad_iso.get(fp.get("squadId"))
        if not iso:
            continue
        cands = pool_by_team.get(iso, [])
        names = [norm(fp.get("knownName") or ""),
                 norm(f"{fp.get('firstName','')} {fp.get('lastName','')}"),
                 norm(fp.get("lastName") or "")]
        names = [n for n in names if n]
        best, best_score = None, 0.0
        for c in cands:
            for n in names:
                if not n:
                    continue
                if n == c["n"]:
                    best, best_score = c, 1.0
                    break
                sc = SequenceMatcher(None, n, c["n"]).ratio()
                # surname containment is a strong signal
                if names[-1] and (names[-1] in c["n"] or c["n"].endswith(names[-1])):
                    sc = max(sc, 0.86)
                if sc > best_score:
                    best, best_score = c, sc
            if best_score == 1.0:
                break
        if best and best_score >= 0.78:
            fifa_map[fp["id"]] = best["id"]
        else:
            unmatched.append((fp.get("knownName") or fp.get("lastName"), iso))
    return fifa_map, unmatched


# ----------------------------------------------------------------- fixtures ---

def load_gw_fixtures(db, gw):
    out = []
    for d in db.collection("wc_fixtures").where("gw", "==", gw).stream():
        f = d.to_dict() or {}
        f["_id"] = d.id
        out.append(f)
    return out


def espn_events(dates):
    evs = []
    for date in dates:
        try:
            data = fetch_json(ESPN_SCOREBOARD.format(date=date))
        except Exception as exc:
            print(f"[warn] espn scoreboard {date}: {exc}")
            continue
        evs.extend(data.get("events") or [])
    return evs


def match_event_to_fixture(ev, fixtures, name_to_iso):
    comp = (ev.get("competitions") or [{}])[0]
    sides = comp.get("competitors") or []
    if len(sides) != 2:
        return None
    isos = set()
    for s in sides:
        iso = resolve_iso(s.get("team", {}).get("displayName", ""), name_to_iso)
        if iso:
            isos.add(iso)
    for f in fixtures:
        pair = {(f.get("homeTeam") or {}).get("isoCode"), (f.get("awayTeam") or {}).get("isoCode")}
        if pair == isos:
            return f
    return None


# ------------------------------------------------------------------- stats ---

def espn_player_stats(eid, name_to_iso):
    """eid -> {our-iso: {norm_name: stats_dict}}, plus per-team goals conceded."""
    data = fetch_json(ESPN_SUMMARY.format(eid=eid))
    out, conceded = {}, {}
    # minutes from sub events
    subs = []  # (clock_min, in_name, out_name)
    for ev in (data.get("keyEvents") or []):
        if "Substitution" in (ev.get("type", {}).get("text") or ""):
            try:
                clock = int(re.match(r"(\d+)", ev.get("clock", {}).get("displayValue", "90")).group(1))
            except Exception:
                clock = 90
            ath = ev.get("participants") or []
            in_n = norm(ath[0].get("athlete", {}).get("displayName", "")) if len(ath) > 0 else ""
            out_n = norm(ath[1].get("athlete", {}).get("displayName", "")) if len(ath) > 1 else ""
            subs.append((clock, in_n, out_n))

    header_comp = (data.get("header", {}).get("competitions") or [{}])[0]
    score_by_team = {}
    for c in header_comp.get("competitors") or []:
        iso = resolve_iso(c.get("team", {}).get("displayName", ""), name_to_iso)
        if iso:
            score_by_team[iso] = int(c.get("score") or 0)
    isos = list(score_by_team)
    if len(isos) == 2:
        conceded[isos[0]] = score_by_team[isos[1]]
        conceded[isos[1]] = score_by_team[isos[0]]

    for r in (data.get("rosters") or []):
        iso = resolve_iso(r.get("team", {}).get("displayName", ""), name_to_iso)
        if not iso:
            continue
        team_stats = {}
        for entry in r.get("roster") or []:
            ath = entry.get("athlete", {})
            nm = norm(ath.get("displayName", ""))
            sd = {s.get("name"): s.get("value") for s in (entry.get("stats") or [])}
            played = bool(entry.get("starter")) or (sd.get("subIns") or 0) > 0 or (sd.get("appearances") or 0) > 0
            minutes = 0
            if entry.get("starter"):
                minutes = 90
                for clock, in_n, out_n in subs:
                    if out_n and out_n == nm:
                        minutes = min(minutes, clock)
            elif (sd.get("subIns") or 0) > 0:
                minutes = 30
                for clock, in_n, out_n in subs:
                    if in_n and in_n == nm:
                        minutes = max(0, 90 - clock)
            team_stats[nm] = {
                "played": played,
                "minutes": int(minutes),
                "goals": int(sd.get("totalGoals") or 0),
                "assists": int(sd.get("goalAssists") or 0),
                "yellowCards": int(sd.get("yellowCards") or 0),
                "redCards": int(sd.get("redCards") or 0),
                "saves": int(sd.get("saves") or 0),
                "ownGoals": int(sd.get("ownGoals") or 0),
                "shots": int(sd.get("totalShots") or 0),
                "shotsOnTarget": int(sd.get("shotsOnTarget") or 0),
                "foulsCommitted": int(sd.get("foulsCommitted") or 0),
            }
        out[iso] = team_stats
    return out, conceded


# -------------------------------------------------------------------- main ---

def main():
    force = "--force" in sys.argv
    now = datetime.now(timezone.utc)
    db = db_client()

    league0 = db.collection("leagues").document(LEAGUES[0]).get().to_dict() or {}
    gw = league0.get("currentGw") or 1
    fixtures = load_gw_fixtures(db, gw)

    def kdt(f):
        k = f.get("kickoff")
        return k if isinstance(k, datetime) else None

    active = [f for f in fixtures if kdt(f) and kdt(f) - LIVE_WINDOW_BEFORE <= now <= kdt(f) + LIVE_WINDOW_AFTER]
    pending_fix = [f for f in fixtures if f.get("status") in ("FT", "AET", "PEN") and not f.get("processedForFantasy")]
    if not force and not active and not pending_fix:
        print(f"[{now:%H:%M}] idle — no live window, nothing pending. exit.")
        return

    name_to_iso = build_team_name_to_iso(db)

    # ---- FIFA: points (the authoritative fantasy score) ----
    fifa_players = fetch_json(FIFA_PLAYERS)
    fifa_squads = fetch_json(FIFA_SQUADS)
    fifa_players = fifa_players if isinstance(fifa_players, list) else fifa_players.get("players", [])
    fifa_squads =