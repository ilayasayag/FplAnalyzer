"""
Two-phase waiver / free agent system.

Phase 1 (Waivers): Priority-based claims processed at waiver deadline.
  Priority = inverse standings (last place picks first).
  After a successful claim, that manager drops to lowest priority.

Phase 2 (Free Agency): FCFS after waivers process until GW deadline.
  Must drop a player of the SAME POSITION.
"""

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class WaiverManager:
    def __init__(self, db, fpl_client=None):
        self.db = db
        self.fpl = fpl_client

    def submit_waiver(self, lid: str, uid: str, player_in: int,
                      player_out: int, gw: int) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")
        if league_doc.to_dict().get("status") != "active":
            raise ValueError("League is not active")

        squad = self._get_squad(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}

        if player_out not in squad_map:
            raise ValueError("Drop player not in your squad")

        owned_ids = self._get_all_owned(lid)
        if player_in in owned_ids:
            raise ValueError("Player is not a free agent")

        member_doc = (league_ref.collection("members")
                      .document(uid).get())
        priority = member_doc.to_dict().get("waiverPriority", 99)

        waiver_ref = league_ref.collection("waivers").document()
        waiver_data = {
            "uid": uid,
            "playerIn": player_in,
            "playerOut": player_out,
            "priority": priority,
            "gw": gw,
            "status": "pending",
            "createdAt": SERVER_TIMESTAMP,
        }
        waiver_ref.set(waiver_data)

        return {
            "waiverId": waiver_ref.id,
            "playerIn": player_in,
            "playerOut": player_out,
            "priority": priority,
            "gw": gw,
            "status": "pending",
        }

    def cancel_waiver(self, lid: str, waiver_id: str, uid: str):
        ref = (self.db.collection("leagues").document(lid)
               .collection("waivers").document(waiver_id))
        doc = ref.get()
        if not doc.exists:
            raise ValueError("Waiver not found")
        data = doc.to_dict()
        if data["uid"] != uid:
            raise ValueError("Not your waiver claim")
        if data["status"] != "pending":
            raise ValueError("Waiver already processed")
        ref.delete()

    def process_waivers(self, lid: str, gw: int) -> dict:
        """Process all pending waivers for a GW in priority order."""
        league_ref = self.db.collection("leagues").document(lid)

        all_waivers = list(
            league_ref.collection("waivers")
            .where("gw", "==", gw)
            .get()
        )
        pending = [d for d in all_waivers if d.to_dict().get("status") == "pending"]
        pending.sort(key=lambda d: d.to_dict().get("priority", 99))

        claimed_players = set()
        results = []

        for doc in pending:
            waiver = doc.to_dict()
            uid = waiver["uid"]
            pin = waiver["playerIn"]
            pout = waiver["playerOut"]

            if pin in claimed_players:
                doc.reference.update({"status": "rejected"})
                results.append({
                    "uid": uid, "playerIn": pin, "status": "rejected",
                    "reason": "Player claimed by higher priority",
                })
                continue

            squad = self._get_squad(lid, uid)
            squad_map = {p["playerId"]: p for p in squad}
            if pout not in squad_map:
                doc.reference.update({"status": "rejected"})
                results.append({
                    "uid": uid, "playerIn": pin, "status": "rejected",
                    "reason": "Drop player no longer in squad",
                })
                continue

            self._execute_swap(lid, uid, pin, pout, squad)
            claimed_players.add(pin)
            doc.reference.update({"status": "approved"})

            self._drop_waiver_priority(lid, uid)

            results.append({
                "uid": uid, "playerIn": pin, "playerOut": pout,
                "status": "approved",
            })

        return {"gw": gw, "processed": len(results), "results": results}

    def sign_free_agent(self, lid: str, uid: str, player_in: int,
                        player_out: int) -> dict:
        """FCFS free agent signing (Phase 2, after waivers)."""
        league_ref = self.db.collection("leagues").document(lid)
        squad = self._get_squad(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}

        if player_out not in squad_map:
            raise ValueError("Drop player not in your squad")

        out_pos = squad_map[player_out]["position"]

        owned_ids = self._get_all_owned(lid)
        if player_in in owned_ids:
            raise ValueError("Player is already owned")

        player_map = self.fpl.get_player_map()
        incoming = player_map.get(player_in)
        if not incoming:
            raise ValueError("Player not found")

        in_pos = incoming.get("element_type")
        if in_pos != out_pos:
            raise ValueError(
                f"Must swap same position. "
                f"Dropping {POS_NAMES[out_pos]}, "
                f"signing {POS_NAMES[in_pos]}."
            )

        self._execute_swap(lid, uid, player_in, player_out, squad)

        return {"status": "ok", "playerIn": player_in, "playerOut": player_out}

    def get_free_agents(self, lid: str, position: int = None) -> list:
        owned_ids = self._get_all_owned(lid)
        players = self.fpl.get_players()
        team_map = self.fpl.get_team_map()
        result = []
        for p in players:
            if p["id"] in owned_ids:
                continue
            if position and p["element_type"] != position:
                continue
            result.append({
                "id": p["id"],
                "webName": p.get("web_name", "?"),
                "position": p["element_type"],
                "positionName": POS_NAMES.get(p["element_type"], "?"),
                "teamId": p.get("team", 0),
                "teamShort": team_map.get(p.get("team", 0), {}).get("short_name", "?"),
                "totalPoints": p.get("total_points", 0),
                "form": p.get("form", "0"),
            })
        result.sort(key=lambda x: -x["totalPoints"])
        return result

    def _get_squad(self, lid: str, uid: str) -> list:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError("No squad found")
        return doc.to_dict()["players"]

    def _get_all_owned(self, lid: str) -> set:
        league_ref = self.db.collection("leagues").document(lid)
        squads = list(league_ref.collection("squads").get())
        owned = set()
        for doc in squads:
            for p in doc.to_dict().get("players", []):
                owned.add(p["playerId"])
        return owned

    def _execute_swap(self, lid: str, uid: str, player_in: int,
                      player_out: int, squad: list):
        league_ref = self.db.collection("leagues").document(lid)
        squad_ref = league_ref.collection("squads").document(uid)

        player_data = self.fpl.get_player_map().get(player_in, {})
        team_map = self.fpl.get_team_map()

        new_player = {
            "playerId": player_in,
            "webName": player_data.get("web_name", "?"),
            "position": player_data.get("element_type", 0),
            "positionName": POS_NAMES.get(player_data.get("element_type", 0), "?"),
            "teamId": player_data.get("team", 0),
            "teamShort": team_map.get(player_data.get("team", 0), {}).get("short_name", "?"),
        }

        new_squad = [p for p in squad if p["playerId"] != player_out]
        new_squad.append(new_player)
        squad_ref.update({"players": new_squad})

    def _drop_waiver_priority(self, lid: str, uid: str):
        league_ref = self.db.collection("leagues").document(lid)
        members = list(league_ref.collection("members").get())
        max_priority = max(
            m.to_dict().get("waiverPriority", 1) for m in members
        )
        league_ref.collection("members").document(uid).update({
            "waiverPriority": max_priority + 1,
        })
