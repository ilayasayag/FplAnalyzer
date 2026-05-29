"""
H2H match schedule generator.

Round-robin: N managers play N-1 rounds per cycle. For 38 GWs, cycle repeats.
Classic format uses a simple total-points leaderboard (no schedule needed).
"""

from google.cloud.firestore_v1 import SERVER_TIMESTAMP


class ScheduleManager:
    def __init__(self, db):
        self.db = db

    def generate_schedule(self, lid: str, start_gw: int = 1,
                          end_gw: int = 38) -> dict:
        league_ref = self.db.collection("leagues").document(lid)
        league_doc = league_ref.get()
        if not league_doc.exists:
            raise ValueError("League not found")

        league = league_doc.to_dict()
        if league.get("format") != "h2h":
            return {"status": "skipped", "reason": "Classic format has no schedule"}

        members = list(league_ref.collection("members").get())
        uids = [m.id for m in members]
        n = len(uids)
        if n < 2:
            raise ValueError("Need at least 2 members")

        if n % 2 == 1:
            uids.append("__BYE__")
            n += 1

        rounds = self._round_robin(uids)

        gw = start_gw
        round_idx = 0
        total_rounds = 0

        while gw <= end_gw:
            r = rounds[round_idx % len(rounds)]
            matches = []
            for home, away in r:
                if home == "__BYE__" or away == "__BYE__":
                    continue
                matches.append({
                    "home": home,
                    "away": away,
                    "homePoints": 0,
                    "awayPoints": 0,
                    "finished": False,
                })

            league_ref.collection("schedule").document(str(gw)).set({
                "gw": gw,
                "matches": matches,
                "createdAt": SERVER_TIMESTAMP,
            })

            gw += 1
            round_idx += 1
            total_rounds += 1

        return {"status": "ok", "gwsScheduled": total_rounds, "startGw": start_gw}

    def get_gw_schedule(self, lid: str, gw: int) -> dict:
        doc = (self.db.collection("leagues").document(lid)
               .collection("schedule").document(str(gw)).get())
        if not doc.exists:
            return {"gw": gw, "matches": []}
        return doc.to_dict()

    def _round_robin(self, teams: list) -> list:
        """
        Standard circle method for round-robin tournament.
        Returns list of rounds, each round is list of (home, away) tuples.
        """
        n = len(teams)
        fixed = teams[0]
        rotating = list(teams[1:])
        rounds = []

        for _ in range(n - 1):
            r = []
            r.append((fixed, rotating[0]))
            for j in range(1, n // 2):
                r.append((rotating[j], rotating[n - 1 - j]))
            rounds.append(r)
            rotating = rotating[1:] + rotating[:1]

        return rounds
