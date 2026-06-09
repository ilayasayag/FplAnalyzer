"""PR-0 migration 4/5 — DETECT & REPORT member/schedule mismatch (report-only).

Issue (WC2026_WINDOWS_DESIGN.md §12.3): lg_mock_draft has 11 members but its H2H
schedule was built for fewer (design says "9"; live data shows the schedule has
4 matches/GW = 8 distinct participants — and league.maxMembers == 8). The late
joiners are NOT in the schedule, so PR 7 (open trade window in mock) would act on
managers with no fixtures.

This script does NOT regenerate the schedule. Schedule regeneration touches H2H
fairness, already-played GW1-2 results, and standings/knockout — too risky to
automate. It produces a precise report so a human can decide. It will PROPOSE a
safe reconciliation in dry-run output, but the only thing it is willing to do
under --apply is the conservative, lossless option (see below); the destructive
option (rebuild schedule) is never performed by this script.

Proposed reconciliation options (printed, human chooses):
  A) Treat extra members as spectators/non-playing for the already-started
     group phase (leave schedule as-is). Lossless. No write needed.
  B) Rebuild the H2H schedule for all 11 members from the next unplayed GW
     forward, preserving finished GWs. NOT done here — needs design sign-off and
     a dedicated scheduler.

--apply here only records a marker on the league doc
(``scheduleMismatchAck``) noting the mismatch was reviewed; it makes NO change
to members, schedule, scores, or standings. Without --apply, zero writes.

Example:
    .venv/bin/python scripts/migrations/03_report_member_schedule_mismatch.py
    .venv/bin/python scripts/migrations/03_report_member_schedule_mismatch.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _prod_common import add_common_args, banner, footer, get_db  # noqa: E402

LEAGUES = ["lg_mock_draft"]


def main() -> int:
    parser = add_common_args(
        argparse.ArgumentParser(
            description="Report lg_mock_draft member/schedule mismatch."
        )
    )
    args = parser.parse_args()
    banner("Migration 4/5: member/schedule mismatch REPORT", args.apply)

    db = get_db()
    for lid in LEAGUES:
        ref = db.collection("leagues").document(lid)
        L = ref.get().to_dict() or {}
        members = list(ref.collection("members").stream())
        member_uids = {m.id for m in members}
        member_names = {m.id: (m.to_dict() or {}).get("displayName") for m in members}

        sched_docs = list(ref.collection("schedule").stream())
        sched_uids: set[str] = set()
        matches_per_gw = {}
        for s in sched_docs:
            sd = s.to_dict() or {}
            ms = sd.get("matches") or []
            matches_per_gw[s.id] = len(ms)
            for mt in ms:
                for side in ("home", "away"):
                    if mt.get(side):
                        sched_uids.add(mt[side])

        print(f"\nleague {lid}")
        print(f"  name           = {L.get('name')!r}")
        print(f"  status         = {L.get('status')!r}")
        print(f"  maxMembers     = {L.get('maxMembers')}")
        print(f"  members        = {len(members)}")
        print(f"  schedule docs  = {len(sched_docs)} (matches/GW: {matches_per_gw})")
        print(f"  distinct uids in schedule = {len(sched_uids)}")

        print("\n  MEMBERS:")
        for uid in sorted(member_uids):
            in_sched = "IN schedule" if uid in sched_uids else "*** NOT in schedule ***"
            print(f"     - {uid} ({member_names.get(uid)!r}): {in_sched}")

        missing = sorted(member_uids - sched_uids)  # members never scheduled
        extra = sorted(sched_uids - member_uids)  # scheduled but not a member

        print(f"\n  members MISSING from schedule ({len(missing)}):")
        for uid in missing:
            print(f"     - {uid} ({member_names.get(uid)!r})")
        print(f"\n  schedule participants that are NOT members ({len(extra)}):")
        for uid in extra:
            print(f"     - {uid}")

        print("\n  ASSESSMENT:")
        if not missing and not extra:
            print("     schedule and membership are consistent. Nothing to do.")
        else:
            print(
                f"     {len(missing)} member(s) have NO H2H fixtures. The schedule "
                f"was built for {len(sched_uids)} managers (maxMembers="
                f"{L.get('maxMembers')}), but the league has {len(members)} members."
            )
            print("     PROPOSED OPTIONS (human decides; not auto-applied):")
            print(
                "       A) Keep schedule as-is; treat the "
                f"{len(missing)} extra member(s) as non-playing spectators for the "
                "in-progress group phase. Lossless, zero writes."
            )
            print(
                "       B) Rebuild the H2H schedule for all "
                f"{len(members)} members from the next unplayed GW forward, "
                "preserving finished GWs. Requires a dedicated scheduler + design "
                "sign-off; NOT performed by this script."
            )

        if args.apply:
            ref.update(
                {
                    "scheduleMismatchAck": {
                        "members": len(members),
                        "scheduled": len(sched_uids),
                        "missingFromSchedule": missing,
                        "reviewed": True,
                    }
                }
            )
            print(
                "\n  --apply: wrote 'scheduleMismatchAck' marker on league doc "
                "(no member/schedule/score data changed)."
            )
        else:
            print(
                "\n  (dry-run) --apply would ONLY record a 'scheduleMismatchAck' "
                "marker; it will NOT rebuild the schedule."
            )

    footer(args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
