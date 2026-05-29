"""
League management: create, join, configure, list.
"""

import random
import string
from datetime import datetime, timezone
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


def _generate_invite_code(length=6):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


VALID_FORMATS = {"h2h", "classic"}
VALID_TRADE_MODES = {"instant", "admin", "vote", "none"}


class LeagueManager:
    def __init__(self, db):
        self.db = db

    def create_league(self, uid: str, name: str, display_name: str,
                      fmt: str = "h2h", trade_approval: str = "vote",
                      pick_timer: int = 30, max_members: int = 8) -> dict:
        if fmt not in VALID_FORMATS:
            raise ValueError(f"Format must be one of {VALID_FORMATS}")
        if trade_approval not in VALID_TRADE_MODES:
            raise ValueError(f"Trade approval must be one of {VALID_TRADE_MODES}")
        if not 2 <= max_members <= 16:
            raise ValueError("Max members must be between 2 and 16")
        if not 10 <= pick_timer <= 120:
            raise ValueError("Pick timer must be between 10 and 120 seconds")

        invite_code = _generate_invite_code()
        while self._code_exists(invite_code):
            invite_code = _generate_invite_code()

        league_ref = self.db.collection("leagues").document()
        league_data = {
            "name": name,
            "inviteCode": invite_code,
            "format": fmt,
            "tradeApproval": trade_approval,
            "pickTimer": pick_timer,
            "maxMembers": max_members,
            "adminUid": uid,
            "status": "recruiting",
            "seasonStartGw": None,
            "currentGw": None,
            "waiverDeadlineHours": 24,
            "redraftsRemaining": 3,
            "createdAt": SERVER_TIMESTAMP,
        }
        league_ref.set(league_data)

        league_ref.collection("members").document(uid).set({
            "displayName": display_name,
            "teamName": f"{display_name}'s XI",
            "draftPosition": None,
            "role": "admin",
            "waiverPriority": 1,
            "joinedAt": SERVER_TIMESTAMP,
        })

        self._add_league_to_user(uid, league_ref.id)

        return {
            "leagueId": league_ref.id,
            "inviteCode": invite_code,
            "name": name,
            "format": fmt,
            "status": "recruiting",
            "maxMembers": max_members,
        }

    def join_league(self, uid: str, invite_code: str, display_name: str,
                    team_name: str = None) -> dict:
        leagues = (self.db.collection("leagues")
                   .where("inviteCode", "==", invite_code)
                   .limit(1).get())
        if not leagues:
            raise ValueError("Invalid invite code")

        league_doc = leagues[0]
        league = league_doc.to_dict()
        lid = league_doc.id

        if league["status"] != "recruiting":
            raise ValueError("League is no longer accepting new members")

        members = list(league_doc.reference.collection("members").get())
        if len(members) >= league["maxMembers"]:
            raise ValueError("League is full")

        existing = league_doc.reference.collection("members").document(uid).get()
        if existing.exists:
            raise ValueError("Already a member of this league")

        league_doc.reference.collection("members").document(uid).set({
            "displayName": display_name,
            "teamName": team_name or f"{display_name}'s XI",
            "draftPosition": None,
            "role": "manager",
            "waiverPriority": len(members) + 1,
            "joinedAt": SERVER_TIMESTAMP,
        })

        self._add_league_to_user(uid, lid)

        return {"leagueId": lid, "name": league["name"], "members": len(members) + 1}

    def get_my_leagues(self, uid: str) -> list:
        user_doc = self.db.collection("users").document(uid).get()
        if not user_doc.exists:
            return []
        league_ids = user_doc.to_dict().get("leagues", [])
        result = []
        for lid in league_ids:
            doc = self.db.collection("leagues").document(lid).get()
            if doc.exists:
                d = doc.to_dict()
                members = list(doc.reference.collection("members").get())
                result.append({
                    "leagueId": lid,
                    "name": d["name"],
                    "format": d["format"],
                    "status": d["status"],
                    "memberCount": len(members),
                    "maxMembers": d["maxMembers"],
                    "isAdmin": d["adminUid"] == uid,
                })
        return result

    def get_league(self, lid: str, uid: str) -> dict:
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")

        league = doc.to_dict()
        member_docs = list(doc.reference.collection("members").get())

        member = doc.reference.collection("members").document(uid).get()
        if not member.exists:
            raise ValueError("You are not a member of this league")

        members = []
        for m in member_docs:
            md = m.to_dict()
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
            "members": members,
            "myRole": member.to_dict().get("role", "manager"),
        }

    def update_league(self, lid: str, uid: str, updates: dict) -> dict:
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        if doc.to_dict()["adminUid"] != uid:
            raise ValueError("Only the admin can update league settings")

        allowed = {"name", "format", "tradeApproval", "pickTimer",
                   "maxMembers", "waiverDeadlineHours"}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if "format" in filtered and filtered["format"] not in VALID_FORMATS:
            raise ValueError(f"Format must be one of {VALID_FORMATS}")
        if "tradeApproval" in filtered and filtered["tradeApproval"] not in VALID_TRADE_MODES:
            raise ValueError(f"Trade approval must be one of {VALID_TRADE_MODES}")

        doc.reference.update(filtered)
        return {"status": "ok", **filtered}

    def leave_league(self, lid: str, uid: str):
        doc = self.db.collection("leagues").document(lid).get()
        if not doc.exists:
            raise ValueError("League not found")
        league = doc.to_dict()
        if league["adminUid"] == uid:
            raise ValueError("Admin cannot leave the league. Transfer admin first.")
        if league["status"] not in ("recruiting",):
            raise ValueError("Cannot leave an active league")

        doc.reference.collection("members").document(uid).delete()
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            leagues = user_doc.to_dict().get("leagues", [])
            if lid in leagues:
                leagues.remove(lid)
                user_ref.update({"leagues": leagues})

    def _code_exists(self, code: str) -> bool:
        results = (self.db.collection("leagues")
                   .where("inviteCode", "==", code)
                   .limit(1).get())
        return len(results) > 0

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
