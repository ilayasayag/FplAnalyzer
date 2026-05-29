"""
Trade system.

Like-for-like position trades: if you offer 2 DEF + 1 MID,
you must request 2 DEF + 1 MID back.
Approval modes: instant, admin, vote (50% veto), none.
"""

from collections import Counter
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class TradeManager:
    def __init__(self, db):
        self.db = db

    def propose_trade(self, lid: str, proposer_uid: str, target_uid: str,
                      proposer_player_ids: list,
                      target_player_ids: list) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        league = league_doc.to_dict()
        if league.get("tradeApproval") == "none":
            raise ValueError("Trading is disabled in this league")
        if league.get("status") != "active":
            raise ValueError("League is not active")

        if proposer_uid == target_uid:
            raise ValueError("Cannot trade with yourself")

        prop_squad = self._get_squad(lid, proposer_uid)
        tgt_squad = self._get_squad(lid, target_uid)

        prop_map = {p["playerId"]: p for p in prop_squad}
        tgt_map = {p["playerId"]: p for p in tgt_squad}

        for pid in proposer_player_ids:
            if pid not in prop_map:
                raise ValueError(f"Player {pid} not in your squad")
        for pid in target_player_ids:
            if pid not in tgt_map:
                raise ValueError(f"Player {pid} not in target's squad")

        prop_positions = Counter(
            prop_map[pid]["position"] for pid in proposer_player_ids
        )
        tgt_positions = Counter(
            tgt_map[pid]["position"] for pid in target_player_ids
        )
        if prop_positions != tgt_positions:
            prop_desc = ", ".join(
                f"{c} {POS_NAMES[p]}" for p, c in sorted(prop_positions.items())
            )
            tgt_desc = ", ".join(
                f"{c} {POS_NAMES[p]}" for p, c in sorted(tgt_positions.items())
            )
            raise ValueError(
                f"Trade must be like-for-like by position. "
                f"Offering: {prop_desc}. Requesting: {tgt_desc}."
            )

        prop_players = [
            {"playerId": pid, "position": prop_map[pid]["position"],
             "webName": prop_map[pid]["webName"],
             "positionName": POS_NAMES[prop_map[pid]["position"]]}
            for pid in proposer_player_ids
        ]
        tgt_players = [
            {"playerId": pid, "position": tgt_map[pid]["position"],
             "webName": tgt_map[pid]["webName"],
             "positionName": POS_NAMES[tgt_map[pid]["position"]]}
            for pid in target_player_ids
        ]

        trade_ref = league_ref.collection("trades").document()
        trade_data = {
            "proposerUid": proposer_uid,
            "targetUid": target_uid,
            "proposerPlayers": prop_players,
            "targetPlayers": tgt_players,
            "status": "pending",
            "vetoVotes": [],
            "createdAt": SERVER_TIMESTAMP,
            "resolvedAt": None,
        }
        trade_ref.set(trade_data)

        return {
            "tradeId": trade_ref.id,
            "proposerUid": proposer_uid,
            "targetUid": target_uid,
            "proposerPlayers": prop_players,
            "targetPlayers": tgt_players,
            "status": "pending",
        }

    def respond_trade(self, lid: str, trade_id: str, uid: str,
                      action: str) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        trade_ref = league_ref.collection("trades").document(trade_id)
        trade_doc = trade_ref.get()

        if not trade_doc.exists:
            raise ValueError("Trade not found")

        trade = trade_doc.to_dict()
        if trade["status"] != "pending":
            raise ValueError("Trade is no longer pending")
        if uid != trade["targetUid"]:
            raise ValueError("Only the target can accept/decline")

        if action == "decline":
            trade_ref.update({
                "status": "declined",
                "resolvedAt": SERVER_TIMESTAMP,
            })
            return {"status": "declined"}

        if action == "accept":
            league = league_ref.get().to_dict()
            mode = league.get("tradeApproval", "vote")

            if mode == "instant":
                self._execute_trade(lid, trade)
                trade_ref.update({
                    "status": "accepted",
                    "resolvedAt": SERVER_TIMESTAMP,
                })
                return {"status": "accepted"}
            elif mode == "admin":
                trade_ref.update({"status": "awaiting_admin"})
                return {"status": "awaiting_admin"}
            else:
                trade_ref.update({"status": "awaiting_vote"})
                return {"status": "awaiting_vote"}

        raise ValueError("Action must be 'accept' or 'decline'")

    def admin_approve(self, lid: str, trade_id: str, uid: str) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league = league_ref.get().to_dict()
        if league["adminUid"] != uid:
            raise ValueError("Only admin can approve trades")

        trade_ref = league_ref.collection("trades").document(trade_id)
        trade = trade_ref.get().to_dict()
        if trade["status"] != "awaiting_admin":
            raise ValueError("Trade is not awaiting admin approval")

        self._execute_trade(lid, trade)
        trade_ref.update({
            "status": "accepted",
            "resolvedAt": SERVER_TIMESTAMP,
        })
        return {"status": "accepted"}

    def cast_veto(self, lid: str, trade_id: str, uid: str) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        trade_ref = league_ref.collection("trades").document(trade_id)
        trade = trade_ref.get().to_dict()

        if trade["status"] != "awaiting_vote":
            raise ValueError("Trade is not in voting phase")
        if uid in (trade["proposerUid"], trade["targetUid"]):
            raise ValueError("Trade participants cannot veto")

        vetos = trade.get("vetoVotes", [])
        if uid in vetos:
            raise ValueError("Already voted")

        vetos.append(uid)
        members = list(league_ref.collection("members").get())
        non_participants = len(members) - 2
        threshold = non_participants / 2

        if len(vetos) >= threshold:
            trade_ref.update({
                "vetoVotes": vetos,
                "status": "vetoed",
                "resolvedAt": SERVER_TIMESTAMP,
            })
            return {"status": "vetoed", "vetoCount": len(vetos)}

        trade_ref.update({"vetoVotes": vetos})

        if non_participants - len(vetos) < threshold - len(vetos):
            self._execute_trade(lid, trade)
            trade_ref.update({
                "status": "accepted",
                "resolvedAt": SERVER_TIMESTAMP,
            })
            return {"status": "accepted"}

        return {"status": "awaiting_vote", "vetoCount": len(vetos)}

    def get_trades(self, lid: str, status: str = None) -> list:
        ref = (self.db.collection("leagues").document(lid)
               .collection("trades"))
        if status:
            docs = ref.where("status", "==", status).get()
        else:
            docs = ref.get()
        return [{"tradeId": d.id, **d.to_dict()} for d in docs]

    def _execute_trade(self, lid: str, trade: dict):
        league_ref = self.db.collection("leagues").document(lid)
        prop_uid = trade["proposerUid"]
        tgt_uid = trade["targetUid"]

        prop_squad_ref = league_ref.collection("squads").document(prop_uid)
        tgt_squad_ref = league_ref.collection("squads").document(tgt_uid)

        prop_squad = prop_squad_ref.get().to_dict()["players"]
        tgt_squad = tgt_squad_ref.get().to_dict()["players"]

        prop_out_ids = {p["playerId"] for p in trade["proposerPlayers"]}
        tgt_out_ids = {p["playerId"] for p in trade["targetPlayers"]}

        tgt_incoming = [p for p in prop_squad if p["playerId"] in prop_out_ids]
        prop_incoming = [p for p in tgt_squad if p["playerId"] in tgt_out_ids]

        new_prop = [p for p in prop_squad if p["playerId"] not in prop_out_ids]
        new_prop.extend(prop_incoming)
        new_tgt = [p for p in tgt_squad if p["playerId"] not in tgt_out_ids]
        new_tgt.extend(tgt_incoming)

        prop_squad_ref.update({"players": new_prop})
        tgt_squad_ref.update({"players": new_tgt})

    def _get_squad(self, lid: str, uid: str) -> list:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError(f"No squad found for user")
        return doc.to_dict()["players"]
