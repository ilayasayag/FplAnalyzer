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
            "order": member_uids,
            "currentPick": 0,
            "totalPicks": total_picks,
            "pickDeadline": deadline,
            "pickTimer": pick_timer,
            "pickedPlayerIds": [],
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
        }

    def make_pick(self, lid: str, uid: str, player_id: int,
                  is_auto: bool = False) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        draft_ref = league_ref.collection("draft").document("state")

        draft_snap = draft_ref.get()
        if not draft_snap.exists:
            raise ValueError("Draft not found")

        state = draft_snap.to_dict()
        if state["status"] != "active":
            raise ValueError("Draft is not active")

        current_pick = state["currentPick"]
        order = state["order"]
        num_members = len(order)
        expected_drafter = self._get_drafter(current_pick, order)

        if not is_auto and uid != expected_drafter:
            raise ValueError("Not your turn to pick")

        picked_ids = state.get("pickedPlayerIds", [])
        if player_id in picked_ids:
            raise ValueError("Player already drafted")

        player = self.fpl.get_player_map().get(player_id)
        if not player:
            raise ValueError("Player not found")

        drafter_uid = expected_drafter
        drafter_picks = self._get_drafter_picks(draft_ref, drafter_uid)
        pos = player["element_type"]
        pos_count = sum(1 for p in drafter_picks if p["position"] == pos)
        if pos_count >= POSITION_QUOTA[pos]:
            raise ValueError(
                f"Already have max {POS_NAMES[pos]}s ({POSITION_QUOTA[pos]})"
            )

        rnd = (current_pick // num_members) + 1
        pick_in_round = (current_pick % num_members) + 1
        team_map = self.fpl.get_team_map()

        pick_data = {
            "pickNumber": current_pick,
            "round": rnd,
            "pickInRound": pick_in_round,
            "uid": drafter_uid,
            "playerId": player_id,
            "webName": player.get("web_name", "?"),
            "position": pos,
            "positionName": POS_NAMES[pos],
            "teamId": player.get("team", 0),
            "teamShort": team_map.get(
                player.get("team", 0), {}
            ).get("short_name", "?"),
            "isAutoPick": is_auto,
            "timestamp": SERVER_TIMESTAMP,
        }

        draft_ref.collection("picks").document(str(current_pick)).set(pick_data)

        new_pick = current_pick + 1
        picked_ids.append(player_id)
        pick_timer = state.get("pickTimer", 30)

        update = {
            "currentPick": new_pick,
            "pickedPlayerIds": picked_ids,
            "pickDeadline": time.time() + pick_timer,
        }

        if new_pick >= state["totalPicks"]:
            update["status"] = "complete"
            update["completedAt"] = SERVER_TIMESTAMP

        draft_ref.update(update)

        if update.get("status") == "complete":
            self._finalize_draft(lid)

        return {
            "pickNumber": current_pick,
            "round": rnd,
            "uid": drafter_uid,
            "playerId": player_id,
            "webName": pick_data["webName"],
            "positionName": POS_NAMES[pos],
            "teamShort": pick_data["teamShort"],
        }

    def auto_pick(self, lid: str) -> dict:
        draft_doc = (self.db.collection("leagues").document(lid)
                     .collection("draft").document("state").get())
        if not draft_doc.exists:
            raise ValueError("Draft not found")

        state = draft_doc.to_dict()
        if state["status"] != "active":
            raise ValueError("Draft is not active")

        if time.time() < state.get("pickDeadline", float("inf")):
            raise ValueError("Pick timer has not expired")

        drafter_uid = self._get_drafter(state["currentPick"], state["order"])
        player_id = self._find_best_available(lid, drafter_uid, state)

        return self.make_pick(lid, drafter_uid, player_id, is_auto=True)

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

        for _, target_pos in needs:
            candidates = [
                p for p in players
                if p["id"] not in picked_ids
                and p["element_type"] == target_pos
            ]
            candidates.sort(
                key=lambda x: (x.get("draft_rank") or 9999,
                               -x.get("total_points", 0))
            )
            if candidates:
                return candidates[0]["id"]

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

        league_ref.update({"status": "active"})
