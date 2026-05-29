"""
WC2026 trade system.

Like-for-like position trades.
Veto threshold: ceil(N/3) — not N/2.
Mid-fixture block: cannot trade players whose match is in progress.
Trade auto-expires 48h after proposal.
"""

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT"}


class WCTradeManager:
    def __init__(self, db, wc_client=None):
        self.db = db
        self.wc = wc_client

    def propose_trade(
        self,
        lid: str,
        proposer_uid: str,
        target_uid: str,
        proposer_player_ids: List[int],
        target_player_ids: List[int],
        message: str = "",
    ) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        league = league_doc.to_dict()

        if league.get("tradeApproval") == "none":
            raise ValueError("Trading is disabled in this league")
        if league.get("status") not in ("group_phase", "knockout"):
            raise ValueError("League is not active")

        self._validate_window_open(lid, league)

        if proposer_uid == target_uid:
            raise ValueError("TRADE_TARGET_INVALID")

        members = list(league_ref.collection("members").get())
        member_ids = {
            m.id for m in members
            if not m.to_dict().get("kickedAt") and not m.to_dict().get("leftAt")
        }
        if target_uid not in member_ids:
            raise ValueError("TRADE_TARGET_INVALID")

        if not 1 <= len(proposer_player_ids) <= 5:
            raise ValueError("TRADE_SIZE_INVALID")
        if len(proposer_player_ids) != len(target_player_ids):
            raise ValueError("TRADE_NOT_BALANCED")

        if message and len(message) > 280:
            raise ValueError("TRADE_MESSAGE_INVALID")

        prop_squad = self._get_squad(lid, proposer_uid)
        tgt_squad = self._get_squad(lid, target_uid)
        prop_map = {p["playerId"]: p for p in prop_squad}
        tgt_map = {p["playerId"]: p for p in tgt_squad}

        for pid in proposer_player_ids:
            if pid not in prop_map:
                raise ValueError(f"PROPOSER_PLAYERS_NOT_OWNED: player {pid} not in your squad")
        for pid in target_player_ids:
            if pid not in tgt_map:
                raise ValueError(f"TARGET_PLAYERS_NOT_OWNED: player {pid} not in target's squad")

        prop_positions = Counter(prop_map[pid]["position"] for pid in proposer_player_ids)
        tgt_positions = Counter(tgt_map[pid]["position"] for pid in target_player_ids)
        if prop_positions != tgt_positions:
            raise ValueError(
                f"TRADE_POSITION_MISMATCH: offering "
                f"{_pos_desc(prop_positions)}, requesting {_pos_desc(tgt_positions)}"
            )

        # Mid-fixture check
        all_player_ids = proposer_player_ids + target_player_ids
        self._check_mid_fixture(all_player_ids, prop_map, tgt_map)

        # Check pending trade limits
        existing_prop = list(
            league_ref.collection("trades")
            .where("proposerUid", "==", proposer_uid)
            .where("status", "==", "pending")
            .get()
        )
        if len(existing_prop) >= 5:
            raise ValueError("TRADE_LIMIT_EXCEEDED")

        existing_tgt_incoming = list(
            league_ref.collection("trades")
            .where("targetUid", "==", target_uid)
            .where("status", "==", "pending")
            .get()
        )
        if len(existing_tgt_incoming) >= 10:
            raise ValueError("TARGET_TRADE_LIMIT")

        n = len(member_ids)
        veto_threshold = math.ceil(n / 3)

        prop_players = [
            {
                "playerId": pid,
                "position": prop_map[pid]["position"],
                "positionName": POS_NAMES[prop_map[pid]["position"]],
                "name": prop_map[pid].get("name", ""),
                "teamId": prop_map[pid].get("teamId", 0),
            }
            for pid in proposer_player_ids
        ]
        tgt_players = [
            {
                "playerId": pid,
                "position": tgt_map[pid]["position"],
                "positionName": POS_NAMES[tgt_map[pid]["position"]],
                "name": tgt_map[pid].get("name", ""),
                "teamId": tgt_map[pid].get("teamId", 0),
            }
            for pid in target_player_ids
        ]

        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

        trade_ref = league_ref.collection("trades").document()
        trade_ref.set({
            "proposerUid": proposer_uid,
            "targetUid": target_uid,
            "proposerPlayers": prop_players,
            "targetPlayers": tgt_players,
            "message": message[:280] if message else None,
            "status": "pending",
            "vetoVotes": [],
            "approveVotes": [],
            "vetoThreshold": veto_threshold,
            "createdAt": SERVER_TIMESTAMP,
            "resolvedAt": None,
            "expiresAt": expires_at,
        })

        return {
            "tradeId": trade_ref.id,
            "proposerUid": proposer_uid,
            "targetUid": target_uid,
            "proposerPlayers": prop_players,
            "targetPlayers": tgt_players,
            "status": "pending",
            "vetoThreshold": veto_threshold,
        }

    def respond_trade(self, lid: str, trade_id: str, uid: str, action: str) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        trade_ref = league_ref.collection("trades").document(trade_id)
        trade_doc = trade_ref.get()

        if not trade_doc.exists:
            raise ValueError("Trade not found")

        trade = trade_doc.to_dict()
        if trade["status"] != "pending":
            raise ValueError("Trade is no longer pending")
        if uid != trade["targetUid"]:
            raise ValueError("Only the trade target can accept or decline")

        self._check_trade_expired(trade)

        if action == "decline":
            trade_ref.update({"status": "declined", "resolvedAt": SERVER_TIMESTAMP})
            return {"status": "declined"}

        if action == "accept":
            league = league_ref.get().to_dict()
            mode = league.get("tradeApproval", "vote")

            # Re-check mid-fixture at accept time
            all_ids = (
                [p["playerId"] for p in trade["proposerPlayers"]] +
                [p["playerId"] for p in trade["targetPlayers"]]
            )
            prop_map = {p["playerId"]: p for p in self._get_squad(lid, trade["proposerUid"])}
            tgt_map = {p["playerId"]: p for p in self._get_squad(lid, trade["targetUid"])}
            try:
                self._check_mid_fixture(all_ids, prop_map, tgt_map)
            except ValueError as e:
                trade_ref.update({"status": "declined", "resolvedAt": SERVER_TIMESTAMP,
                                  "declineReason": str(e)})
                raise

            if mode == "instant":
                self._execute_trade(lid, trade)
                trade_ref.update({"status": "accepted", "resolvedAt": SERVER_TIMESTAMP})
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
        trade_doc = trade_ref.get()
        if not trade_doc.exists:
            raise ValueError("Trade not found")
        trade = trade_doc.to_dict()
        if trade["status"] != "awaiting_admin":
            raise ValueError("Trade is not awaiting admin approval")

        self._execute_trade(lid, trade)
        trade_ref.update({"status": "accepted", "resolvedAt": SERVER_TIMESTAMP})
        return {"status": "accepted"}

    def cast_veto(self, lid: str, trade_id: str, uid: str) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        trade_ref = league_ref.collection("trades").document(trade_id)
        trade_doc = trade_ref.get()

        if not trade_doc.exists:
            raise ValueError("Trade not found")

        trade = trade_doc.to_dict()
        if trade["status"] != "awaiting_vote":
            raise ValueError("Trade is not in voting phase")
        if uid in (trade["proposerUid"], trade["targetUid"]):
            raise ValueError("Trade participants cannot veto")

        self._check_trade_expired(trade)

        vetos = trade.get("vetoVotes", [])
        if uid in vetos:
            raise ValueError("Already voted")

        vetos = vetos + [uid]
        threshold = trade.get("vetoThreshold", 2)

        if len(vetos) >= threshold:
            trade_ref.update({
                "vetoVotes": vetos,
                "status": "vetoed",
                "resolvedAt": SERVER_TIMESTAMP,
            })
            return {"status": "vetoed", "vetoCount": len(vetos)}

        trade_ref.update({"vetoVotes": vetos})

        # Check if veto is now mathematically impossible
        members = list(league_ref.collection("members").get())
        non_participants = len(members) - 2
        remaining_potential = non_participants - len(vetos)
        if remaining_potential < threshold - len(vetos):
            self._execute_trade(lid, trade)
            trade_ref.update({"status": "accepted", "resolvedAt": SERVER_TIMESTAMP})
            return {"status": "accepted"}

        return {"status": "awaiting_vote", "vetoCount": len(vetos), "threshold": threshold}

    def cancel_trade(self, lid: str, trade_id: str, uid: str) -> dict:
        trade_ref = (self.db.collection("leagues").document(lid)
                     .collection("trades").document(trade_id))
        trade_doc = trade_ref.get()
        if not trade_doc.exists:
            raise ValueError("Trade not found")
        trade = trade_doc.to_dict()
        if trade["proposerUid"] != uid:
            raise ValueError("Only the proposer can cancel")
        if trade["status"] not in ("pending", "awaiting_vote", "awaiting_admin"):
            raise ValueError("Trade cannot be cancelled in its current state")

        trade_ref.update({"status": "cancelled", "resolvedAt": SERVER_TIMESTAMP})
        return {"status": "cancelled"}

    def get_trades(self, lid: str, status: Optional[str] = None) -> list:
        ref = self.db.collection("leagues").document(lid).collection("trades")
        if status:
            docs = ref.where("status", "==", status).get()
        else:
            docs = ref.get()
        return [{"tradeId": d.id, **d.to_dict()} for d in docs]

    def expire_stale_trades(self, lid: str):
        """Mark trades past their 48h expiry as expired. Call periodically."""
        now = datetime.now(timezone.utc)
        pending = (self.db.collection("leagues").document(lid)
                   .collection("trades")
                   .where("status", "in", ["pending"])
                   .get())
        for doc in pending:
            trade = doc.to_dict()
            expires_at = trade.get("expiresAt")
            if expires_at and expires_at <= now:
                doc.reference.update({"status": "expired", "resolvedAt": SERVER_TIMESTAMP})

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _execute_trade(self, lid: str, trade: dict):
        prop_uid = trade["proposerUid"]
        tgt_uid = trade["targetUid"]
        prop_squad_ref = (self.db.collection("leagues").document(lid)
                          .collection("squads").document(prop_uid))
        tgt_squad_ref = (self.db.collection("leagues").document(lid)
                         .collection("squads").document(tgt_uid))

        prop_squad = prop_squad_ref.get().to_dict()["players"]
        tgt_squad = tgt_squad_ref.get().to_dict()["players"]

        prop_out_ids = {p["playerId"] for p in trade["proposerPlayers"]}
        tgt_out_ids = {p["playerId"] for p in trade["targetPlayers"]}

        # Build incoming player objects (keep squad metadata, swap ownership)
        prop_incoming = [p for p in tgt_squad if p["playerId"] in tgt_out_ids]
        tgt_incoming = [p for p in prop_squad if p["playerId"] in prop_out_ids]

        new_prop = [p for p in prop_squad if p["playerId"] not in prop_out_ids] + prop_incoming
        new_tgt = [p for p in tgt_squad if p["playerId"] not in tgt_out_ids] + tgt_incoming

        prop_squad_ref.update({"players": new_prop})
        tgt_squad_ref.update({"players": new_tgt})

        league_ref = self.db.collection("leagues").document(lid)
        league_ref.collection("transactions").document().set({
            "type": "trade_accepted",
            "proposerUid": prop_uid,
            "targetUid": tgt_uid,
            "proposerPlayers": trade["proposerPlayers"],
            "targetPlayers": trade["targetPlayers"],
            "timestamp": SERVER_TIMESTAMP,
        })

    def _get_squad(self, lid: str, uid: str) -> list:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError(f"No squad found for user {uid}")
        return doc.to_dict().get("players", [])

    def _check_mid_fixture(
        self,
        player_ids: List[int],
        prop_map: Dict,
        tgt_map: Dict,
    ):
        """
        Raises ValueError if any involved player's national team has a match
        currently in progress.
        """
        if not self.wc:
            return

        all_map = {**prop_map, **tgt_map}
        team_ids = {all_map[pid]["teamId"] for pid in player_ids if pid in all_map}

        try:
            live_fixtures = self.wc.get_live_fixtures()
        except Exception:
            return

        live_team_ids = set()
        for f in live_fixtures:
            status = f.get("fixture", {}).get("status", {}).get("short", "")
            if status in LIVE_STATUSES:
                teams = f.get("teams", {})
                live_team_ids.add(teams.get("home", {}).get("id"))
                live_team_ids.add(teams.get("away", {}).get("id"))

        blocked = team_ids & live_team_ids
        if blocked:
            raise ValueError(f"PLAYER_MID_FIXTURE: teams {blocked} have matches in progress")

    def _validate_window_open(self, lid: str, league: dict):
        from fpl_predictor.game.wc_gameweeks import is_transfer_window_open
        gw = league.get("currentGw", 1)
        if not is_transfer_window_open(gw - 1 if gw > 1 else 0):
            raise ValueError("TRADES_BLOCKED_WINDOW_CLOSED")

    def _check_trade_expired(self, trade: dict):
        expires_at = trade.get("expiresAt")
        if expires_at and expires_at <= datetime.now(timezone.utc):
            raise ValueError("Trade has expired")


def _pos_desc(counter: Counter) -> str:
    return ", ".join(f"{c} {POS_NAMES[p]}" for p, c in sorted(counter.items()))
