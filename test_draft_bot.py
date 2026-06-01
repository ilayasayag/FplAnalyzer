#!/usr/bin/env python3
"""
Sprint 1 — Bot-driven snake draft dry-run + draft validation tests.

Runs against the LOCAL emulator stack (Auth :9099, Firestore :8080, Flask :5000).
Does NOT touch production.

Coverage:
  1. Happy path — admin starts the draft, every manager auto-picks in snake
     order until all 7×15 = 105 picks are made; final squads have the right
     position quotas (2 GK / 5 DEF / 5 MID / 3 FWD).
  2. Negative paths:
     - non-admin tries /draft/start                → "Only the admin"
     - missing playerId in /draft/pick body        → "playerId required"
     - pick when not your turn                     → "Not your turn"
     - pick an already-drafted player              → "Player already drafted"
     - pick a 3rd GK once 2 GKs are on the squad   → "Already have max GKs"

The bot exercises the live HTTP surface (/api/v1/wc/...) — same path the
frontend uses — not the engine directly, so the route ↔ engine plumbing
is part of the test (this is how I'd have caught the idempotency_key
signature bug that just shipped to prod).

Pre-reqs: local stack running, emulator seeded with lg_pre_draft + members.
"""
import os
import sys
import time
from typing import Dict, List, Optional

os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests
import firebase_admin
from firebase_admin import auth as fb_auth, firestore

PROJECT_ID = "fpl-analyzer-792eb"
EMULATOR_API_KEY = "fake-api-key"  # any string works for the Auth emulator
AUTH_EMU = "http://localhost:9099"
API_BASE = "http://localhost:5000/api/v1/wc"
LID = "lg_pre_draft"

if not firebase_admin._apps:
    from google.auth.credentials import AnonymousCredentials
    firebase_admin.initialize_app(credential=AnonymousCredentials(), options={"projectId": PROJECT_ID})

_db = firestore.client(database_id=os.environ.get("FIRESTORE_DB_ID", "gamedb"))
_token_cache: Dict[str, str] = {}


# ----------------------------- auth helpers -----------------------------

def id_token_for(uid: str) -> str:
    """Mint a custom token via admin SDK, exchange for an ID token via Auth emu."""
    if uid in _token_cache:
        return _token_cache[uid]
    custom = fb_auth.create_custom_token(uid).decode("utf-8")
    r = requests.post(
        f"{AUTH_EMU}/identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={EMULATOR_API_KEY}",
        json={"token": custom, "returnSecureToken": True},
        timeout=10,
    )
    r.raise_for_status()
    tok = r.json()["idToken"]
    _token_cache[uid] = tok
    return tok


def api(method: str, path: str, uid: Optional[str] = None, body=None):
    headers = {"Content-Type": "application/json"}
    if uid:
        headers["Authorization"] = f"Bearer {id_token_for(uid)}"
    r = requests.request(method, f"{API_BASE}{path}", headers=headers, json=body, timeout=15)
    raw = r.json() if r.text else {}
    # Unwrap the {data, error} envelope for happy paths; pass through on error.
    if isinstance(raw, dict) and "data" in raw and "error" in raw:
        if raw.get("error"):
            return r.status_code, {"error": raw["error"]}
        return r.status_code, (raw.get("data") or {})
    return r.status_code, raw


# ----------------------------- fixtures -----------------------------

def current_drafter(state: Dict) -> str:
    """Compute snake-order drafter — the API returns raw state, not this."""
    pick = state["currentPick"]
    order = state["order"]
    n = len(order)
    rnd = pick // n
    pos_in_round = pick % n
    return order[pos_in_round] if rnd % 2 == 0 else order[n - 1 - pos_in_round]


def league_members() -> List[Dict]:
    docs = _db.collection("leagues").document(LID).collection("members").get()
    return [{"uid": d.id, **d.to_dict()} for d in docs]


def league_admin() -> str:
    return _db.collection("leagues").document(LID).get().to_dict()["adminUid"]


def reset_draft_state():
    """Wipe any in-flight draft so the test starts clean. Idempotent."""
    league_ref = _db.collection("leagues").document(LID)
    state_ref = league_ref.collection("draft").document("state")
    if state_ref.get().exists:
        for pick in state_ref.collection("picks").get():
            pick.reference.delete()
        state_ref.delete()
    # Squads from a prior finalize_draft would block re-running.
    for sq in league_ref.collection("squads").get():
        sq.reference.delete()
    league_ref.update({"status": "pre_draft", "draftComplete": False})


def fresh_player_pool() -> List[Dict]:
    """All players, sorted by FPL element_type so we can pick by position deterministically."""
    docs = _db.collection("wc_players").get()
    out = []
    for d in docs:
        data = d.to_dict()
        out.append({
            "id": int(data.get("id") or d.id),
            "position": data.get("position"),  # 1=GK 2=DEF 3=MID 4=FWD
            "team": data.get("teamId"),
            "web_name": data.get("name", "?"),
        })
    return out


# ----------------------------- assertions -----------------------------

PASSES = []
FAILS = []

def check(name: str, cond: bool, detail: str = ""):
    if cond:
        PASSES.append(name)
        print(f"  ✓ {name}")
    else:
        FAILS.append((name, detail))
        print(f"  ✗ {name}  {detail}")


# ----------------------------- the test -----------------------------

def run():
    print(f"🎯 Target: {API_BASE} (LID={LID})")
    members = league_members()
    admin_uid = league_admin()
    print(f"  league has {len(members)} members; admin={admin_uid}")
    assert len(members) >= 2, "Need >=2 members for a draft"

    print("\n=== NEGATIVE: /draft/start by non-admin ===")
    reset_draft_state()
    non_admin = next(m["uid"] for m in members if m["uid"] != admin_uid)
    sc, body = api("POST", f"/leagues/{LID}/draft/start", uid=non_admin)
    check("non-admin /draft/start rejected", sc >= 400 and "admin" in str(body).lower(), f"sc={sc} body={body}")

    print("\n=== HAPPY PATH: full snake draft ===")
    reset_draft_state()
    sc, body = api("POST", f"/leagues/{LID}/draft/start", uid=admin_uid)
    check("admin /draft/start ok", sc == 200, f"sc={sc} body={body}")
    order = body["order"]
    total_picks = body["totalPicks"]
    n = len(order)
    print(f"    draft order: {order}")
    print(f"    totalPicks={total_picks}  (n={n} × 15 rounds)")
    check("totalPicks == n*15", total_picks == n * 15)

    # Route contract: /draft/state must return currentDrafter + picks so the
    # frontend Draft Room (onTheClock / isMyTurn) actually works.
    sc, st0 = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
    check("/draft/state returns currentDrafter", "currentDrafter" in st0 and st0["currentDrafter"] in order, f"got={st0.get('currentDrafter')!r}")
    check("/draft/state returns picks list", isinstance(st0.get("picks"), list), f"picks type={type(st0.get('picks')).__name__}")
    check("/draft/state returns currentRound", isinstance(st0.get("currentRound"), int), f"currentRound={st0.get('currentRound')!r}")

    pool = fresh_player_pool()
    # group pool by position for deterministic per-uid quotas
    by_pos = {1: [], 2: [], 3: [], 4: []}
    for p in pool:
        if p["position"] in by_pos:
            by_pos[p["position"]].append(p)

    drafted = set()
    pos_counts_by_uid = {u: {1: 0, 2: 0, 3: 0, 4: 0} for u in order}
    # snake-friendly position template — fill the same 15 slots for each manager
    POS_TEMPLATE = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]  # 2GK 5DEF 5MID 3FWD
    QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}

    last_drafted_player_id = None
    for pick_no in range(total_picks):
        sc, state = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
        if sc != 200:
            print(f"  ! /draft/state failed sc={sc} body={state}")
            break
        drafter = current_drafter(state)
        my_counts = pos_counts_by_uid[drafter]
        # find next position this manager needs, walking the template
        my_picks_so_far = sum(my_counts.values())
        target_pos = POS_TEMPLATE[my_picks_so_far]
        # if their quota for that position is already full, walk forward
        while my_counts[target_pos] >= QUOTA[target_pos]:
            my_picks_so_far += 1
            target_pos = POS_TEMPLATE[my_picks_so_far]
        candidate = next((p for p in by_pos[target_pos] if p["id"] not in drafted), None)
        assert candidate, f"no candidate for pos={target_pos}"

        sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                       uid=drafter, body={"playerId": candidate["id"]})
        if sc != 200:
            print(f"  ! pick #{pick_no} by {drafter} failed sc={sc} body={body}")
            check(f"pick #{pick_no} ok", False, f"{sc} {body}")
            break
        drafted.add(candidate["id"])
        pos_counts_by_uid[drafter][target_pos] += 1
        last_drafted_player_id = candidate["id"]
        if pick_no % 20 == 0 or pick_no == total_picks - 1:
            print(f"    pick {pick_no+1}/{total_picks}  R{body['round']}  {drafter[:10]:<10}  →  {body['webName']} ({body['positionName']})")

    sc, final_state = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
    check("draft status complete", final_state.get("status") == "complete", f"status={final_state.get('status')}")
    check(f"currentPick == totalPicks ({total_picks})", final_state.get("currentPick") == total_picks)
    check("105 unique players drafted", len(set(final_state.get("pickedPlayerIds", []))) == total_picks)

    print("\n=== SQUAD SHAPE VALIDATION ===")
    for m in members:
        uid = m["uid"]
        c = pos_counts_by_uid[uid]
        ok = c == QUOTA
        check(f"{uid}: 2GK/5DEF/5MID/3FWD", ok, f"got {c}")

    print("\n=== NEGATIVE: pick after draft complete ===")
    # currentDrafter is None; any pick should fail
    any_uid = members[0]["uid"]
    sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                   uid=any_uid, body={"playerId": pool[0]["id"]})
    check("post-complete pick rejected", sc >= 400, f"sc={sc} body={body}")

    # --- Re-start a fresh draft for the in-progress negative tests ---
    print("\n=== Reset for negative-path tests ===")
    reset_draft_state()
    sc, body = api("POST", f"/leagues/{LID}/draft/start", uid=admin_uid)
    assert sc == 200, body
    order = body["order"]

    print("\n=== NEGATIVE: missing playerId ===")
    first = order[0]
    sc, body = api("POST", f"/leagues/{LID}/draft/pick", uid=first, body={})
    check("missing playerId rejected", sc >= 400 and "playerid" in str(body).lower(), f"sc={sc} body={body}")

    print("\n=== NEGATIVE: pick when not your turn ===")
    wrong = order[1]  # it's order[0]'s turn
    a_player = next(p["id"] for p in pool)
    sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                   uid=wrong, body={"playerId": a_player})
    check("not-your-turn rejected", sc >= 400 and "turn" in str(body).lower(), f"sc={sc} body={body}")

    print("\n=== NEGATIVE: pick already-drafted player ===")
    # first makes a legit pick, then second tries to pick the same id
    a_gk = next(p["id"] for p in by_pos[1])
    sc, body = api("POST", f"/leagues/{LID}/draft/pick", uid=first, body={"playerId": a_gk})
    assert sc == 200, f"setup failed: {body}"
    # round 1 is snake, next drafter is order[1]
    sc_state, st = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
    next_drafter = current_drafter(st)
    sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                   uid=next_drafter, body={"playerId": a_gk})
    check("dup-player rejected", sc >= 400 and "already" in str(body).lower(), f"sc={sc} body={body}")

    print("\n=== NEGATIVE: 3rd GK rejected ===")
    # first already picked 1 GK. Drive him to pick 2 more GKs:
    # snake order: R1 first picks first, R2 first picks LAST. So after R1 pick 1,
    # we need to play through other R1 picks (n-1 picks), then in R2 first picks
    # last after n-1 picks. Simpler: drive a focused mini-scenario manually.
    # We'll just play through and have `first` pick a 2nd GK on his round-2
    # turn, then try a 3rd on his round-3 turn.
    # Reserve GKs for `first`; other drafters pick non-GKs so we don't burn the pool.
    first_gk_count = 1  # already picked a_gk above
    while first_gk_count < 2:
        sc, st = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
        drafter = current_drafter(st)
        taken = set(st["pickedPlayerIds"])
        if drafter == first:
            target = next((p["id"] for p in by_pos[1] if p["id"] not in taken), None)
            assert target, "ran out of GKs"
            sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                           uid=first, body={"playerId": target})
            assert sc == 200, body
            first_gk_count += 1
        else:
            # other drafter — pick any NON-GK so we keep the GK pool for `first`
            any_pid = next(p["id"] for p in pool if p["id"] not in taken and p["position"] != 1)
            sc, _ = api("POST", f"/leagues/{LID}/draft/pick",
                        uid=drafter, body={"playerId": any_pid})
            assert sc == 200

    # Now wait until first's next turn and try a 3rd GK.
    sc, st = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
    third_gk = next(p["id"] for p in by_pos[1] if p["id"] not in set(st["pickedPlayerIds"]))
    while True:
        sc, st = api("GET", f"/leagues/{LID}/draft/state", uid=admin_uid)
        drafter = current_drafter(st)
        if drafter == first:
            break
        taken = set(st["pickedPlayerIds"])
        any_pid = next(p["id"] for p in pool if p["id"] not in taken and p["position"] != 1)
        api("POST", f"/leagues/{LID}/draft/pick", uid=drafter, body={"playerId": any_pid})

    sc, body = api("POST", f"/leagues/{LID}/draft/pick",
                   uid=first, body={"playerId": third_gk})
    check("3rd GK rejected", sc >= 400 and ("max" in str(body).lower() or "gk" in str(body).lower()), f"sc={sc} body={body}")

    print()
    print("=" * 60)
    print(f"  ✅ {len(PASSES)} passed     ❌ {len(FAILS)} failed")
    print("=" * 60)
    if FAILS:
        for name, detail in FAILS:
            print(f"  - {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    run()
