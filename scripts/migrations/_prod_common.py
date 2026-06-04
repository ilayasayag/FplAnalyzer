"""Shared helpers for WC 2026 PR-0 prod data-cleanup migrations.

Connects to the LIVE prod Firestore (project ``fpl-analyzer-792eb``, named
database ``gamedb``) using the active gcloud SA access token. The ADC file is a
person login lacking ``datastore.user`` (it 403s), so we mint a token via
``gcloud auth print-access-token`` instead.

All migration scripts import :func:`get_db` from here and share the
:func:`add_common_args` / :func:`banner` helpers so behaviour is uniform:
DRY-RUN by default, ``--apply`` required to write, zero writes without it.
"""
from __future__ import annotations

import argparse
import subprocess

PROJECT = "fpl-analyzer-792eb"
DATABASE = "gamedb"


def get_db():
    """Return a firestore.Client bound to prod gamedb via the gcloud SA token."""
    from google.cloud import firestore
    from google.oauth2.credentials import Credentials

    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"]
    ).decode().strip()
    return firestore.Client(
        project=PROJECT, database=DATABASE, credentials=Credentials(token=token)
    )


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this flag the script is DRY-RUN "
        "(prints planned changes, makes ZERO writes).",
    )
    return parser


def banner(title: str, apply: bool) -> None:
    mode = "APPLY (WRITES ENABLED)" if apply else "DRY-RUN (no writes)"
    print("=" * 72)
    print(f"  {title}")
    print(f"  target: project={PROJECT} database={DATABASE}")
    print(f"  mode:   {mode}")
    print("=" * 72)


def footer(apply: bool) -> None:
    print("-" * 72)
    if apply:
        print("APPLY complete. Re-run to confirm idempotency (should be a no-op).")
    else:
        print("DRY-RUN complete. No writes were made. Re-run with --apply to write.")
