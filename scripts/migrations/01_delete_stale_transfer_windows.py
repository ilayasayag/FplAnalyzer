"""PR-0 migration 1/5 — delete stale ``transfer_windows`` docs in lg_mock_draft.

Issue (WC2026_WINDOWS_DESIGN.md §12.1): ``lg_mock_draft`` carries 5 stale
``transfer_windows`` docs that are ALL ``status:"open"`` with ``gw:None`` and no
timestamps — the legacy "never-closes" bug, ×5. The new design treats
``transfer_windows`` as audit-only (closed records); these stale open docs are
noise and must be deleted.

Safety: deletes ONLY docs that look stale (status=="open" AND gw is None AND no
openedAt/closedAt). A healthy audit doc (real gw / timestamps / closed status)
is left alone, so this is safe to re-run (idempotent) and won't nuke future
legitimate windows.

DRY-RUN by default. Use --apply to delete.

Example:
    .venv/bin/python scripts/migrations/01_delete_stale_transfer_windows.py
    .venv/bin/python scripts/migrations/01_delete_stale_transfer_windows.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _prod_common import add_common_args, banner, footer, get_db  # noqa: E402

LEAGUES = ["lg_mock_draft"]


def is_stale(d: dict) -> bool:
    return (
        d.get("status") == "open"
        and d.get("gw") is None
        and not d.get("openedAt")
        and not d.get("closedAt")
    )


def main() -> int:
    parser = add_common_args(
        argparse.ArgumentParser(description="Delete stale transfer_windows docs.")
    )
    args = parser.parse_args()
    banner("Migration 1/5: delete stale transfer_windows", args.apply)

    db = get_db()
    total_deletable = 0
    for lid in LEAGUES:
        col = db.collection("leagues").document(lid).collection("transfer_windows")
        docs = list(col.stream())
        stale = [d for d in docs if is_stale(d.to_dict() or {})]
        kept = [d for d in docs if not is_stale(d.to_dict() or {})]
        print(f"\nleague {lid}: {len(docs)} transfer_windows docs total")
        for d in kept:
            dd = d.to_dict() or {}
            print(
                f"   KEEP   {d.id}: status={dd.get('status')!r} gw={dd.get('gw')} "
                f"(not stale)"
            )
        for d in stale:
            dd = d.to_dict() or {}
            print(
                f"   DELETE {d.id}: status={dd.get('status')!r} gw={dd.get('gw')} "
                f"openedAt={dd.get('openedAt')} closedAt={dd.get('closedAt')}"
            )
        total_deletable += len(stale)

        if args.apply:
            for d in stale:
                d.reference.delete()
            if stale:
                print(f"   -> deleted {len(stale)} stale docs in {lid}")

    print(f"\nstale docs targeted: {total_deletable}")
    if not args.apply and total_deletable:
        print(f"WOULD delete {total_deletable} stale transfer_windows docs.")
    footer(args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
