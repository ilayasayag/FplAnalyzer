"""
Squad and lineup management.

Squad = 15 players (2GK, 5DEF, 5MID, 3FWD).
Lineup = starting 11 + bench order (4 subs).
No captaincy in FPL Draft.
Valid formations: 1GK + at least 3DEF + at least 2MID + at least 1FWD.
"""

from google.cloud.firestore_v1 import SERVER_TIMESTAMP

VALID_FORMATIONS = [
    (1, 3, 5, 2), (1, 3, 4, 3), (1, 4, 5, 1),
    (1, 4, 4, 2), (1, 4, 3, 3), (1, 5, 4, 1),
    (1, 5, 3, 2), (1, 5, 2, 3),
]

MIN_POS = {1: 1, 2: 3, 3: 2, 4: 1}  # minimum per position in starting XI


class SquadManager:
    def __init__(self, db, fpl_client):
        self.db = db
        self.fpl = fpl_client

    def get_squad(self, lid: str, uid: str) -> dict:
        doc = (self.db.collection("leagues").document(lid)
               .collection("squads").document(uid).get())
        if not doc.exists:
            return {"players": []}
        return doc.to_dict()

    def get_lineup(self, lid: str, uid: str, gw: int) -> dict:
        doc_id = f"{uid}_{gw}"
        doc = (self.db.collection("leagues").document(lid)
               .collection("lineups").document(doc_id).get())
        if not doc.exists:
            prev = self._get_previous_lineup(lid, uid, gw)
            if prev:
                return prev
            return self._default_lineup(lid, uid)
        return doc.to_dict()

    def set_lineup(self, lid: str, uid: str, gw: int,
                   starting: list, bench: list) -> dict:
        league_doc = self.db.collection("leagues").document(lid).get()
        if not league_doc.exists:
            raise ValueError("League not found")
        if league_doc.to_dict().get("status") != "active":
            raise ValueError("League is not active")

        squad_doc = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid).get())
        if not squad_doc.exists:
            raise ValueError("No squad found")

        squad_ids = {p["playerId"] for p in squad_doc.to_dict()["players"]}
        all_ids = set(starting) | set(bench)
        if all_ids != squad_ids:
            raise ValueError(
                "Lineup must contain exactly your 15 squad players"
            )
        if len(starting) != 11:
            raise ValueError("Must have exactly 11 starters")
        if len(bench) != 4:
            raise ValueError("Must have exactly 4 on the bench")
        if len(set(starting)) != 11 or len(set(bench)) != 4:
            raise ValueError("Duplicate player IDs")

        player_map = {
            p["playerId"]: p for p in squad_doc.to_dict()["players"]
        }
        formation = self._get_formation(starting, player_map)
        if formation not in VALID_FORMATIONS:
            raise ValueError(
                f"Invalid formation {formation}. "
                f"Need 1GK + at least 3DEF/2MID/1FWD."
            )

        doc_id = f"{uid}_{gw}"
        lineup_data = {
            "starting": starting,
            "bench": bench,
            "formation": list(formation),
            "locked": False,
            "autoSubsMade": [],
            "updatedAt": SERVER_TIMESTAMP,
        }
        (self.db.collection("leagues").document(lid)
         .collection("lineups").document(doc_id).set(lineup_data))

        return {
            "starting": starting,
            "bench": bench,
            "formation": list(formation),
            "locked": False,
            "autoSubsMade": [],
        }

    def process_auto_subs(self, lid: str, uid: str, gw: int,
                          live_data: dict) -> list:
        """
        After GW: replace non-playing starters with bench players.
        live_data: dict of player_id -> {minutes, total_points, ...}
        Returns list of subs made.
        """
        doc_id = f"{uid}_{gw}"
        lineup_ref = (self.db.collection("leagues").document(lid)
                      .collection("lineups").document(doc_id))
        lineup_doc = lineup_ref.get()
        if not lineup_doc.exists:
            return []

        lineup = lineup_doc.to_dict()
        starting = list(lineup["starting"])
        bench = list(lineup["bench"])

        squad_doc = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid).get())
        player_map = {
            p["playerId"]: p for p in squad_doc.to_dict()["players"]
        }

        subs_made = []
        for i, pid in enumerate(starting):
            minutes = live_data.get(pid, {}).get("minutes", 0)
            if minutes > 0:
                continue

            for j, bench_pid in enumerate(bench):
                bench_minutes = live_data.get(bench_pid, {}).get("minutes", 0)
                if bench_minutes == 0:
                    continue

                test_starting = starting.copy()
                test_starting[i] = bench_pid
                formation = self._get_formation(test_starting, player_map)
                if formation in VALID_FORMATIONS:
                    starting[i] = bench_pid
                    bench.pop(j)
                    subs_made.append({"out": pid, "in": bench_pid})
                    break

        if subs_made:
            lineup_ref.update({
                "starting": starting,
                "bench": bench,
                "autoSubsMade": subs_made,
                "locked": True,
            })

        return subs_made

    def _get_formation(self, starting_ids: list, player_map: dict) -> tuple:
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for pid in starting_ids:
            p = player_map.get(pid)
            if p:
                counts[p["position"]] = counts.get(p["position"], 0) + 1
        return (counts[1], counts[2], counts[3], counts[4])

    def _default_lineup(self, lid: str, uid: str) -> dict:
        squad_doc = (self.db.collection("leagues").document(lid)
                     .collection("squads").document(uid).get())
        if not squad_doc.exists:
            return {"starting": [], "bench": [], "formation": []}

        players = squad_doc.to_dict()["players"]
        by_pos = {1: [], 2: [], 3: [], 4: []}
        for p in players:
            by_pos[p["position"]].append(p["playerId"])

        starting = []
        bench = []
        # Default 4-4-2: 1GK + 4DEF + 4MID + 2FWD
        for pos, count in [(1, 1), (2, 4), (3, 4), (4, 2)]:
            pool = by_pos[pos]
            starting.extend(pool[:count])
            bench.extend(pool[count:])

        return {
            "starting": starting,
            "bench": bench,
            "formation": [1, 4, 4, 2],
            "locked": False,
            "autoSubsMade": [],
        }

    def _get_previous_lineup(self, lid: str, uid: str, gw: int):
        for prev_gw in range(gw - 1, 0, -1):
            doc_id = f"{uid}_{prev_gw}"
            doc = (self.db.collection("leagues").document(lid)
                   .collection("lineups").document(doc_id).get())
            if doc.exists:
                data = doc.to_dict()
                return {
                    "starting": data["starting"],
                    "bench": data["bench"],
                    "formation": data["formation"],
                    "locked": False,
                    "autoSubsMade": [],
                }
        return None
