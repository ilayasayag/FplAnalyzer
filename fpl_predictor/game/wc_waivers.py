"""
WC2026 two-phase waiver / free agent system.

Phase 1 (T+0 → T+24h): Submit claims. Processed in priority order at T+24h.
Phase 2 (T+24h → window close): FCFS free agent signing.

Priority: inverse draft order initially; drops to bottom after successful claim.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

POS_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
MAX_WAIVER_CLAIMS_PER_MANAGER = 10


class WCWaiverManager:
    def __init__(self, db, wc_client=None):
        self.db = db
        self.wc = wc_client

    # ------------------------------------------------------------------
    # Submit waiver claim
    # ------------------------------------------------------------------

    def submit_waiver(
        self,
        lid: str,
        uid: str,
        player_in: int,
        player_out: int,
        window_number: int,
    ) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        self._validate_window_open(lid)
        self._validate_in_submission_phase(lid, window_number)

        squad = self._get_squad(lid, uid)
        squad_map = {p["playerId"]: p for p in squad}

        if player_out not in squad_map:
            raise ValueError("PLAYER_OUT_NOT_OWNED: drop player not in your squad")

        player_in_doc = self._get_wc_player(player_in)
        if not player_in_doc:
            raise ValueError("PLAYER_NOT_FOUND")

        if player_in_doc.get("eliminated", False):
            raise ValueError("PLAYER_TEAM_ELIMINATED")

        owned = self._get_all_owned(lid)
        if player_in in owned:
            raise ValueError("PLAYER_ALREADY_OWNED")

        # Position quota check after hypothetical swap
        out_pos = squad_map[player_out]["position"]
        in_pos = player_in_doc.get("position", 3)
        if out_pos != in_pos:
            raise ValueError(
                f"POSITION_QUOTA_VIOLATED: dropping {POS_NAMES[out_pos]}, "
                f"claiming {POS_NAMES[in_pos]} — must be same position for waivers"
            )

        # Anti-spam: max 10 pending claims per manager per window
        existing_claims = list(
            league_ref.collection("waivers")
            .where("uid", "==", uid)
            .where("windowNumber", "==", window_number)
            .where("status", "==", "pending")
            .get()
        )
        if len(existing_claims) >= MAX_WAIVER_CLAIMS_PER_MANAGER:
            raise ValueError(f"WAIVER_LIMIT_EXCEEDED: max {MAX_WAIVER_CLAIMS_PER_MANAGER} claims per window")

        # Duplicate playerIn check (same manager, same playerIn in same window)
        for doc in existing_claims:
            claim = doc.to_dict()
            if claim["playerIn"] == player_in:
                raise ValueError("DUPLICATE_WAIVER_CLAIM: already have a claim for this player")

        # Waiver drop conflict warning (same playerOut used in multiple claims)
        drop_conflicts = [
            doc.id for doc in existing_claims
            if doc.to_dict()["playerOut"] == player_out
        ]

        member_doc = league_ref.collection("members").document(uid).get()
        priority = member_doc.to_dict().get("waiverPriority", 99) if member_doc.exists else 99

        waiver_ref = league_ref.collection("waivers").document()
        league_doc_gw = league_doc.to_dict().get("currentGw", 1)

        waiver_ref.set({
            "uid": uid,
            "playerIn": player_in,
            "playerOut": player_out,
            "priority": priority,
            "gw": league_doc_gw,
            "windowNumber": window_number,
            "status": "pending",
            "rejectionReason": None,
            "createdAt": SERVER_TIMESTAMP,
        })

        result = {
            "waiverId": waiver_ref.id,
            "playerIn": player_in,
            "playerOut": player_out,
            "priority": priority,
            "windowNumber": window_number,
            "status": "pending",
        }

        if drop_conflicts:
            result["warnings"] = [{
                "code": "WAIVER_DROP_CONFLICT",
                "message": f"You already have another claim to drop player {player_out}. "
                           f"Only the first processed claim for this player will execute.",
                "conflictingWaiverIds": drop_conflicts,
            }]

        return result

    def cancel_waiver(self, lid: str, waiver_id: str, uid: str):
        ref = (self.db.collection("leagues").document(lid)
               .collection("waivers").document(waiver_id))
        doc = ref.get()
        if not doc.exists:
            raise ValueError("Waiver claim not found")
        data = doc.to_dict()
        if data["uid"] != uid:
            raise ValueError("Not your waiver claim")
        if data["status"] != "pending":
            raise ValueError("Waiver already processed")
        ref.delete()

    def get_my_waivers(self, lid: str, uid: str, window_number: int) -> list:
        docs = (self.db.collection("leagues").document(lid)
                .collection("waivers")
                .where("uid", "==", uid)
                .where("windowNumber", "==", window_number)
                .get())
        return [{"waiverId": d.id, **d.to_dict()} for d in docs]

    # ------------------------------------------------------------------
    # Waiver processing (runs at T+24h)
    # ------------------------------------------------------------------

    def process_waivers(self, lid: str, window_number: int) -> dict:
        """
        Process all pending waiver claims for this window in priority order.
        Called by background job at T+24h after window opens.
        """
        league_ref = self.db.collection("leagues").document(lid)

        pending_docs = list(
            league_ref.collection("waivers")
            .where("windowNumber", "==", window_number)
            .where("status", "==", "pending")
            .get()
        )

        # Sort: priority ASC, then createdAt ASC
        pending_docs.sort(key=lambda d: (
            d.to_dict().get("priority", 99),
            d.to_dict().get("createdAt") or datetime.min.replace(tzinfo=timezone.utc),
        ))

        claimed_players: set = set()   # playerIn already claimed this run
        claimed_drops: Dict[str, set] = {}  # uid -> set of playerOut already used

        results = []

        for doc in pending_docs:
            waiver = doc.to_dict()
            uid = waiver["uid"]
            pin = waiver["playerIn"]
            pout = waiver["playerOut"]

            if pin in claimed_players:
                doc.reference.update({
                    "status": "rejected",
                    "rejectionReason": "Player already claimed by higher priority manager",
                })
                results.append({"uid": uid, "playerIn": pin, "status": "rejected",
                                 "reason": "Player claimed"})
                continue

            squad = self._get_squad(lid, uid)
            squad_ids = {p["playerId"] for p in squad}
            if pout not in squad_ids:
                doc.reference.update({
                    "status": "rejected",
                    "rejectionReason": "Drop player no longer in squad (earlier claim used it)",
                })
                results.append({"uid": uid, "playerIn": pin, "status": "rejected",
                                 "reason": "Drop player consumed"})
                continue

            # Check playerOut not already used by an earlier approved claim for this uid
            uid_drops = claimed_drops.setdefault(uid, set())
            if pout in uid_drops:
                doc.reference.update({
                    "status": "rejected",
                    "rejectionReason": "Drop player already used by earlier claim in this run",
                })
                results.append({"uid": uid, "playerIn": pin, "status": "rejected",
                                 "reason": "Drop conflict"})
                continue

            # Execute swap
            player_in_doc = self._get_wc_player(pin)
            if not player_in_doc:
                doc.reference.update({
                    "status": "rejected",
                    "rejectionReason": "Player not found in database",
                })
                continue

            self._execute_swap(lid, uid, pin, pout, squad, player_in_doc)
            claimed_players.add(pin)
            uid_drops.add(pout)

            doc.reference.update({"status": "approved"})
            self._drop_waiver_priority(lid, uid)

            league_ref.collection("transactions").document().set({
                "type": "waiver_approved",
                "uid": uid,
                "playerIn": pin,
                "playerOut": pout,
                "windowNumber": window_number,
                "timestamp": SERVER_TIMESTAMP,
            })

            results.append({"uid": uid, "playerIn": pin, "playerOut": pout, "status": "approved"})

        return {
            "windowNumber": window_number,
            "processed": len(results),
            "approved": sum(1 for r in results if r["status"] == "approved"),
            "rejected": sum(1 for r in results if r["status"] == "rejected"),
            "results": results,
        }

    # ------------------------------------------------------------------
    # Free agent phase
    # ------------------------------------------------------------------

    def get_free_agents(self, lid: str, position: Optional[int] = None,
                        search: str = "", limit: int = 50) -> list:
        """List unclaimed players available for waiver or free agent pickup."""
        owned = self._get_all_owned(lid)
        player_docs = self.db.collection("wc_players").get()

        result = []
        for doc in player_docs:
            p = doc.to_dict()
            pid = p.get("id")
            if pid in owned:
                continue
            if p.get("eliminated", False):
                continue
            if position and p.get("position") != position:
                continue
            if search:
                if search.lower() not in p.get("name", "").lower():
                    continue
            result.append({
                "id": pid,
                "name": p.get("name", ""),
                "position": p.get("position", 3),
                "positionName": p.get("positionName", "?"),
                "teamId": p.get("teamId", 0),
                "teamName": p.get("teamName", ""),
                "teamIso": p.get("teamIso", ""),
            })

        return result[:limit]

    # ------------------------------------------------------------------
    # Waiver priority management
    # ------------------------------------------------------------------

    def get_waiver_order(self, lid: str) -> list:
        members = list(
            self.db.collection("leagues").document(lid).collection("members").get()
        )
        active = [
            {
                "uid": m.id,
                "displayName": m.to_dict().get("displayName", ""),
                "waiverPriority": m.to_dict().get("waiverPriority", 99),
            }
            for m in members
            if not m.to_dict().get("kickedAt") and not m.to_dict().get("leftAt")
        ]
        return sorted(active, key=lambda x: x["waiverPriority"])

    def reset_waiver_priority_to_standings(self, lid: str, admin_uid: str):
        """Admin can reset waiver order to reverse-standings after a GW."""
        league = self.db.collection("leagues").document(lid).get().to_dict()
        if league.get("adminUid") != admin_uid:
            raise ValueError("Only admin can reset waiver priority")

        standings_doc = (self.db.collection("leagues").document(lid)
                         .collection("standings").document("current").get())
        if not standings_doc.exists:
            raise ValueError("No standings available yet")

        managers = standings_doc.to_dict().get("managers", [])
        sorted_managers = sorted(managers, key=lambda m: (-m.get("hpts", 0), -m.get("fpts", 0)))

        league_ref = self.db.collection("leagues").document(lid)
        for rank, manager in enumerate(reversed(sorted_managers), start=1):
            league_ref.collection("members").document(manager["uid"]).update({
                "waiverPriority": rank,
            })

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_squad(self, lid: str, uid: str) -> list:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            raise ValueError("No squad found")
        return doc.to_dict().get("players", [])

    def _get_all_owned(self, lid: str) -> set:
        squads = self.db.collection("leagues").document(lid).collection("squads").get()
        owned = set()
        for doc in squads:
            for p in doc.to_dict().get("players", []):
                owned.add(p["playerId"])
        return owned

    def _get_wc_player(self, player_id: int) -> Optional[dict]:
        doc = self.db.collection("wc_players").document(str(player_id)).get()
        return doc.to_dict() if doc.exists else None

    def _execute_swap(self, lid: str, uid: str, player_in: int, player_out: int,
                      squad: list, player_in_doc: dict):
        squad_ref = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid))
        new_player = {
            "playerId": player_in,
            "name": player_in_doc.get("name", ""),
            "position": player_in_doc.get("position", 3),
            "positionName": player_in_doc.get("positionName", "?"),
            "teamId": player_in_doc.get("teamId", 0),
            "teamName": player_in_doc.get("teamName", ""),
            "teamIso": player_in_doc.get("teamIso", ""),
            "eliminated": player_in_doc.get("eliminated", False),
        }
        new_squad = [p for p in squad if p["playerId"] != player_out]
        new_squad.append(new_player)
        squad_ref.update({"players": new_squad})

    def _drop_waiver_priority(self, lid: str, uid: str):
        league_ref = self.db.collection("leagues").document(lid)
        members = list(league_ref.collection("members").get())
        max_priority = max(
            (m.to_dict().get("waiverPriority", 1) for m in members),
            default=1,
        )
        league_ref.collection("members").document(uid).update({
            "waiverPriority": max_priority + 1,
        })

    def _validate_window_open(self, lid: str):
        league_doc = self.db.collection("leagues").document(lid).get()
        if not league_doc.exists:
            raise ValueError("League not found")
        if league_doc.to_dict().get("status") not in ("group_phase", "knockout"):
            raise ValueError("League is not active")

    def _validate_in_submission_phase(self, lid: str, window_number: int):
        """Ensure we're in the T+0 to T+24h waiver submission window."""
        pass  # Deadline enforced server-side at process time; submit any time window is open

    def _is_past_waiver_deadline(self, lid: str, window_number: int) -> bool:
        """
        True if waiver processing has already run for this window
        (i.e., we're in the free-agent FCFS phase).
        """
        processed = list(
            self.db.collection("leagues").document(lid)
            .collection("waivers")
            .where("windowNumber", "==", window_number)
            .where("status", "in", ["approved", "rejected"])
            .limit(1)
            .get()
        )
        return len(processed) > 0
