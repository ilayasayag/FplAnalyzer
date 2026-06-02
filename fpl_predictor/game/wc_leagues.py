"""
WC2026 league management: create, join, configure, lock for draft.

Extends the base league system with WC-specific fields:
  knockoutStartGw, leaguePhaseGws, knockoutQualifiers, draftAt.
"""

import random
import string
from datetime import datetime, timezone
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from fpl_predictor.game.wc_gameweeks import (
    compute_knockout_start_gw,
    compute_league_phase_gws,
    compute_knockout_qualifiers,
)

VALID_TRADE_MODES = {"instant", "admin", "vote", "none"}
VALID_PICK_TIMERS = {30, 60, 90, 120, 180, 300}


def _generate_invite_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


class WCLeagueManager:
    def __init__(self, db):
        self.db = db

    def create_league(
        self,
        uid: str,
        name: str,
        display_name: str,
        trade_approval: str = "vote",
        pick_timer: int = 60,
        max_members: int = 8,
        draft_at: datetime = None,
    ) -> dict:
        if trade_approval not in VALID_TRADE_MODES:
            raise ValueError(f"tradeApproval must be one of {VALID_TRADE_MODES}")
        if pick_timer not in VALID_PICK_TIMERS:
            raise ValueError(f"pickTimer must be one of {VALID_PICK_TIMERS}")
        # Load tournament rules from Firestore config
        config_doc = self.db.collection("wc_config").document("tournament").get()
        rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}

        league_size_conf = rules.get("leagueSize", {})
        min_managers = league_size_conf.get("minManagers", 6)
        max_managers = min(league_size_conf.get("maxManagers", 10), 10)

        if not min_managers <= max_members <= max_managers:
            raise ValueError(f"maxMembers must be between {min_managers} and {max_managers}")


        if len(name.strip()) < 2:
            raise ValueError("League name must be at least 2 characters")

        invite_code = _generate_invite_code()
        while self._code_exists(invite_code):
            invite_code = _generate_invite_code()

        # Dynamically calculated based on max_members and rules config
        size_rules = rules.get("leagueSizeRules", {}).get(str(max_members), {})
        if size_rules:
            knockout_start = size_rules.get("knockoutStartGw", 7)
            league_phase_gws = size_rules.get("leaguePhaseGws", [1, 2, 3, 4, 5, 6])
            qualifiers = size_rules.get("knockoutQualifiers", 4)
        else:
            knockout_start = compute_knockout_start_gw(max_members)
            league_phase_gws = compute_league_phase_gws(max_members)
            qualifiers = compute_knockout_qualifiers(max_members)


        league_ref = self.db.collection("leagues").document()
        league_data = {
            "name": name.strip(),
            "inviteCode": invite_code,
            "adminUid": uid,
            "format": "h2h",
            "status": "pre_draft",
            "maxMembers": max_members,
            "pickTimer": pick_timer,
            "tradeApproval": trade_approval,
            "knockoutStartGw": knockout_start,
            "leaguePhaseGws": league_phase_gws,
            "knockoutQualifiers": qualifiers,
            "currentGw": None,
            "draftAt": draft_at,
            "seasonStartedAt": None,
            "createdAt": SERVER_TIMESTAMP,
        }
        league_ref.set(league_data)

        league_ref.collection("members").document(uid).set({
            "displayName": display_name,
            "teamName": f"{display_name}'s World",
            "draftPosition": None,
            "role": "admin",
            "waiverPriority": 1,
            "squadFrozen": False,
            "kickedAt": None,
            "leftAt": None,
            "joinedAt": SERVER_TIMESTAMP,
            "predictions": {
                "predictedWinner": None,
                "predictedTopScorer": None,
                "predictionsLockedAt": None,
            },
        })

        self._add_league_to_user(uid, league_ref.id)

        return {
            "leagueId": league_ref.id,
            "inviteCode": invite_code,
            "name": name.strip(),
            "status": "pre_draft",
            "maxMembers": max_members,
            "knockoutStartGw": knockout_start,
            "knockoutQualifiers": qualifiers,
        }

    def join_league(self, uid: str, invite_code: str, display_name: str,
                    team_name: str = None) -> dict:
        leagues = (self.db.collection("leagues")
                   .where("inviteCode", "==", invite_code.upper())
                   .limit(1).get())
        if not leagues:
            raise ValueError("Invalid invite code")

        league_doc = leagues[0]
        league = league_doc.to_dict()
        lid = league_doc.id

        if league["status"] != "pre_draft":
            raise ValueError("League is no longer accepting new members")

        member_docs = list(league_doc.reference.collection("members").get())
        if len(member_docs) >= league["maxMembers"]:
            raise ValueError("League is full")

        existing = league_doc.reference.collection("members").document(uid).get()
        if existing.exists:
            kicked_at = existing.to_dict().get("kickedAt")
            if kicked_at:
                raise ValueError("You have been removed from this league")
            raise ValueError("Already a member of this league")

        user_leagues = self._get_user_leagues(uid)
        if len(user_leagues) >= 5:
            raise ValueError("Maximum 5 active leagues per user")

        league_doc.reference.collection("members").document(uid).set({
            "displayName": display_name,
            "teamName": team_name or f"{display_name}'s World",
            "draftPosition": None,
            "role": "manager",
            "waiverPriority": len(member_docs) + 1,
            "squadFrozen": False,
            "kickedAt": None,
            "leftAt": None,
            "joinedAt": SERVER_TIMESTAMP,
            "predictions": {
                "predictedWinner": None,
                "predictedTopScorer": None,
                "predictionsLockedAt": None,
            },
        })

        self._add_league_to_user(uid, lid)

        return {
            "leagueId": lid,
            "name": league["name"],
            "members": len(member_docs) + 1,
            "maxMembers": league["maxMembers"],
        }

    def get_league(self, lid: str, uid: str) -> dict:
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")

        member_ref = doc.reference.collection("members").document(uid)
        member = member_ref.get()
        league = doc.to_dict()
        # Simulated (showcase/demo) leagues are publicly viewable by any
        # authenticated user. If the caller isn't in the members sub-collection
        # yet, treat them as a read-only participant so they can still see
        # the league data and squad breakdown (their own squad fetch will return
        # empty, which the frontend already handles gracefully).
        if not member.exists and not league.get("simulated"):
            raise ValueError("You are not a member of this league")
        member_docs = list(doc.reference.collection("members").get())

        members = []
        for m in member_docs:
            md = m.to_dict()
            if md.get("kickedAt") or md.get("leftAt"):
                continue
            members.append({
                "uid": m.id,
                "displayName": md.get("displayName", ""),
                "teamName": md.get("teamName", ""),
                "role": md.get("role", "manager"),
                "draftPosition": md.get("draftPosition"),
                "waiverPriority": md.get("waiverPriority"),
            })

        return {
            "leagueId": lid,
            **league,
            "memberCount": len(members),
            "members": members,
            "myRole": member.to_dict().get("role", "manager"),
        }

    def get_my_leagues(self, uid: str) -> list:
        user_doc = self.db.collection("users").document(uid).get()
        if not user_doc.exists:
            return []
        league_ids = user_doc.to_dict().get("leagues", [])
        result = []
        for lid in league_ids:
            doc = self.db.collection("leagues").document(lid).get()
            if not doc.exists:
                continue
            d = doc.to_dict()
            members = [
                m for m in doc.reference.collection("members").get()
                if not m.to_dict().get("kickedAt") and not m.to_dict().get("leftAt")
            ]
            result.append({
                "leagueId": lid,
                "name": d["name"],
                "status": d["status"],
                "memberCount": len(members),
                "maxMembers": d["maxMembers"],
                "knockoutStartGw": d.get("knockoutStartGw"),
                "currentGw": d.get("currentGw"),
                "simulated": d.get("simulated", False),
                "isAdmin": d["adminUid"] == uid,
            })
        return result

    def update_league(self, lid: str, uid: str, updates: dict) -> dict:
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] != uid:
            raise ValueError("Only the admin can update league settings")
        if league["status"] not in ("pre_draft",):
            raise ValueError("League settings can only be changed before the draft")

        allowed = {"name", "tradeApproval", "pickTimer", "draftAt"}
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if "tradeApproval" in filtered and filtered["tradeApproval"] not in VALID_TRADE_MODES:
            raise ValueError(f"tradeApproval must be one of {VALID_TRADE_MODES}")
        if "pickTimer" in filtered and filtered["pickTimer"] not in VALID_PICK_TIMERS:
            raise ValueError(f"pickTimer must be one of {VALID_PICK_TIMERS}")

        doc.reference.update(filtered)
        return {"status": "ok", **filtered}

    def kick_member(self, lid: str, admin_uid: str, target_uid: str) -> dict:
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] != admin_uid:
            raise ValueError("Only the admin can kick members")
        if league["status"] not in ("pre_draft",):
            raise ValueError("Members can only be kicked before the draft starts")
        if target_uid == admin_uid:
            raise ValueError("Admin cannot kick themselves")

        doc.reference.collection("members").document(target_uid).update({
            "kickedAt": SERVER_TIMESTAMP,
        })
        self._remove_league_from_user(target_uid, lid)
        return {"status": "kicked", "uid": target_uid}

    def leave_league(self, lid: str, uid: str):
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] == uid:
            raise ValueError("Admin cannot leave the league; transfer admin first")
        if league["status"] not in ("pre_draft",):
            raise ValueError("Cannot leave an active league")

        doc.reference.collection("members").document(uid).update({
            "leftAt": SERVER_TIMESTAMP,
        })
        self._remove_league_from_user(uid, lid)

    def lock_for_draft(self, lid: str, admin_uid: str) -> dict:
        """
        Admin locks the league to start the draft.
        Validates minimum member count, recalculates knockout thresholds
        based on actual member count (maxMembers may have been > actual).
        """
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] != admin_uid:
            raise ValueError("Only the admin can start the draft")
        if league["status"] != "pre_draft":
            raise ValueError("League is not in pre-draft state")

        members = [
            m for m in doc.reference.collection("members").get()
            if not m.to_dict().get("kickedAt") and not m.to_dict().get("leftAt")
        ]
        n = len(members)
        
        # Load tournament rules from Firestore config
        config_doc = self.db.collection("wc_config").document("tournament").get()
        rules = config_doc.to_dict().get("rules", {}) if config_doc.exists else {}

        league_size_conf = rules.get("leagueSize", {})
        min_managers = league_size_conf.get("minManagers", 6)

        if n < min_managers:
            raise ValueError(f"Need at least {min_managers} managers; have {n}")

        # Dynamically calculated based on actual members n and rules config
        size_rules = rules.get("leagueSizeRules", {}).get(str(n), {})
        if size_rules:
            knockout_start = size_rules.get("knockoutStartGw", 7)
            league_phase_gws = size_rules.get("leaguePhaseGws", [1, 2, 3, 4, 5, 6])
            qualifiers = size_rules.get("knockoutQualifiers", 4)
        else:
            knockout_start = compute_knockout_start_gw(n)
            league_phase_gws = compute_league_phase_gws(n)
            qualifiers = compute_knockout_qualifiers(n)


        doc.reference.update({
            "status": "drafting",
            "knockoutStartGw": knockout_start,
            "leaguePhaseGws": league_phase_gws,
            "knockoutQualifiers": qualifiers,
            "actualMemberCount": n,
        })

        return {
            "leagueId": lid,
            "status": "drafting",
            "memberCount": n,
            "knockoutStartGw": knockout_start,
            "leaguePhaseGws": league_phase_gws,
            "knockoutQualifiers": qualifiers,
        }

    def start_season(self, lid: str, admin_uid: str) -> dict:
        """Called after draft completes to transition league to group_phase."""
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] != admin_uid:
            raise ValueError("Only the admin can start the season")
        if league["status"] != "drafting":
            raise ValueError("Draft must complete before starting the season")

        doc.reference.update({
            "status": "group_phase",
            "currentGw": 1,
            "seasonStartedAt": SERVER_TIMESTAMP,
        })

        self._generate_schedule(lid, league.get("leaguePhaseGws", [1, 2, 3]), doc)

        return {"leagueId": lid, "status": "group_phase", "currentGw": 1}

    def _generate_schedule(self, lid: str, league_phase_gws: list, league_doc):
        """Generate round-robin H2H schedule for all league-phase GWs."""
        from fpl_predictor.game.schedule import ScheduleManager
        start_gw = league_phase_gws[0] if league_phase_gws else 1
        end_gw = league_phase_gws[-1] if league_phase_gws else 3
        ScheduleManager(self.db).generate_schedule(lid, start_gw=start_gw, end_gw=end_gw)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _code_exists(self, code: str) -> bool:
        results = (self.db.collection("leagues")
                   .where("inviteCode", "==", code)
                   .limit(1).get())
        return len(results) > 0

    def _get_user_leagues(self, uid: str) -> list:
        user_doc = self.db.collection("users").document(uid).get()
        if not user_doc.exists:
            return []
        return user_doc.to_dict().get("leagues", [])

    def _add_league_to_user(self, uid: str, lid: str):
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            leagues = user_doc.to_dict().get("leagues", [])
            if lid not in leagues:
                leagues.append(lid)
                user_ref.update({"leagues": leagues})
        else:
            user_ref.set({"leagues": [lid]}, merge=True)

    def _remove_league_from_user(self, uid: str, lid: str):
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return
        leagues = user_doc.to_dict().get("leagues", [])
        if lid in leagues:
            leagues.remove(lid)
            user_ref.update({"leagues": leagues})
