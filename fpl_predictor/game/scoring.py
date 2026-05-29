"""
GW scoring engine.

Pulls actual FPL points from the live API for each manager's starting 11.
Applies auto-subs, stores results, updates standings.
"""

from google.cloud.firestore_v1 import SERVER_TIMESTAMP


class ScoringEngine:
    def __init__(self, db, fpl_client, squad_manager):
        self.db = db
        self.fpl = fpl_client
        self.squads = squad_manager

    def process_gw(self, lid: str, gw: int) -> dict:
        """Process scores for all managers in a league for a completed GW."""
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        live_elements = self.fpl.get_gw_live(gw)
        live_map = {}
        for el in live_elements:
            eid = el.get("id")
            stats = el.get("stats", {})
            live_map[eid] = {
                "minutes": stats.get("minutes", 0),
                "total_points": stats.get("total_points", 0),
            }

        draft_to_main = self.fpl.get_draft_to_main_map()
        draft_live = {}
        for draft_id, main_player in draft_to_main.items():
            main_id = main_player.get("id")
            if main_id and main_id in live_map:
                draft_live[draft_id] = live_map[main_id]

        members = list(league_ref.collection("members").get())
        results = {}

        for member in members:
            uid = member.id
            self.squads.process_auto_subs(lid, uid, gw, draft_live)

            lineup_doc = (league_ref.collection("lineups")
                          .document(f"{uid}_{gw}").get())
            if not lineup_doc.exists:
                lineup = self.squads._default_lineup(lid, uid)
            else:
                lineup = lineup_doc.to_dict()

            starting = lineup.get("starting", [])
            total = 0
            player_scores = []
            for pid in starting:
                pts = draft_live.get(pid, {}).get("total_points", 0)
                total += pts
                player_scores.append({"playerId": pid, "points": pts})

            results[uid] = {
                "points": total,
                "playerScores": player_scores,
                "autoSubs": lineup.get("autoSubsMade", []),
            }

        score_ref = league_ref.collection("scores").document(str(gw))
        score_ref.set({
            "results": results,
            "processed": True,
            "processedAt": SERVER_TIMESTAMP,
        })

        self._update_h2h_results(lid, gw, results)

        return {"gw": gw, "results": results}

    def get_gw_scores(self, lid: str, gw: int) -> dict:
        doc = (self.db.collection("leagues").document(lid)
               .collection("scores").document(str(gw)).get())
        if not doc.exists:
            return {"processed": False}
        return doc.to_dict()

    def get_standings(self, lid: str) -> dict:
        league_doc = self.db.collection("leagues").document(lid).get()
        if not league_doc.exists:
            raise ValueError("League not found")

        league = league_doc.to_dict()
        fmt = league.get("format", "h2h")
        members = list(
            league_doc.reference.collection("members").get()
        )
        member_map = {
            m.id: m.to_dict() for m in members
        }

        scores_docs = list(
            league_doc.reference.collection("scores").get()
        )

        if fmt == "classic":
            return self._classic_standings(member_map, scores_docs)
        else:
            return self._h2h_standings(lid, member_map, scores_docs)

    def _classic_standings(self, member_map: dict, scores_docs) -> dict:
        totals = {uid: 0 for uid in member_map}
        gw_count = 0
        for doc in scores_docs:
            data = doc.to_dict()
            if not data.get("processed"):
                continue
            gw_count += 1
            for uid, result in data.get("results", {}).items():
                totals[uid] = totals.get(uid, 0) + result.get("points", 0)

        standings = []
        for uid, total in sorted(totals.items(), key=lambda x: -x[1]):
            m = member_map.get(uid, {})
            standings.append({
                "uid": uid,
                "teamName": m.get("teamName", "?"),
                "displayName": m.get("displayName", "?"),
                "totalPoints": total,
                "gwPlayed": gw_count,
            })

        return {"format": "classic", "standings": standings}

    def _h2h_standings(self, lid: str, member_map: dict,
                       scores_docs) -> dict:
        table = {
            uid: {"w": 0, "d": 0, "l": 0, "pts": 0, "pf": 0, "pa": 0}
            for uid in member_map
        }

        schedule_docs = list(
            self.db.collection("leagues").document(lid)
            .collection("schedule").get()
        )
        for doc in schedule_docs:
            data = doc.to_dict()
            for match in data.get("matches", []):
                if not match.get("finished"):
                    continue
                h = match["home"]
                a = match["away"]
                hp = match.get("homePoints", 0)
                ap = match.get("awayPoints", 0)
                if h in table:
                    table[h]["pf"] += hp
                    table[h]["pa"] += ap
                if a in table:
                    table[a]["pf"] += ap
                    table[a]["pa"] += hp
                if hp > ap:
                    table[h]["w"] += 1
                    table[h]["pts"] += 3
                    table[a]["l"] += 1
                elif hp < ap:
                    table[a]["w"] += 1
                    table[a]["pts"] += 3
                    table[h]["l"] += 1
                else:
                    table[h]["d"] += 1
                    table[h]["pts"] += 1
                    table[a]["d"] += 1
                    table[a]["pts"] += 1

        standings = []
        for uid in sorted(
            table.keys(),
            key=lambda u: (-table[u]["pts"], -(table[u]["pf"] - table[u]["pa"]),
                           -table[u]["pf"])
        ):
            m = member_map.get(uid, {})
            standings.append({
                "uid": uid,
                "teamName": m.get("teamName", "?"),
                "displayName": m.get("displayName", "?"),
                **table[uid],
            })

        return {"format": "h2h", "standings": standings}

    def _update_h2h_results(self, lid: str, gw: int, results: dict):
        schedule_ref = (self.db.collection("leagues").document(lid)
                        .collection("schedule").document(str(gw)))
        schedule_doc = schedule_ref.get()
        if not schedule_doc.exists:
            return

        data = schedule_doc.to_dict()
        matches = data.get("matches", [])
        updated = False
        for match in matches:
            h = match["home"]
            a = match["away"]
            if h in results and a in results:
                match["homePoints"] = results[h]["points"]
                match["awayPoints"] = results[a]["points"]
                match["finished"] = True
                updated = True

        if updated:
            schedule_ref.update({"matches": matches})
