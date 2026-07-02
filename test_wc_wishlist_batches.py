#!/usr/bin/env python3
"""Tier-1 unit tests for the batched wishlist transform (sprint: wishlist bid
run, part 2) — ``wc_wishlist_batches``: the lossless flat ⇄ batch mapping the
batched editor is built on.

Run:
    .venv/bin/python -m pytest test_wc_wishlist_batches.py -v

The contract under test (user-specified):
  * ``unbatch(batch(L)) == L`` for EVERY flat list L — batch it, unbatch it,
    return to the same exact order;
  * batch → edit (reorder ins/outs, reprioritize batches, delete) → unbatch
    reflects the edits in the expected flat order;
  * expansion is OUT-major (all INs against the first OUT, then the next);
  * validation: empty batch sides, in-side/out-side repeats, duplicate
    (in, out) pairs across the expansion, and the expanded-size cap.

The centerpiece fixture is Ilay's REAL 16-bid GW5 wishlist (shape copied
from prod on 2026-07-02) — the exact messy list this feature was designed
around: it must batch into 5 groups and round-trip byte-identically.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fpl_predictor.game.wc_wishlist_batches import (  # noqa: E402
    MAX_EXPANDED_BIDS, batch_bids, enforce_cap, unbatch, validate_batches,
)

# Symbolic player ids mirroring Ilay's real GW5 list. OUT side: Tah (DEF),
# Havertz + Gakpo (FWD), Vargas (MID), Verbruggen (GK).
TAH, HAV, GAK, VAR, VER = 1, 2, 3, 4, 5
DIOP, MAZ, THEO = 101, 102, 103            # DEF ins
SUA, DAV, QUI, NDI, JIM = 201, 202, 203, 204, 205  # FWD ins
AND = 301                                   # MID in
FRE, NYL = 401, 402                         # GK ins


def _b(pin, pout, pos):
    return {"playerIn": pin, "playerOut": pout, "position": pos}


ILAY_GW5 = [
    _b(DIOP, TAH, "DEF"), _b(MAZ, TAH, "DEF"), _b(THEO, TAH, "DEF"),
    _b(SUA, HAV, "FWD"), _b(DAV, HAV, "FWD"), _b(QUI, HAV, "FWD"), _b(NDI, HAV, "FWD"),
    _b(SUA, GAK, "FWD"), _b(DAV, GAK, "FWD"), _b(QUI, GAK, "FWD"), _b(NDI, GAK, "FWD"),
    _b(AND, VAR, "MID"),
    _b(JIM, HAV, "FWD"), _b(JIM, GAK, "FWD"),
    _b(FRE, VER, "GK"), _b(NYL, VER, "GK"),
]


# ---------------------------------------------------------------------------
# 1. The real-world fixture: exact grouping + byte-identical round-trip
# ---------------------------------------------------------------------------

def test_ilay_real_list_batches_into_five_groups():
    batches = batch_bids(ILAY_GW5)
    assert batches == [
        {"position": "DEF", "outs": [TAH], "ins": [DIOP, MAZ, THEO]},
        {"position": "FWD", "outs": [HAV, GAK], "ins": [SUA, DAV, QUI, NDI]},
        {"position": "MID", "outs": [VAR], "ins": [AND]},
        {"position": "FWD", "outs": [HAV, GAK], "ins": [JIM]},
        {"position": "GK", "outs": [VER], "ins": [FRE, NYL]},
    ]


def test_ilay_real_list_roundtrips_identically():
    assert unbatch(batch_bids(ILAY_GW5)) == ILAY_GW5


# ---------------------------------------------------------------------------
# 2. Round-trip identity holds for ANY flat list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flat", [
    [],                                                     # empty
    [_b(SUA, HAV, "FWD")],                                  # single bid
    # IN-major shaped product (i1×o1, i1×o2, i2×o1, i2×o2) — groups as two
    # small 2-out batches, still lossless.
    [_b(SUA, HAV, "FWD"), _b(SUA, GAK, "FWD"),
     _b(DAV, HAV, "FWD"), _b(DAV, GAK, "FWD")],
    # Truncated product: second out only replays part of the IN sequence.
    [_b(SUA, HAV, "FWD"), _b(DAV, HAV, "FWD"), _b(SUA, GAK, "FWD")],
    # Exact duplicate pair back-to-back (legacy data tolerated on read).
    [_b(SUA, HAV, "FWD"), _b(SUA, HAV, "FWD")],
    # Positions interleaved bid-by-bid — all singletons.
    [_b(DIOP, TAH, "DEF"), _b(SUA, HAV, "FWD"),
     _b(MAZ, TAH, "DEF"), _b(DAV, HAV, "FWD")],
    # Same OUT sequence, different IN order per out — NOT a product.
    [_b(SUA, HAV, "FWD"), _b(DAV, HAV, "FWD"),
     _b(DAV, GAK, "FWD"), _b(SUA, GAK, "FWD")],
])
def test_roundtrip_identity(flat):
    assert unbatch(batch_bids(flat)) == flat


def test_expansion_is_out_major():
    flat = unbatch([{"position": "FWD", "outs": [HAV, GAK], "ins": [SUA, DAV]}])
    assert flat == [
        _b(SUA, HAV, "FWD"), _b(DAV, HAV, "FWD"),
        _b(SUA, GAK, "FWD"), _b(DAV, GAK, "FWD"),
    ]


def test_adjacent_equivalent_batches_normalize_merged():
    # [o1]×[i1,i2] directly followed by [o2]×[i1,i2] IS the OUT-major product
    # [o1,o2]×[i1,i2]: identical expansion, so re-deriving merges the display
    # grouping. Documented normalization (derived-only view, user decision).
    two = [
        {"position": "FWD", "outs": [HAV], "ins": [SUA, DAV]},
        {"position": "FWD", "outs": [GAK], "ins": [SUA, DAV]},
    ]
    merged = batch_bids(unbatch(two))
    assert merged == [{"position": "FWD", "outs": [HAV, GAK], "ins": [SUA, DAV]}]
    assert unbatch(merged) == unbatch(two)


# ---------------------------------------------------------------------------
# 3. Edit scenarios: batch → change → unbatch reflects the change
# ---------------------------------------------------------------------------

def test_reorder_ins_changes_expansion():
    batches = batch_bids(ILAY_GW5)
    # Move Ndiaye to the top of the big FWD batch's IN priority.
    fwd = batches[1]
    fwd["ins"] = [NDI, SUA, DAV, QUI]
    flat = unbatch(batches)
    assert flat[3] == _b(NDI, HAV, "FWD")     # first FWD bid is now Ndiaye↔Havertz
    assert flat[7] == _b(NDI, GAK, "FWD")     # and he leads the Gakpo replay too
    assert len(flat) == len(ILAY_GW5)


def test_delete_an_out_shrinks_the_batch():
    batches = batch_bids(ILAY_GW5)
    batches[1]["outs"] = [GAK]                # drop Havertz from the big FWD batch
    flat = unbatch(batches)
    assert len(flat) == len(ILAY_GW5) - 4     # Havertz×4 ins gone from that batch
    assert _b(SUA, HAV, "FWD") not in flat
    assert _b(JIM, HAV, "FWD") in flat        # batch #4 still covers Havertz


def test_reprioritize_batches_moves_whole_segments():
    batches = batch_bids(ILAY_GW5)
    batches.insert(0, batches.pop(2))         # Anderson↔Vargas becomes priority #1
    flat = unbatch(batches)
    assert flat[0] == _b(AND, VAR, "MID")
    assert flat[1:4] == ILAY_GW5[0:3]         # Tah batch follows intact


def test_delete_last_in_kills_batch_client_contract():
    # The client deletes a batch when a side empties; the server backs that up
    # by rejecting an empty side outright.
    with pytest.raises(ValueError, match="BATCH_SIDE_EMPTY"):
        validate_batches([{"position": "GK", "outs": [VER], "ins": []}])
    with pytest.raises(ValueError, match="BATCH_SIDE_EMPTY"):
        validate_batches([{"position": "GK", "outs": [], "ins": [FRE]}])


# ---------------------------------------------------------------------------
# 4. Validation + cap
# ---------------------------------------------------------------------------

def test_validate_rejects_malformed_payloads():
    with pytest.raises(ValueError, match="BATCHES_MALFORMED"):
        validate_batches({"not": "a list"})
    with pytest.raises(ValueError, match="BATCHES_MALFORMED"):
        validate_batches(["nope"])
    with pytest.raises(ValueError, match="BATCHES_MALFORMED"):
        validate_batches([{"outs": [1], "ins": [2]}])          # no position
    with pytest.raises(ValueError, match="BATCHES_MALFORMED"):
        validate_batches([{"position": "GK", "outs": ["x"], "ins": [2]}])
    with pytest.raises(ValueError, match="BATCH_DUP_OUT"):
        validate_batches([{"position": "FWD", "outs": [HAV, HAV], "ins": [SUA]}])
    with pytest.raises(ValueError, match="BATCH_DUP_IN"):
        validate_batches([{"position": "FWD", "outs": [HAV], "ins": [SUA, SUA]}])


def test_validate_rejects_duplicate_pair_across_batches():
    with pytest.raises(ValueError, match="DUPLICATE_SWAP"):
        validate_batches([
            {"position": "FWD", "outs": [HAV, GAK], "ins": [SUA]},
            {"position": "FWD", "outs": [HAV], "ins": [SUA]},   # (SUA, HAV) again
        ])


def test_validate_allows_shared_out_and_in_across_batches():
    # Ilay's real pattern: Havertz/Gakpo reused as OUTs in a later fallback
    # batch with a DIFFERENT in — allowed (the auction's skip rules handle it).
    cleaned = validate_batches([
        {"position": "FWD", "outs": [HAV, GAK], "ins": [SUA, DAV]},
        {"position": "FWD", "outs": [HAV, GAK], "ins": [JIM]},
    ])
    assert len(unbatch(cleaned)) == 6


def test_cap_enforced_on_expanded_size():
    ins = list(range(1000, 1000 + 21))
    over = unbatch([{"position": "FWD", "outs": [HAV, GAK, VAR], "ins": ins}])
    assert len(over) == 63
    with pytest.raises(ValueError, match="TOO_MANY_BIDS"):
        enforce_cap(over)
    enforce_cap(over[:MAX_EXPANDED_BIDS])      # exactly at the cap is fine
