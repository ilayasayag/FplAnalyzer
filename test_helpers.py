#!/usr/bin/env python3
"""Shared test infrastructure for the WC2026 scoring suite (EP6-W1).

This module owns:

  * the in-memory, path-keyed **fake Firestore** (``_Snap/_Doc/_Coll/FakeDB``)
    originally written inline in ``test_aggregate.py`` (EP2). It supports the
    operations the scoring pipeline calls against the client:
    ``collection().document().get()/.set(merge=)/.update()``, collection
    ``.get()``/``.stream()``, ``.where(...)`` chains, a ``.batch()`` writer,
    ``collection_group(...)``, dotted-path merges, and interception of the
    ``firestore.Increment`` sentinel so repeated increments accumulate.

  * small **seed helpers** (``seed_player``/``seed_fixture``/``player_block``/…)
    used to build api-sports-shaped raw stats for ``process_fixture``.

  * a reusable, realistic **seeded dataset** (``build_seeded_db``) covering all
    four positions, two fixtures, and one league with squads + lineups + a H2H
    schedule for two managers — the substrate the EP6 e2e reconciliation test
    runs against.

``test_aggregate.py`` (EP2) imports the fake + its seed helpers from here so
there is a single source of truth and EP2 stays green.

NOT modelled here: the full ``finalize_gw`` flow (knockout seeding, elimination
detection, transfer-window/standings side effects) is too coupled to real
client semantics. The e2e test exercises the layers that DO run against the
fake — ``process_fixture`` -> playerScores -> ``wc_players.totalPoints`` and
``_snapshot_gw_history`` with directly-seeded lineups/scores — exactly as EP2's
``test_aggregate.py`` scoped it. See the e2e test module's notes.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from google.cloud.firestore_v1 import Increment  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory path-keyed fake Firestore
# ---------------------------------------------------------------------------

def _apply_value(store, path, field, value):
    """Write one field onto store[path], handling Increment + dotted paths."""
    doc = store.setdefault(path, {})
    parts = field.split(".")
    target = doc
    for p in parts[:-1]:
        target = target.setdefault(p, {})
    leaf = parts[-1]
    if isinstance(value, Increment):
        target[leaf] = (target.get(leaf) or 0) + value.value
    else:
        target[leaf] = value


def _merge_into(store, path, data, merge):
    """Mimic Firestore set(): top-level merge, Increment sentinels resolved."""
    if not merge:
        # Overwrite — but still resolve any Increment against nothing (=> value).
        store[path] = {}
    for field, value in data.items():
        if isinstance(value, dict) and not isinstance(value, Increment):
            # Nested dict merge (used by finalize results.{uid} merges).
            existing = store.setdefault(path, {})
            _deep_merge(existing, {field: value})
        else:
            _apply_value(store, path, field, value)


def _deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, Increment):
            dst[k] = (dst.get(k) or 0) + v.value
        elif isinstance(v, dict):
            node = dst.get(k)
            if not isinstance(node, dict):
                node = {}
                dst[k] = node
            _deep_merge(node, v)
        else:
            dst[k] = v


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None

    @property
    def reference(self):
        return self._ref

    def _bind(self, ref):
        self._ref = ref
        return self


class _Doc:
    def __init__(self, store, path):
        self.store, self.path = store, path

    @property
    def id(self):
        return self.path.rsplit("/", 1)[-1]

    @property
    def parent(self):
        # The collection that holds this document (mirrors DocumentReference.parent).
        return _Coll(self.store, self.path.rsplit("/", 1)[0])

    def collection(self, name):
        return _Coll(self.store, f"{self.path}/{name}")

    def get(self):
        return _Snap(self.id, self.store.get(self.path))._bind(self)

    def set(self, data, merge=False):
        _merge_into(self.store, self.path, data, merge)

    def update(self, patch):
        # update == merge semantics for our purposes (creates if missing).
        _merge_into(self.store, self.path, patch, merge=True)

    def delete(self):
        self.store.pop(self.path, None)


class _Coll:
    def __init__(self, store, path):
        self.store, self.path = store, path

    @property
    def parent(self):
        # The document that holds this subcollection, or None for a top-level
        # collection (mirrors CollectionReference.parent). Enables
        # ``snap.reference.parent.parent`` collection-group -> parent-doc walks.
        if "/" not in self.path:
            return None
        return _Doc(self.store, self.path.rsplit("/", 1)[0])

    def document(self, doc_id=None):
        if doc_id is None:
            n = sum(1 for k in self.store if k.startswith(self.path + "/"))
            doc_id = f"auto-{n}"
        return _Doc(self.store, f"{self.path}/{doc_id}")

    def _children(self):
        depth = self.path.count("/") + 1
        for key, data in list(self.store.items()):
            if key.startswith(self.path + "/") and key.count("/") == depth:
                doc = _Doc(self.store, key)
                yield _Snap(key.rsplit("/", 1)[-1], data)._bind(doc)

    def stream(self):
        yield from self._children()

    def get(self):
        return list(self._children())

    def where(self, field, op, value):
        return _Query([s for s in self._children()
                       if _matches(s.to_dict() or {}, field, op, value)])


def _matches(data, field, op, value):
    """Minimal Firestore filter support for the fake DB: ``==`` and ``in``."""
    fv = (data or {}).get(field)
    if op == "==":
        return fv == value
    if op == "in":
        return fv in value
    raise AssertionError(f"unsupported op {op!r}")


class _Query:
    def __init__(self, snaps):
        self._snaps = snaps

    def where(self, field, op, value):
        return _Query([s for s in self._snaps
                       if _matches(s.to_dict() or {}, field, op, value)])

    def get(self):
        return list(self._snaps)


class _Batch:
    def __init__(self, store):
        self.store = store
        self._ops = []

    def set(self, ref, data, merge=False):
        self._ops.append(("set", ref.path, data, merge))

    def update(self, ref, patch):
        self._ops.append(("update", ref.path, patch, True))

    def delete(self, ref):
        self._ops.append(("delete", ref.path, None, False))

    def commit(self):
        for op, path, data, merge in self._ops:
            if op == "delete":
                self.store.pop(path, None)
            else:
                _merge_into(self.store, path, data, merge)
        self._ops = []


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Coll(self.store, name)

    def collection_group(self, name):
        # All docs whose immediate parent collection segment == name.
        snaps = []
        for key, data in list(self.store.items()):
            segs = key.split("/")
            if len(segs) >= 2 and segs[-2] == name:
                snaps.append(_Snap(segs[-1], data)._bind(_Doc(self.store, key)))
        return _Query(snaps)

    def batch(self):
        return _Batch(self.store)


# ---------------------------------------------------------------------------
# Seed helpers — build raw api-sports-shaped stats for process_fixture
# ---------------------------------------------------------------------------

def player_block(pid, name, minutes=90, goals=0, assists=0, rating="7.0",
                 saves=0, owngoals=0, yellow=0, red=0, pen_missed=0,
                 pen_saved=0, tackles=None):
    """One api-sports player stat block. Mirrors what wc_api returns."""
    tackles = tackles or {"total": 0, "interceptions": 0, "blocks": 0}
    return {
        "player": {"id": pid, "name": name},
        "statistics": [{
            "games": {"minutes": minutes, "rating": rating},
            "goals": {"total": goals, "assists": assists,
                      "saves": saves, "owngoals": owngoals},
            "cards": {"yellow": yellow, "red": red},
            "penalty": {"missed": pen_missed, "saved": pen_saved},
            "tackles": dict(tackles),
        }],
    }


def raw_stats(home_team, away_team, home_players, away_players):
    return [
        {"team": {"id": home_team}, "players": home_players},
        {"team": {"id": away_team}, "players": away_players},
    ]


def seed_fixture(db, fid, gw, home_team, away_team, home_goals, away_goals):
    db.store[f"wc_fixtures/{fid}"] = {
        "id": fid, "gw": gw,
        "homeTeam": {"id": home_team}, "awayTeam": {"id": away_team},
        "score": {"home": home_goals, "away": away_goals},
        "processedForFantasy": False,
    }


def seed_players(db, players):
    """players: {pid: position int}"""
    for pid, pos in players.items():
        db.store[f"wc_players/{pid}"] = {"id": pid, "position": pos, "totalPoints": 0}


def seed_rules(db, rules):
    """Seed wc_config/tournament.rules so process_fixture reads custom scoring."""
    db.store["wc_config/tournament"] = {"rules": rules}


def sum_total_points(db):
    return sum((v.get("totalPoints") or 0)
               for k, v in db.store.items() if k.startswith("wc_players/"))


def sum_player_scores(db):
    total = 0
    for k, v in db.store.items():
        if "/playerScores/" in k:
            total += v.get("fantasyPoints", 0)
    return total


# ---------------------------------------------------------------------------
# Shared seeded dataset (EP6-W1)
# ---------------------------------------------------------------------------

# Player ids grouped by the four positions, two national teams (10 home, 20
# away in fixture A; 30 vs 40 in fixture B). Positions: 1=GK 2=DEF 3=MID 4=FWD.
SEED_POSITIONS = {
    # Team 10 (fixture A home)
    101: 1, 102: 2, 103: 2, 104: 3, 105: 3, 106: 4,
    # Team 20 (fixture A away)
    201: 1, 202: 2, 203: 3, 204: 3, 205: 4, 206: 4,
    # Team 30 (fixture B home)
    301: 1, 302: 2, 303: 3, 304: 4,
    # Team 40 (fixture B away)
    401: 1, 402: 2, 403: 3, 404: 4,
}


def _fixture_a_raw():
    """Fixture A: team 10 beats team 20, 2-0 (GW1).

    Shaped so the new engine rules are all observable:
      - a DEF over the DefCon threshold (102: 10 actions) and one under (103)
      - a MID over the threshold (104: 12 actions) and one under (105)
      - a goal scorer (106 FWD x2), an assister (104)
      - a sub-60 appearance (203) and a 0-minute no-show (206)
      - a clean rating spread for the 3/2/1 bonus
    """
    home = [
        player_block(101, "GK Ten", minutes=90, rating="7.0"),
        player_block(102, "Def Ten A", minutes=90, rating="8.5",
                     tackles={"total": 5, "interceptions": 3, "blocks": 2}),  # 10 -> DefCon
        player_block(103, "Def Ten B", minutes=90, rating="6.5",
                     tackles={"total": 2, "interceptions": 1, "blocks": 0}),  # 3 -> none
        player_block(104, "Mid Ten A", minutes=90, assists=1, rating="9.0",
                     tackles={"total": 6, "interceptions": 4, "blocks": 2}),  # 12 -> DefCon
        player_block(105, "Mid Ten B", minutes=70, rating="6.8",
                     tackles={"total": 3, "interceptions": 1, "blocks": 0}),  # 4 -> none
        player_block(106, "Fwd Ten", minutes=90, goals=2, rating="8.8"),
    ]
    away = [
        player_block(201, "GK Twenty", minutes=90, rating="6.0", saves=4),
        player_block(202, "Def Twenty", minutes=90, rating="6.2",
                     tackles={"total": 4, "interceptions": 2, "blocks": 1}),
        player_block(203, "Mid Twenty A", minutes=45, rating="6.4"),  # sub-60
        player_block(204, "Mid Twenty B", minutes=90, rating="6.6",
                     tackles={"total": 5, "interceptions": 5, "blocks": 3}),  # 13 -> DefCon
        player_block(205, "Fwd Twenty A", minutes=90, rating="6.1"),
        player_block(206, "Fwd Twenty B", minutes=0, rating="0"),  # no-show
    ]
    return raw_stats(10, 20, home, away)


def _fixture_b_raw():
    """Fixture B: team 30 vs team 40, 1-1 (GW1)."""
    home = [
        player_block(301, "GK Thirty", minutes=90, rating="6.7", saves=3),
        player_block(302, "Def Thirty", minutes=90, rating="7.2",
                     tackles={"total": 5, "interceptions": 4, "blocks": 2}),  # 11 -> DefCon
        player_block(303, "Mid Thirty", minutes=90, assists=1, rating="7.8",
                     tackles={"total": 4, "interceptions": 2, "blocks": 1}),  # 7 -> none
        player_block(304, "Fwd Thirty", minutes=90, goals=1, rating="8.0"),
    ]
    away = [
        player_block(401, "GK Forty", minutes=90, rating="6.5", saves=2),
        player_block(402, "Def Forty", minutes=90, rating="6.3", yellow=1,
                     tackles={"total": 3, "interceptions": 1, "blocks": 0}),
        player_block(403, "Mid Forty", minutes=80, rating="6.9",
                     tackles={"total": 7, "interceptions": 5, "blocks": 1}),  # 13 -> DefCon
        player_block(404, "Fwd Forty", minutes=90, goals=1, rating="7.5"),
    ]
    return raw_stats(30, 40, home, away)


# Raw stats for each fixture, keyed by fixture id.
SEED_FIXTURE_RAW = {
    9001: _fixture_a_raw(),
    9002: _fixture_b_raw(),
}

# Two managers' squads (15-ish ids drawn from both fixtures) and their GW1
# lineups (starting + bench). Kept simple/valid; the e2e test seeds the
# scores/results directly so it does not depend on finalize_gw running.
SEED_MANAGERS = {
    "u_alice": {
        "squad": [101, 102, 103, 104, 105, 106, 201, 202],
        "starting": [101, 102, 103, 104, 105, 106],
        "bench": [201, 202],
    },
    "u_bob": {
        "squad": [301, 302, 303, 304, 401, 402, 403, 404],
        "starting": [301, 302, 303, 304, 401, 402],
        "bench": [403, 404],
    },
}

SEED_LID = "lg_e2e"


def build_seeded_db(rules=None):
    """Build a realistic seeded fake Firestore for the e2e reconciliation test.

    Seeds:
      - ``wc_players`` for all four positions across two fixtures' worth of
        players (``SEED_POSITIONS``)
      - two ``wc_fixtures`` (GW1), each with ``build_team_raw_stats``-shaped
        raw stats available via ``SEED_FIXTURE_RAW``
      - one league (``SEED_LID``) with two managers, their squads and GW1
        lineups, members docs, and a H2H schedule

    Returns the ``FakeDB``. ``process_fixture`` / ``_snapshot_gw_history`` are
    NOT run here — the test drives those so it can assert at each layer.

    No active leagues are flagged ``group_phase``/``knockout`` by default so the
    live ``_propagate_to_leagues`` accrual is a harmless no-op and the test
    focuses on the authoritative aggregation + snapshot invariants.
    """
    db = FakeDB()
    seed_players(db, SEED_POSITIONS)
    if rules is not None:
        seed_rules(db, rules)

    # Fixtures (GW1). Scores chosen to match the raw stats above.
    seed_fixture(db, 9001, 1, 10, 20, 2, 0)
    seed_fixture(db, 9002, 1, 30, 40, 1, 1)

    # League metadata + members + squads + lineups + schedule.
    db.store[f"leagues/{SEED_LID}"] = {
        "leagueId": SEED_LID, "status": "pre_season", "currentGw": 1,
        "leaguePhaseGws": [1, 2, 3], "knockoutStartGw": 4,
    }
    schedule_matches = [{"home": "u_alice", "away": "u_bob"}]
    db.store[f"leagues/{SEED_LID}/schedule/1"] = {"gw": 1, "matches": schedule_matches}

    for uid, m in SEED_MANAGERS.items():
        db.store[f"leagues/{SEED_LID}/members/{uid}"] = {
            "displayName": uid, "teamName": f"{uid} XI",
        }
        db.store[f"leagues/{SEED_LID}/squads/{uid}"] = {
            "players": [{"playerId": pid, "position": SEED_POSITIONS[pid]}
                        for pid in m["squad"]],
        }
        db.store[f"leagues/{SEED_LID}/lineups/{uid}_1"] = {
            "starting": list(m["starting"]),
            "bench": list(m["bench"]),
            "locked": True,
            "autoSubsMade": [],
        }
    return db
