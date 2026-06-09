"""PR-0 migration 5/5 — populate wc_config/tournament.adminUids.

Issue (WC2026_WINDOWS_DESIGN.md §12.4): wc_config/tournament.adminUids == [] in
prod, so every admin-gated route (api_wc.py:88) 403s off-emulator. We must
populate adminUids before any admin-triggered window / process-waivers action.

Candidate admin uids: the task spec said "role == 'owner'/'admin' in members",
but the LIVE data has no such member role (mock members carry no role;
lg_pre_draft members are role='manager'/None). The real owner/commissioner
signal in prod is the **league-level ``adminUid`` field**:
    lg_mock_draft.adminUid = 'u_mk_golden'
    lg_pre_draft.adminUid  = 'u_netanel'
So this script gathers the distinct ``adminUid`` of every league as the
candidate set (it also honours any member with role in {owner,admin,commissioner}
if one ever appears, for forward-compat).

Behaviour:
  * Reads current wc_config/tournament.adminUids.
  * Computes candidates = union of league adminUids (+ any owner/admin members).
  * New value = sorted(union(current, candidates)) — additive, never drops an
    existing admin. => idempotent (second --apply is a no-op).
  * Prints current -> proposed. --apply writes; without it, zero writes.

Example:
    .venv/bin/python scripts/migrations/04_populate_admin_uids.py
    .venv/bin/python scripts/migrations/04_populate_admin_uids.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _prod_common import add_common_args, banner, footer, get_db  # noqa: E402

OWNER_ROLES = {"owner", "admin", "commissioner"}


def main() -> int:
    parser = add_common_args(
        argparse.ArgumentParser(description="Populate tournament.adminUids.")
    )
    args = parser.parse_args()
    banner("Migration 5/5: populate wc_config/tournament.adminUids", args.apply)

    db = get_db()

    # current global value
    cfg_ref = db.collection("wc_config").document("tournament")
    cfg = cfg_ref.get().to_dict() or {}
    current = list(cfg.get("adminUids") or [])
    print(f"\nwc_config/tournament.adminUids (current) = {current}")

    # gather candidates from each league
    candidates: set[str] = set()
    print("\ncandidate admins per league:")
    for lg in db.collection("leagues").stream():
        L = lg.to_dict() or {}
        admin_uid = L.get("adminUid")
        if admin_uid:
            candidates.add(admin_uid)
            print(f"   {lg.id}: adminUid = {admin_uid!r}")
        # forward-compat: any explicit owner/admin role member
        for m in lg.reference.collection("members").stream():
            md = m.to_dict() or {}
            if (md.get("role") or "").lower() in OWNER_ROLES:
                candidates.add(m.id)
                print(f"   {lg.id}: member {m.id} role={md.get('role')!r} (owner-ish)")

    proposed = sorted(set(current) | candidates)
    print(f"\ncandidate uids gathered = {sorted(candidates)}")
    print(f"current adminUids        = {current}")
    print(f"proposed adminUids       = {proposed}")

    if proposed == sorted(set(current)):
        print("\nadminUids already contain all candidates. No change needed.")
        if args.apply:
            print("--apply: nothing to write (idempotent no-op).")
    else:
        if args.apply:
            cfg_ref.set({"adminUids": proposed}, merge=True)
            print(f"\n--apply: set wc_config/tournament.adminUids = {proposed}")
        else:
            print(
                f"\n(dry-run) WOULD set wc_config/tournament.adminUids = {proposed}"
            )

    print(
        "\nNOTE: per-league admin is already encoded in league.adminUid; this "
        "migration does not modify it (it only reads it as the source of truth)."
    )
    footer(args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
