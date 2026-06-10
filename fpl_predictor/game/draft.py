"""
Real-time snake draft engine.

State machine backed by Firestore. Clients use onSnapshot for real-time updates.
15 rounds: fill 2GK + 5DEF + 5MID + 3FWD.
Snake order: odd rounds go 1->N, even rounds go N->1.
"""

import random
import time
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POSITION_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}  # GK, DEF, MID, FWD
NATION_QUOTA = 3   # max players from one nation per squad
TOTAL_ROUNDS = 15
POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class DraftEngine:
    def __init__(self, db, fpl_client):
        self.db = db
        self.fpl = fpl_client

    def start_draft(self, lid: str, uid: str, current_gw: int) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        league = league_doc.to_dict()
        if league["adminUid"] != uid:
            raise ValueError("Only the admin can start the draft")
        if league["status"] not in ("recruiting", "pre_draft", "drafting"):
            raise ValueError("Draft can only be started from recruiting or pre_draft status")

        members = list(league_ref.collection("members").get())
        if len(members) < 2:
            raise ValueError("Need at least 2 members to start draft")

        member_uids = [m.id for m in members]
        random.shuffle(member_uids)

        for i, muid in enumerate(member_uids):
            league_ref.collection("members").document(muid).update({
                "draftPosition": i + 1,
            })

        pick_timer = league.get("pickTimer", 30)
        total_picks = len(member_uids) * TOTAL_ROUNDS
        deadline = time.time() + pick_timer

        draft_ref = league_ref.collection("draft").document("state")
        draft_ref.set({
            "status": "active",
            "paused": False,
            "order": member_uids,
            "currentPick": 0,
            "totalPicks": total_picks,
            "pickDeadline": deadline,
            "pickTimer": pick_timer,
            "pickedPlayerIds": [],
            "currentDrafter": member_uids[0],
            "startedAt": SERVER_TIMESTAMP,
        })

        league_ref.update({
            "status": "drafting",
            "seasonStartGw": current_gw,
            "currentGw": current_gw,
        })

        return {
            "status": "active",
            "order": member_uids,
            "totalPicks": total_picks,
            "pickTimer": pick_timer,
            "currentPick": 0,
            "currentDrafter": member_uids[0],
        }

    def get_draft_state(self, lid: str) -> dict:
        draft_doc = (self.db.collection("leagues").document(lid)
                     .collection("draft").document("state").get())
        if not draft_doc.exists:
            return {"status": "pending"}
        state = draft_doc.to_dict()

        picks_docs = (self.db.collection("leagues").document(lid)
                      .collection("draft").document("state")
                      .collection("picks").order_by("pickNumber").get())
        picks = []
        for p in picks_docs:
            picks.append(p.to_dict())

        num_members = len(state.get("order", []))
        if num_members > 0:
            drafter_uid = self._get_drafter(
                state["currentPick"], state["order"]
            )
        else:
            drafter_uid = None

        return {
            "status": state.get("status", "pending"),
            "order": state.get("order", []),
            "currentPick": state.get("currentPick", 0),
            "totalPicks": state.get("totalPicks", 0),
            "pickDeadline": state.get("pickDeadline"),
            "pickTimer": state.get("pickTimer", 30),
            "picks": picks,
            "currentDrafter": drafter_uid,
            "currentRound": (state["currentPick"] // num_members) + 1 if num_members else 0,
            "pickedPlayerIds": state.get("pickedPlayerIds", []),
            "paused": state.get("paused", False),
            "humanUids": state.get("humanUids", []),
        }

    def make_pick(self, lid: str, uid: str, player_id: int,
                  is_auto: bool = False, idempotency_key: str = None,
                  expected_pick: int = None) -> dict:
        """Make one draft pick ATOMICALLY.

        All multi-writer hazards (several clients firing auto-picks, the
        advance nudge, manual clicks) funnel through a Firestore transaction
        on the state doc: the pick-doc write, the currentPick advance and the
        pickedPlayerIds append commit together or not at all. Stale callers
        fail with clean retryable errors instead of corrupting state:
          - "Player already drafted"  (dedupe re-checked inside the txn)
          - "STALE_PICK"              (expected_pick no longer current)
          - "TURN_CHANGED"            (auto pick computed for a previous
                                       drafter must NOT be credited to the
                                       next one — the old behaviour silently
                                       reassigned it)
        FakeDB (tests) has no transactions — falls back to plain ops there.
        """
        league_ref = self.db.collection("leagues").document(lid)
        draft_ref = league_ref.collection("draft").document("state")

        player_map = self.fpl.get_player_map()
        player = player_map.get(player_id)
        if not player:
            raise ValueError("Player not found")

        def _pick(txn):
            snap = (draft_ref.get(transaction=txn) if txn is not None
                    else draft_ref.get())
            if not snap.exists:
                raise ValueError("Draft not found")
            state = snap.to_dict()
            if state["status"] != "active":
                raise ValueError("Draft is not active")
            if state.get("paused", False):
                raise ValueError("Draft is paused")

            current_pick = state["currentPick"]
            if expected_pick is not None and current_pick != expected_pick:
                raise ValueError("STALE_PICK: state advanced, recompute")
            order = state["order"]
            num_members = len(order)
            expected_drafter = self._get_drafter(current_pick, order)
            if not is_auto and uid != expected_drafter:
                raise ValueError("Not your turn to pick")
            if is_auto and uid and uid != expected_drafter:
                # Candidate was computed for a drafter whose turn has passed.
                raise ValueError("TURN_CHANGED: recompute for current drafter")

            picked_ids = list(state.get("pickedPlayerIds", []))
            if player_id in picked_ids:
                raise ValueError("Player already drafted")

            drafter_uid = expected_drafter
            drafter_picks = self._get_drafter_picks(draft_ref, drafter_uid)
            pos = player["element_type"]
            pos_count = sum(1 for p in drafter_picks if p["position"] == pos)
            if pos_count >= POSITION_QUOTA[pos]:
                raise ValueError(
                    f"Already have max {POS_NAMES[pos]}s ({POSITION_QUOTA[pos]})"
                )

            # Nation cap (compared via the enriched teamShort ISO).
            nation = player.get("teamShort")
            if nation:
                nation_count = 0
                for p in drafter_picks:
                    try:
                        held = player_map.get(int(p.get("playerId"))) or {}
                    except (TypeError, ValueError):
                        held = {}
                    if held.get("teamShort") == nation:
                        nation_count += 1
                if nation_count >= NATION_QUOTA:
                    raise ValueError(
                        f"Already have max {NATION_QUOTA} players from {nation}"
                    )

            rnd = (current_pick // num_members) + 1
            pick_data = {
                "pickNumber": current_pick,
                "round": rnd,
                "pickInRound": (current_pick % num_members) + 1,
                "uid": drafter_uid,
                "playerId": player_id,
                "webName": player.get("web_name", "?"),
                "position": pos,
                "positionName": POS_NAMES[pos],
                "teamId": player.get("teamId", player.get("team", 0)),
                "teamShort": player.get("teamShort") or "?",
                "isAutoPick": is_auto,
                "timestamp": SERVER_TIMESTAMP,
            }

            new_pick = current_pick + 1
            picked_ids.append(player_id)
            update = {
                "currentPick": new_pick,
                "pickedPlayerIds": picked_ids,
                "pickDeadline": time.time() + state.get("pickTimer", 30),
                "currentDrafter": (self._get_drafter(new_pick, order)
                                   if new_pick < state["totalPicks"] else None),
            }
            completed = new_pick >= state["totalPicks"]
            if completed:
                update["status"] = "complete"
                update["completedAt"] = SERVER_TIMESTAMP

            pick_ref = draft_ref.collection("picks").document(str(current_pick))
            if txn is not None:
                txn.set(pick_ref, pick_data)
                txn.update(draft_ref, update)
            else:
                pick_ref.set(pick_data)
                draft_ref.update(update)

            return {
                "pickNumber": current_pick,
                "round": rnd,
                "uid": drafter_uid,
                "playerId": player_id,
                "webName": pick_data["webName"],
                "positionName": POS_NAMES[pos],
                "teamShort": pick_data["teamShort"],
                "_completed": completed,
            }

        if hasattr(self.db, "transaction"):
            from google.cloud.firestore_v1 import transactional

            @transactional
            def _txn_pick(txn):
                return _pick(txn)

            result = _txn_pick(self.db.transaction())
        else:
            result = _pick(None)

        if result.pop("_completed", False):
            self._finalize_draft(lid)
        return result

    # make_pick errors that mean "recompute from fresh state and try again"
    # rather than "give up" — stale candidate, advanced state, raced quota.
    _RETRYABLE = ("already drafted", "STALE_PICK", "TURN_CHANGED", "max ")

    def auto_pick(self, lid: str) -> dict:
        """Timeout pick. NEVER stalls on a stale candidate: if the chosen
        player was just taken (or the state advanced under us), recompute the
        next-best candidate from fresh state and retry, up to 3 attempts."""
        state_ref = (self.db.collection("leagues").document(lid)
                     .collection("draft").document("state"))
        last_err = None
        for _attempt in range(3):
            draft_doc = state_ref.get()
            if not draft_doc.exists:
                raise ValueError("Draft not found")
            state = draft_doc.to_dict()
            if state["status"] != "active":
                raise ValueError("Draft is not active")
            if state.get("paused", False):
                raise ValueError("Draft is paused")
            if time.time() < state.get("pickDeadline", float("inf")):
                raise ValueError("Pick timer has not expired")

            drafter_uid = self._get_drafter(state["currentPick"], state["order"])
            player_id = self._find_best_available(lid, drafter_uid, state)
            if not player_id:
                raise ValueError("No legal player available")
            try:
                return self.make_pick(lid, drafter_uid, player_id,
                                      is_auto=True,
                                      expected_pick=state["currentPick"])
            except ValueError as exc:
                msg = str(exc)
                if any(t in msg for t in self._RETRYABLE):
                    last_err = exc
                    continue
                raise
        raise last_err or ValueError("Auto-pick failed")

    def rollback_draft(self, lid: str, to_pick: int) -> dict:
        """Roll the draft back so pick number ``to_pick`` is ON THE CLOCK again.

        Deletes every pick doc with pickNumber >= to_pick, rebuilds
        pickedPlayerIds from the surviving picks (deduped — this also repairs
        any pre-existing duplicate corruption), resets currentPick/currentDrafter
        and re-arms a full pick clock for the resume. Only allowed while the
        draft is PAUSED so no concurrent picks race the rewind. If the draft
        had completed, squads are wiped and the league reopened for drafting.
        """
        league_ref = self.db.collection("leagues").document(lid)
        draft_ref = league_ref.collection("draft").document("state")
        snap = draft_ref.get()
        if not snap.exists:
            raise ValueError("Draft not found")
        state = snap.to_dict()
        if not state.get("paused", False) and state.get("status") == "active":
            raise ValueError("Pause the draft before rolling back")
        current_pick = state.get("currentPick", 0)
        if to_pick < 0 or to_pick >= current_pick:
            raise ValueError(
                f"toPick must be between 0 and {current_pick - 1}")

        removed = []
        survivors = []
        for p in draft_ref.collection("picks").get():
            pd = p.to_dict() or {}
            if pd.get("pickNumber", 0) >= to_pick:
                removed.append({"pickNumber": pd.get("pickNumber"),
                                "uid": pd.get("uid"),
                                "webName": pd.get("webName")})
                p.reference.delete()
            else:
                survivors.append(pd)

        picked_ids, seen = [], set()
        for pd in sorted(survivors, key=lambda x: x.get("pickNumber", 0)):
            pid = pd.get("playerId")
            if pid is not None and pid not in seen:
                seen.add(pid)
                picked_ids.append(pid)

        order = state.get("order", [])
        draft_ref.update({
            "currentPick": to_pick,
            "pickedPlayerIds": picked_ids,
            "currentDrafter": self._get_drafter(to_pick, order) if order else None,
            "status": "active",
            "paused": True,
            "pausedRemaining": state.get("pickTimer", 30),
            "completedAt": None,
        })

        league_doc = league_ref.get()
        if league_doc.exists and (league_doc.to_dict() or {}).get("draftComplete"):
            for sq in league_ref.collection("squads").get():
                sq.reference.delete()
            league_ref.update({"draftComplete": False, "status": "drafting"})

        return {"currentPick": to_pick,
                "currentDrafter": self._get_drafter(to_pick, order) if order else None,
                "removed": sorted(removed, key=lambda x: x["pickNumber"]),
                "stillPaused": True}

    def validate_draft(self, lid: str) -> dict:
        """Integrity report: duplicate players, quota/nation violations,
        pick-number gaps, and pickedPlayerIds drift vs the pick docs."""
        league_ref = self.db.collection("leagues").document(lid)
        draft_ref = league_ref.collection("draft").document("state")
        snap = draft_ref.get()
        if not snap.exists:
            raise ValueError("Draft not found")
        state = snap.to_dict()
        picks = [p.to_dict() or {} for p in draft_ref.collection("picks").get()]
        picks.sort(key=lambda x: x.get("pickNumber", 0))

        by_player = {}
        for pd in picks:
            by_player.setdefault(pd.get("playerId"), []).append(pd)
        duplicates = [
            {"playerId": pid, "webName": lst[0].get("webName"),
             "picks": [{"pickNumber": p.get("pickNumber"), "uid": p.get("uid")}
                       for p in lst]}
            for pid, lst in by_player.items() if len(lst) > 1]

        player_map = self.fpl.get_player_map()
        quota_violations, nation_violations = [], []
        by_uid = {}
        for pd in picks:
            by_uid.setdefault(pd.get("uid"), []).append(pd)
        for muid, lst in by_uid.items():
            pos_counts, nat_counts = {}, {}
            for pd in lst:
                pos_counts[pd.get("position")] = pos_counts.get(pd.get("position"), 0) + 1
                try:
                    iso = (player_map.get(int(pd.get("playerId"))) or {}).get("teamShort")
                except (TypeError, ValueError):
                    iso = None
                if iso:
                    nat_counts[iso] = nat_counts.get(iso, 0) + 1
            for pos, c in pos_counts.items():
                if c > POSITION_QUOTA.get(pos, 99):
                    quota_violations.append({"uid": muid, "position": POS_NAMES.get(pos), "count": c})
            for iso, c in nat_counts.items():
                if c > NATION_QUOTA:
                    nation_violations.append({"uid": muid, "nation": iso, "count": c})

        nums = [pd.get("pickNumber") for pd in picks]
        gaps = [n for n in range(state.get("currentPick", 0)) if n not in set(nums)]
        doc_ids = {pd.get("playerId") for pd in picks}
        state_ids = set(state.get("pickedPlayerIds", []))
        return {
            "ok": not (duplicates or quota_violations or nation_violations or gaps
                       or doc_ids != state_ids),
            "duplicates": duplicates,
            "quotaViolations": quota_violations,
            "nationViolations": nation_violations,
            "pickNumberGaps": gaps,
            "stateIdsMissingFromDocs": sorted(state_ids - doc_ids),
            "docIdsMissingFromState": sorted(doc_ids - state_ids),
            "currentPick": state.get("currentPick"),
            "nPickDocs": len(picks),
        }

    def get_available_players(self, lid: str, position: int = None) -> list:
        draft_doc = (self.db.collection("leagues").document(lid)
                     .collection("draft").document("state").get())
        picked_ids = set()
        if draft_doc.exists:
            picked_ids = set(draft_doc.to_dict().get("pickedPlayerIds", []))

        players = self.fpl.get_players()
        team_map = self.fpl.get_team_map()
        result = []
        for p in players:
            if p["id"] in picked_ids:
                continue
            if position and p["element_type"] != position:
                continue
            result.append({
                "id": p["id"],
                "webName": p.get("web_name", "?"),
                "position": p["element_type"],
                "positionName": POS_NAMES.get(p["element_type"], "?"),
                "teamId": p.get("team", 0),
                "teamShort": team_map.get(
                    p.get("team", 0), {}
                ).get("short_name", "?"),
                "totalPoints": p.get("total_points", 0),
                "form": p.get("form", "0"),
                "draftRank": p.get("draft_rank"),
            })

        result.sort(key=lambda x: (x["draftRank"] or 9999, -x["totalPoints"]))
        return result

    def _get_drafter(self, pick_number: int, order: list) -> str:
        num = len(order)
        rnd = pick_number // num
        pos_in_round = pick_number % num
        if rnd % 2 == 0:
            return order[pos_in_round]
        else:
            return order[num - 1 - pos_in_round]

    def _get_drafter_picks(self, draft_ref, uid: str) -> list:
        picks = draft_ref.collection("picks").where(
            "uid", "==", uid
        ).get()
        return [p.to_dict() for p in picks]

    def _get_watchlist(self, lid: str, uid: str) -> list:
        """The manager's ordered draft watchlist (player ids) — the same
        per-manager doc the /draft/watchlist API reads/writes. ``[]`` if none."""
        doc = (self.db.collection("leagues").document(lid)
               .collection("draft").document("watchlists")
               .collection(uid).document("list").get())
        return (doc.to_dict() or {}).get("playerIds", []) if doc.exists else []

    def _find_best_available(self, lid: str, uid: str, state: dict) -> int:
        draft_ref = (self.db.collection("leagues").document(lid)
                     .collection("draft").document("state"))
        drafter_picks = self._get_drafter_picks(draft_ref, uid)
        pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for p in drafter_picks:
            pos_counts[p["position"]] = pos_counts.get(p["position"], 0) + 1

        needs = []
        for pos, quota in POSITION_QUOTA.items():
            deficit = quota - pos_counts.get(pos, 0)
            if deficit > 0:
                needs.append((deficit, pos))
        needs.sort(reverse=True)

        picked_ids = set(state.get("pickedPlayerIds", []))
        players = self.fpl.get_players()

        # Nation counts for this drafter (cap = NATION_QUOTA per nation).
        by_pid = {p["id"]: p for p in players}
        nation_counts = {}
        for dp in drafter_picks:
            try:
                iso = (by_pid.get(int(dp.get("playerId"))) or {}).get("teamShort")
            except (TypeError, ValueError):
                iso = None
            if iso:
                nation_counts[iso] = nation_counts.get(iso, 0) + 1

        def nation_ok(p):
            iso = p.get("teamShort")
            return not iso or nation_counts.get(iso, 0) < NATION_QUOTA

        # Honor the manager's saved watchlist FIRST (the priority queue they
        # built in the Draft Room). Pick the highest-priority watchlisted player
        # that is still available AND keeps the squad within its position quota
        # AND under the per-nation cap. Only if none qualifies do we fall back
        # to the best-available-by-draft-rank heuristic below.
        watchlist = self._get_watchlist(lid, uid)
        if watchlist:
            by_id = {}
            for p in players:
                by_id[p["id"]] = p
                by_id[str(p["id"])] = p   # tolerate string-typed ids from the client
            for wid in watchlist:
                p = by_id.get(wid)
                if p is None:
                    try:
                        p = by_id.get(int(wid))
                    except (TypeError, ValueError):
                        p = None
                if not p or p["id"] in picked_ids:
                    continue
                pos = p.get("element_type")
                if pos_counts.get(pos, 0) < POSITION_QUOTA.get(pos, 0) and nation_ok(p):
                    return p["id"]

        for _, target_pos in needs:
            candidates = [
                p for p in players
                if p["id"] not in picked_ids
                and p["element_type"] == target_pos
                and nation_ok(p)
            ]
            candidates.sort(
                key=lambda x: (x.get("draft_rank") or 9999,
                               -x.get("total_points", 0))
            )
            if candidates:
                return candidates[0]["id"]

        all_available = [p for p in players
                         if p["id"] not in picked_ids and nation_ok(p)]
        if not all_available:
            # Degenerate safety net: never deadlock the draft.
            all_available = [p for p in players if p["id"] not in picked_ids]
        all_available.sort(
            key=lambda x: (x.get("draft_rank") or 9999,
                           -x.get("total_points", 0))
        )
        return all_available[0]["id"] if all_available else 0

    def _finalize_draft(self, lid: str):
        league_ref = self.db.collection("leagues").document(lid)
        draft_ref = league_ref.collection("draft").document("state")

        picks = list(
            draft_ref.collection("picks").order_by("pickNumber").get()
        )

        squads = {}
        for p in picks:
            pd = p.to_dict()
            uid = pd["uid"]
            if uid not in squads:
                squads[uid] = []
            squads[uid].append({
                "playerId": pd["playerId"],
                "webName": pd["webName"],
                "position": pd["position"],
                "positionName": pd["positionName"],
                "teamId": pd["teamId"],
                "teamShort": pd["teamShort"],
            })

        for uid, players in squads.items():
            league_ref.collection("squads").document(uid).set({
                "players": players,
            })

        # Draft is done, but the SEASON has not started yet. Leave the league
        # in "drafting" so start_season() can transition drafting -> group_phase
        # (the canonical playing state recognized by scoring/propagation/squads/
        # trades/waivers). Do NOT set "active" — it is an orphan status that
        # every gameplay subsystem ignores and that start_season rejects.
        league_ref.update({
            "draftComplete": True,
            "draftCompletedAt": SERVER_TIMESTAMP,
        })
