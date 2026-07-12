#!/usr/bin/env python3
"""Unit tests for the GW7 knockout LIVE swap-draft (``wc_ko_draft``).

Pure unit tests — no emulator, no prod. A small in-memory fake Firestore
(honouring the ``@firestore.transactional`` contract the engine uses) models
exactly what ``KnockoutSwapDraftEngine`` touches: ``leagues/{lid}``,
``.../members/{uid}``, ``.../squads/{uid}``, ``.../ko_draft/{config,state}``,
``.../transactions``, and top-level ``wc_players/{id}``.

Run:
    .venv/bin/python -m pytest test_wc_ko_draft.py -v

Covers: rehearsal never writes squads/members; straight seed-order rotation;
Pass shrinks the rotation and completes when all pass; swap validation
(OUT-owned / IN-free / nation-eliminated / quota); a dropped player returns to
the pool and can be re-picked; live mode empties eliminated squads and writes
the picker's squad; eliminated squads' players are in the pool.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_ko_draft import KnockoutSwapDraftEngine  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory fake Firestore (honours @transactional via the fixture below)
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        if self._data is None:
            return None
        d = dict(self._data)
        if "players" in d:
            d["players"] = [dict(p) for p in d["players"]]
        if "swaps" in d:
            d["swaps"] = [dict(s) for s in d["swaps"]]
        return d


class FakeDocRef:
    def __init__(self, store, key, doc_id):
        self._store = store
        self._key = key
        self._id = doc_id

    @property
    def id(self):
        return self._id

    def get(self, transaction=None):
        data = self._store.get(self._key)
        if data is not None:
            data = dict(data)
            if "players" in data:
                data["players"] = [dict(p) for p in data["players"]]
        return FakeSnapshot(self._id, data)

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)

    def update(self, patch):
        self._store.setdefault(self._key, {}).update(patch)

    def delete(self):
        self._store.pop(self._key, None)

    def collection(self, name):
        return FakeCollectionRef(self._store, f"{self._key}/{name}")


class FakeCollectionRef:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix
        self._auto = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._auto += 1
            doc_id = f"auto-{self._auto}"
        return FakeDocRef(self._store, f"{self._prefix}/{doc_id}", doc_id)

    def get(self):
        docs = []
        plen = len(self._prefix) + 1
        for key, data in self._store.items():
            if not key.startswith(self._prefix + "/"):
                continue
            rest = key[plen:]
            if "/" in rest:
                continue
            docs.append(FakeSnapshot(rest, data))
        return docs


class FakeTransaction:
    def __init__(self, store):
        self._store = store
        self._writes = []

    def _begin(self):
        self._writes = []

    def update(self, ref, patch):
        self._writes.append((ref, dict(patch)))

    def _commit(self):
        for ref, patch in self._writes:
            ref.update(patch)
        self._writes = []

    def _rollback(self):
        self._writes = []


class FakeDB:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return FakeCollectionRef(self._store, name)

    def transaction(self):
        return FakeTransaction(self._store)


import google.cloud.firestore_v1 as _fs  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_transactional(monkeypatch):
    def fake_transactional(fn):
        def wrapper(txn, *args, **kwargs):
            txn._begin()
            try:
                result = fn(txn, *args, **kwargs)
            except Exception:
                txn._rollback()
                raise
            txn._commit()
            return result
        return wrapper

    monkeypatch.setattr(_fs, "transactional", fake_transactional)
    # wc_ko_draft imports SERVER_TIMESTAMP at module load, but writes it as a
    # plain value into the fake store — nothing to patch there.
    yield


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

LID = "lg_test"
MANAGERS = ["m1", "m2", "m3", "m4", "m5", "m6"]
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
# Position layout for the 15 base-squad slots (2/5/5/3).
LAYOUT = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]


def _player_doc(pid, pos, *, eliminated=False, team=None):
    return {
        "id": pid,
        "name": f"P{pid}",
        "position": pos,
        "positionName": POS[pos],
        "teamId": team if team is not None else pid,  # unique nation by default
        "teamName": f"N{team if team is not None else pid}",
        "teamIso": "",
        "eliminated": eliminated,
    }


def _squad_player(pid, pos, *, team=None):
    return {
        "playerId": pid,
        "position": pos,
        "positionName": POS[pos],
        "name": f"P{pid}",
        "teamId": team if team is not None else pid,
        "teamName": f"N{team if team is not None else pid}",
        "teamIso": "",
        "eliminated": False,
    }


def _seed(db, *, free_agents=None):
    """6 managers, each a legal 2/5/5/3 squad with disjoint ids; a pool of
    free-agent wc_players. wc_players holds EVERY player so swap-ins resolve."""
    store = db._store
    store[f"leagues/{LID}"] = {"adminUid": "m1", "knockoutStartGw": 7}

    # wc_players + squads
    for idx, m in enumerate(MANAGERS, start=1):
        store[f"leagues/{LID}/members/{m}"] = {"displayName": m}
        players = []
        for slot, pos in enumerate(LAYOUT):
            pid = idx * 100 + slot
            players.append(_squad_player(pid, pos))
            store[f"wc_players/{pid}"] = _player_doc(pid, pos)
        store[f"leagues/{LID}/squads/{m}"] = {"players": players}

    # Free-agent pool (unowned). Default: a few of each position, all alive,
    # plus one nation-eliminated DEF that must be rejected as an IN.
    fa = free_agents or [
        (900, 1), (901, 2), (902, 2), (903, 3), (904, 3), (905, 4), (906, 4),
    ]
    for pid, pos in fa:
        store[f"wc_players/{pid}"] = _player_doc(pid, pos)
    store["wc_players/999"] = _player_doc(999, 2, eliminated=True)  # nation out
    return db


def _engine(db):
    return KnockoutSwapDraftEngine(db, wc_client=None)


def _fresh(**cfg_kwargs):
    db = FakeDB()
    _seed(db)
    eng = _engine(db)
    cfg = dict(eliminated_uids=["m5", "m6"], order=["m1", "m2", "m3", "m4"],
               rehearsal=True, pick_timer=60)
    cfg.update(cfg_kwargs)
    eng.set_config(LID, **cfg)
    eng.start(LID)
    return db, eng


# helper: a legal same-position swap-in for a given squad slot
def _def_out(manager_idx):  # a DEF the manager owns (slot 2)
    return manager_idx * 100 + 2


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_config_validation():
    db = FakeDB(); _seed(db); eng = _engine(db)
    with pytest.raises(ValueError):  # overlap picker/eliminated
        eng.set_config(LID, eliminated_uids=["m1"], order=["m1", "m2"])
    with pytest.raises(ValueError):  # unknown manager
        eng.set_config(LID, eliminated_uids=["mX"], order=["m1", "m2"])


def test_rehearsal_never_writes_squads_or_members():
    db, eng = _fresh()
    base_m1 = [dict(p) for p in db._store["leagues/lg_test/squads/m1"]["players"]]

    # m1 makes a legal DEF->DEF swap (out a DEF, in FA 901 a DEF).
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))

    # Squad doc UNCHANGED (rehearsal writes only ko_draft/*).
    assert db._store["leagues/lg_test/squads/m1"]["players"] == base_m1
    # Members not flagged eliminated.
    assert "eliminated" not in db._store["leagues/lg_test/members/m5"]
    assert db._store["leagues/lg_test/squads/m5"]["players"]  # not emptied

    # But the swap IS recorded in state and reflected in the effective squad.
    st = eng.get_state(LID)
    assert st["swaps"][0]["playerIn"] == 901
    eff_ids = {p["playerId"] for p in st["squads"]["m1"]}
    assert 901 in eff_ids and _def_out(1) not in eff_ids


def test_straight_seed_order_rotation():
    db, eng = _fresh()
    st = eng.get_state(LID)
    assert st["currentDrafter"] == "m1"
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    assert eng.get_state(LID)["currentDrafter"] == "m2"
    eng.make_swap(LID, "m2", player_in=902, player_out=_def_out(2))
    assert eng.get_state(LID)["currentDrafter"] == "m3"
    eng.make_swap(LID, "m3", player_in=903, player_out=(3 * 100 + 7))  # MID out
    assert eng.get_state(LID)["currentDrafter"] == "m4"
    eng.make_swap(LID, "m4", player_in=904, player_out=(4 * 100 + 7))  # MID out
    # wraps back to the top seed
    assert eng.get_state(LID)["currentDrafter"] == "m1"


def test_not_your_turn():
    db, eng = _fresh()
    with pytest.raises(ValueError, match="Not your turn"):
        eng.make_swap(LID, "m2", player_in=901, player_out=_def_out(2))


def test_pass_shrinks_rotation_and_completes():
    db, eng = _fresh()
    eng.pass_turn(LID, "m1")
    assert eng.get_state(LID)["currentDrafter"] == "m2"
    assert "m1" not in eng.get_state(LID)["activePickers"]
    eng.pass_turn(LID, "m2")
    eng.pass_turn(LID, "m3")
    res = eng.pass_turn(LID, "m4")
    assert res["complete"] is True
    st = eng.get_state(LID)
    assert st["status"] == "complete"
    assert st["currentDrafter"] is None


def test_pass_then_next_can_pick():
    db, eng = _fresh()
    eng.pass_turn(LID, "m1")           # m1 done -> m2 on clock
    eng.make_swap(LID, "m2", player_in=901, player_out=_def_out(2))
    assert eng.get_state(LID)["currentDrafter"] == "m3"  # m1 skipped forever


def test_undo_reverts_last_swap_and_returns_clock():
    db, eng = _fresh()
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    assert eng.get_state(LID)["currentDrafter"] == "m2"
    res = eng.undo_last_swap(LID)
    assert res["undone"]["playerIn"] == 901 and res["undone"]["uid"] == "m1"
    st = eng.get_state(LID)
    assert st["currentDrafter"] == "m1"          # clock handed back to m1
    assert st["status"] == "active"
    assert 901 not in st["ownedPlayerIds"]        # the pick is gone
    assert _def_out(1) in st["ownedPlayerIds"]    # the dropped player is restored
    assert len(st["swaps"]) == 0


def test_undo_repeatable_to_start_then_errors():
    db, eng = _fresh()
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    eng.make_swap(LID, "m2", player_in=902, player_out=_def_out(2))
    eng.undo_last_swap(LID)                        # undo m2
    assert eng.get_state(LID)["currentDrafter"] == "m2"
    eng.undo_last_swap(LID)                        # undo m1 (back to start)
    st = eng.get_state(LID)
    assert st["currentDrafter"] == "m1"
    assert len(st["swaps"]) == 0
    with pytest.raises(ValueError):
        eng.undo_last_swap(LID)                    # nothing left to undo


def test_undo_reopens_completed_draft():
    db, eng = _fresh()
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))  # clock -> m2
    eng.pass_turn(LID, "m2"); eng.pass_turn(LID, "m3")
    eng.pass_turn(LID, "m4"); eng.pass_turn(LID, "m1")               # all passed
    assert eng.get_state(LID)["status"] == "complete"
    eng.undo_last_swap(LID)                        # undo m1's pick -> reopen
    st = eng.get_state(LID)
    assert st["status"] == "active"
    assert st["currentDrafter"] == "m1" and "m1" in st["activePickers"]


def test_swap_out_not_owned():
    db, eng = _fresh()
    with pytest.raises(ValueError, match="PLAYER_OUT_NOT_OWNED"):
        eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(2))  # m2's DEF


def test_swap_in_already_owned():
    db, eng = _fresh()
    # IN = a DEF owned by picker m2 -> not a free agent.
    with pytest.raises(ValueError, match="PLAYER_ALREADY_OWNED"):
        eng.make_swap(LID, "m1", player_in=_def_out(2), player_out=_def_out(1))


def test_swap_in_nation_eliminated():
    db, eng = _fresh()
    with pytest.raises(ValueError, match="PLAYER_TEAM_ELIMINATED"):
        eng.make_swap(LID, "m1", player_in=999, player_out=_def_out(1))


def test_swap_position_quota_violation():
    db, eng = _fresh()
    # OUT a DEF, IN a GK -> squad becomes 3 GK / 4 DEF -> rejected.
    with pytest.raises(ValueError, match="POSITION_QUOTA_VIOLATED"):
        eng.make_swap(LID, "m1", player_in=900, player_out=_def_out(1))


def test_no_nation_cap_in_knockout():
    # The knockout draft intentionally has NO per-nation cap (group-stage squads
    # already concentrate nations as teams are eliminated). A swap that pushes a
    # nation past 3 must SUCCEED.
    db = FakeDB(); _seed(db); eng = _engine(db)
    squad = db._store["leagues/lg_test/squads/m1"]["players"]
    mids = [p for p in squad if p["position"] == 3]
    for p in mids[:3]:
        p["teamId"] = 50
        db._store[f"wc_players/{p['playerId']}"]["teamId"] = 50
    db._store["wc_players/950"] = _player_doc(950, 3, team=50)
    eng.set_config(LID, eliminated_uids=["m5", "m6"], order=["m1", "m2", "m3", "m4"])
    eng.start(LID)
    other_mid = mids[3]["playerId"]
    eng.make_swap(LID, "m1", player_in=950, player_out=other_mid)  # 4 from nation 50 — allowed
    assert 950 in eng.get_state(LID)["ownedPlayerIds"]


def test_dropped_player_returns_to_pool():
    db, eng = _fresh()
    dropped = _def_out(1)  # a DEF m1 owns
    eng.make_swap(LID, "m1", player_in=901, player_out=dropped)
    st = eng.get_state(LID)
    assert dropped not in st["ownedPlayerIds"]      # back in the pool
    assert 901 in st["ownedPlayerIds"]              # the FA now owned
    # m2 can pick the dropped player up (same-position DEF swap).
    eng.make_swap(LID, "m2", player_in=dropped, player_out=_def_out(2))
    assert dropped in {p["playerId"] for p in eng.get_state(LID)["squads"]["m2"]}


def test_eliminated_squads_players_in_pool():
    db, eng = _fresh()
    st = eng.get_state(LID)
    m5_players = {p["playerId"] for p in db._store["leagues/lg_test/squads/m5"]["players"]}
    # None of the eliminated manager's players are owned by a picker => all free.
    assert not (m5_players & set(st["ownedPlayerIds"]))


def test_go_live_eliminates_and_writes_squads():
    db = FakeDB(); _seed(db); eng = _engine(db)
    eng.set_config(LID, eliminated_uids=["m5", "m6"], order=["m1", "m2", "m3", "m4"],
                   rehearsal=False)
    eng.start(LID)
    # Eliminated squads emptied + flagged for real.
    assert db._store["leagues/lg_test/squads/m5"]["players"] == []
    assert db._store["leagues/lg_test/members/m5"]["eliminated"] is True
    # Seed pick order persisted as waiverPriority (seed 1 first).
    assert db._store["leagues/lg_test/members/m1"]["waiverPriority"] == 1
    # A live swap writes the real squad.
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    ids = {p["playerId"] for p in db._store["leagues/lg_test/squads/m1"]["players"]}
    assert 901 in ids and _def_out(1) not in ids


def test_idempotent_swap():
    db, eng = _fresh()
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1), idempotency_key="k1")
    # Same key re-fired (e.g. network retry): must not double-apply or error.
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1), idempotency_key="k1")
    st = eng.get_state(LID)
    assert len(st["swaps"]) == 1
    assert st["currentDrafter"] == "m2"  # only advanced once


def test_reset_keeps_config_wipes_state():
    db, eng = _fresh()
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    eng.reset(LID)
    st = eng.get_state(LID)
    assert st["status"] == "pending"
    assert st["config"]["order"] == ["m1", "m2", "m3", "m4"]  # config survives


def test_start_takes_backup():
    db, eng = _fresh()
    bk = db._store.get("leagues/lg_test/ko_draft/backup")
    assert bk is not None
    # Every squad + member captured before the draft touched anything.
    assert set(bk["squads"].keys()) == set(MANAGERS)
    assert len(bk["squads"]["m5"]) == 15


def test_revert_restores_live_draft():
    db = FakeDB(); _seed(db); eng = _engine(db)
    m1_before = [dict(p) for p in db._store["leagues/lg_test/squads/m1"]["players"]]
    m5_before = [dict(p) for p in db._store["leagues/lg_test/squads/m5"]["players"]]
    eng.set_config(LID, eliminated_uids=["m5", "m6"], order=["m1", "m2", "m3", "m4"], rehearsal=False)
    eng.start(LID)
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    # Live draft mutated real data:
    assert db._store["leagues/lg_test/squads/m5"]["players"] == []
    assert db._store["leagues/lg_test/members/m5"]["eliminated"] is True
    # Revert undoes everything.
    res = eng.revert(LID)
    assert res["status"] == "reverted"
    assert db._store["leagues/lg_test/squads/m1"]["players"] == m1_before
    assert db._store["leagues/lg_test/squads/m5"]["players"] == m5_before
    assert db._store["leagues/lg_test/members/m5"]["eliminated"] is False
    assert "leagues/lg_test/ko_draft/state" not in db._store       # draft cleared
    assert "leagues/lg_test/ko_draft/backup" not in db._store      # backup consumed


def test_revert_after_rehearsal_is_safe_noop():
    db, eng = _fresh()  # rehearsal
    m1_before = [dict(p) for p in db._store["leagues/lg_test/squads/m1"]["players"]]
    eng.make_swap(LID, "m1", player_in=901, player_out=_def_out(1))
    eng.revert(LID)
    assert db._store["leagues/lg_test/squads/m1"]["players"] == m1_before
    assert "leagues/lg_test/ko_draft/state" not in db._store


def test_revert_without_backup():
    db = FakeDB(); _seed(db); eng = _engine(db)
    res = eng.revert(LID)
    assert res["status"] == "no_backup"


def test_auto_pass_only_after_deadline():
    db, eng = _fresh()
    with pytest.raises(ValueError, match="not expired"):
        eng.auto_pass(LID)
    # Force the clock past the deadline -> auto-passes the manager on the clock.
    db._store["leagues/lg_test/ko_draft/state"]["pickDeadline"] = 0
    eng.auto_pass(LID)
    assert eng.get_state(LID)["currentDrafter"] == "m2"
    assert "m1" not in eng.get_state(LID)["activePickers"]
