"""PR-0 migration 2&3/5 — renumber member waiverPriority / draftPosition to 1..N.

Issue (WC2026_WINDOWS_DESIGN.md §12.2):
  * §12.2 waiverPriority is NOT a unique total order. lg_mock_draft has dupes
    (1,2,1,6,7,4,2,3,8,5,5); u_netanel + u_roy share waiverPriority=5.
  * draftPosition has the same problem: u_netanel + u_roy share draftPos=3 in
    mock; lg_pre_draft has THREE managers at draftPos=7.

Fix: renumber the chosen field to a clean unique 1..N sequence in BOTH leagues,
**preserving existing relative order** where possible. Deterministic tie-break:
  sort key = (current_value_of_field, draftPosition, uid)
so equal field values fall back to draftPosition, then uid — fully reproducible.

This handles BOTH integrity issues #2 (waiverPriority) and #3 (draftPosition).
By default it processes both fields; pass --field to run one independently.

Idempotent: if a field is already a clean 1..N permutation in member order, the
computed assignment equals the current values and nothing is written.

DRY-RUN by default. Use --apply to write.

Examples:
    .venv/bin/python scripts/migrations/02_renumber_member_ordinals.py
    .venv/bin/python scripts/migrations/02_renumber_member_ordinals.py --field waiverPriority
    .venv/bin/python scripts/migrations/02_renumber_member_ordinals.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _prod_common import add_common_args, banner, footer, get_db  # noqa: E402

LEAGUES = ["lg_mock_draft", "lg_pre_draft"]
FIELDS = ["waiverPriority", "draftPosition"]


def _num(v):
    """Coerce a field value to a sortable number; None sorts last."""
    if isinstance(v, (int, float)):
        return v
    return float("inf")


def plan_for_field(members: list, field: str) -> list:
    """Return ordered list of (uid, old, new) assigning a unique 1..N.

    Sort key preserves relative order by the field's current value, then breaks
    ties deterministically by draftPosition then uid.
    """
    rows = []
    for m in members:
        md = m.to_dict() or {}
        rows.append(
            {
                "uid": m.id,
                "ref": m.reference,
                "cur": md.get(field),
                "draftPos": md.get("draftPosition"),
            }
        )
    rows.sort(
        key=lambda r: (_num(r["cur"]), _num(r["draftPos"]), str(r["uid"]))
    )
    out = []
    for i, r in enumerate(rows, start=1):
        out.append((r["uid"], r["ref"], r["cur"], i))
    return out


def main() -> int:
    parser = add_common_args(
        argparse.ArgumentParser(
            description="Renumber waiverPriority/draftPosition to unique 1..N."
        )
    )
    parser.add_argument(
        "--field",
        choices=FIELDS,
        action="append",
        help="Field(s) to renumber. Repeatable. Default: both.",
    )
    args = parser.parse_args()
    fields = args.field or FIELDS
    banner(
        f"Migration 2&3/5: renumber member ordinals {fields}", args.apply
    )

    db = get_db()
    writes = 0
    for lid in LEAGUES:
        members = list(
            db.collection("leagues").document(lid).collection("members").stream()
        )
        print(f"\nleague {lid}: {len(members)} members")
        for field in fields:
            plan = plan_for_field(members, field)
            cur_vals = [old for (_u, _r, old, _n) in plan]
            new_vals = [new for (_u, _r, _o, new) in plan]
            already_clean = cur_vals == new_vals
            print(f"  field {field}:  (already 1..N in order? {already_clean})")
            for uid, ref, old, new in plan:
                tag = "  " if old == new else "->"
                print(f"     {tag} {uid}: {old} -> {new}")
                if old != new and args.apply:
                    ref.update({field: new})
                    writes += 1
            if not args.apply and not already_clean:
                changed = sum(1 for (_u, _r, o, n) in plan if o != n)
                print(f"     WOULD update {changed} members for {field}.")

    print(f"\ntotal writes performed: {writes}")
    footer(args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
