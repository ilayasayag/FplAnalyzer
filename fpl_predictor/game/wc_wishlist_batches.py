"""
Batched wishlist view — lossless transform between the FLAT ordered bid list
and the BATCH view (sprint: wishlist bid run, part 2).

The flat list (``leagues/{lid}/wishlist_bids/{uid}_{gw}.bids``) stays the ONLY
stored source of truth; the auction, history, rollback and the auto-run
pipeline never see batches. A batch groups one intent — "these players OUT
(in leave-order), these free agents IN (in priority order), same position" —
so a manager replacing several knocked-out players doesn't hand-maintain the
cartesian product of swaps.

Canonical expansion is **OUT-major**: for each OUT in order, every IN in
order. This matches how managers already hand-build the product by hand (all
INs against the first OUT, then all INs against the second), so batching an
existing list and expanding it back returns the identical flat list.

Losslessness is by construction, not by luck: :func:`batch_bids` walks the
flat list left-to-right and only groups a run into a batch when the run IS
exactly that batch's OUT-major expansion. Anything else (hand-interleaved
orders, duplicates, truncated products) falls out as smaller batches or
singletons, so ``unbatch(batch_bids(flat)) == flat`` holds for EVERY input —
the round-trip invariant the tests hammer.

The one normalization: two ADJACENT batches whose grouping forms a larger
perfect product (e.g. ``[o1]×[i1,i2]`` directly followed by ``[o2]×[i1,i2]``)
re-derive as the merged ``[o1,o2]×[i1,i2]``. The expansion — and therefore
the auction — is bit-identical; only the visual grouping normalizes. (User
decision: derived-only view, no stored grouping.)

Pure functions, no Firestore I/O — the API layer feeds them dicts.
"""

from typing import Dict, List

# Keep any batch editor from exploding a manager's list: 4 OUTs × 10 INs is
# already 40 bids. Enforced on the EXPANDED size at save time (both the
# batched and the flat endpoints), never against historical stored data.
MAX_EXPANDED_BIDS = 60


def unbatch(batches: List[Dict]) -> List[Dict]:
    """Expand batches to the canonical flat bid list (OUT-major).

    Each batch: ``{position: str, outs: [pid], ins: [pid]}`` (both sides
    ordered, position is the display string carried on bids e.g. ``"DEF"``).
    Returns ``[{playerIn, playerOut, position}, ...]``.
    """
    flat: List[Dict] = []
    for b in batches or []:
        pos = b.get("position", "")
        for out in b.get("outs", []):
            for inn in b.get("ins", []):
                flat.append({"playerIn": int(inn), "playerOut": int(out),
                             "position": pos})
    return flat


def batch_bids(flat: List[Dict]) -> List[Dict]:
    """Greedy lossless grouping of a flat bid list into batches.

    Walks left-to-right. At each point it first collects the run of
    consecutive bids sharing one playerOut (same position, no repeated
    playerIn) — that fixes the batch's IN sequence. It then keeps absorbing
    the following ``len(ins)`` bids whenever they replay the SAME IN sequence
    against one new playerOut. A batch therefore always expands back to
    exactly the bids it consumed, which is what makes the round-trip
    identity hold for arbitrary input.
    """
    flat = flat or []
    batches: List[Dict] = []
    i, n = 0, len(flat)
    while i < n:
        pos = flat[i].get("position", "")
        out1 = int(flat[i]["playerOut"])
        ins: List[int] = []
        j = i
        while (j < n
               and flat[j].get("position", "") == pos
               and int(flat[j]["playerOut"]) == out1
               and int(flat[j]["playerIn"]) not in ins):
            ins.append(int(flat[j]["playerIn"]))
            j += 1

        outs = [out1]
        m = len(ins)
        while j + m <= n:
            nxt = flat[j:j + m]
            out_next = int(nxt[0]["playerOut"])
            if out_next in outs:
                break
            if any(b.get("position", "") != pos
                   or int(b["playerOut"]) != out_next
                   or int(b["playerIn"]) != ins[k]
                   for k, b in enumerate(nxt)):
                break
            outs.append(out_next)
            j += m

        batches.append({"position": pos, "outs": outs, "ins": ins})
        i = j
    return batches


def validate_batches(batches) -> List[Dict]:
    """Schema-validate a client-submitted batches payload; return it with all
    ids coerced to int. Raises ``ValueError`` with a stable code prefix.

    Checks structure only (the per-bid ownership / free-agent / same-position
    checks happen in ``submit_bids`` on the expanded list, exactly as for a
    flat save): every batch needs a position string, non-empty ``outs`` and
    ``ins`` (an empty side means the batch should have been deleted
    client-side), no repeats within a side, and the expansion must not
    contain the same exact (in, out) pair twice — mirroring the flat editor's
    only duplicate rule.
    """
    if not isinstance(batches, list):
        raise ValueError("BATCHES_MALFORMED: batches must be a list")
    cleaned: List[Dict] = []
    for idx, b in enumerate(batches):
        if not isinstance(b, dict):
            raise ValueError(f"BATCHES_MALFORMED: batch #{idx} must be an object")
        pos = b.get("position")
        if not isinstance(pos, str) or not pos:
            raise ValueError(f"BATCHES_MALFORMED: batch #{idx} needs a position")
        try:
            outs = [int(x) for x in (b.get("outs") or [])]
            ins = [int(x) for x in (b.get("ins") or [])]
        except (TypeError, ValueError):
            raise ValueError(f"BATCHES_MALFORMED: batch #{idx} ids must be integers")
        if not outs or not ins:
            raise ValueError(
                f"BATCH_SIDE_EMPTY: batch #{idx} has an empty side — a batch "
                f"needs at least one player out and one player in")
        if len(set(outs)) != len(outs):
            raise ValueError(f"BATCH_DUP_OUT: batch #{idx} repeats a player out")
        if len(set(ins)) != len(ins):
            raise ValueError(f"BATCH_DUP_IN: batch #{idx} repeats a player in")
        cleaned.append({"position": pos, "outs": outs, "ins": ins})

    seen_pairs = set()
    for bid in unbatch(cleaned):
        pair = (bid["playerIn"], bid["playerOut"])
        if pair in seen_pairs:
            raise ValueError(
                f"DUPLICATE_SWAP: the swap in {bid['playerIn']} / out "
                f"{bid['playerOut']} appears twice across your batches")
        seen_pairs.add(pair)
    return cleaned


def enforce_cap(flat: List[Dict]):
    """Reject an expanded list larger than :data:`MAX_EXPANDED_BIDS`."""
    if len(flat) > MAX_EXPANDED_BIDS:
        raise ValueError(
            f"TOO_MANY_BIDS: this expands to {len(flat)} bids — the maximum "
            f"is {MAX_EXPANDED_BIDS} per gameweek. Trim a batch (fewer "
            f"players in, or fewer players out).")
