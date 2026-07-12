"""Deterministic SHA-256 fingerprint of a frozen split rule.

The fingerprint identifies the exact economic content of a rule version —
who gets paid what, in which configured order — independent of database
internals (row ids, tenant, timestamps, flags). Same rule → same digest,
forever. It is captured on the payment at the moment the rule is frozen
(split execution / claim time) and stored verbatim, so a later rule change
can never alter what a past payment proves.

CANONICAL SERIALIZATION CONTRACT
================================
This is a compatibility contract: once fingerprints are signed, the digest
of a given rule must be reproducible in any language, byte for byte. Do not
change any step below without versioning the contract.

1. Build this JSON document (types are JSON types):

   {
     "name": <rule name, exact string>,
     "targets": [
       {
         "identity": <payout destination: ln_address if set, else
                      lnbits_wallet_id if set, else null>,
         "label": <target label, exact string>,
         "order": <target order, integer>,
         "percentage": <percentage as a string with exactly two decimal
                        digits, e.g. "25.00" — see step 3>
       },
       ...
     ],
     "version": <rule version, integer>
   }

   Included targets: ALL targets stored on the frozen rule, including
   0%-share targets — the fingerprint covers the rule as defined, not just
   the targets that received sats for one particular payment amount.

   Excluded on purpose: database ids/UUIDs, tenant, timestamps,
   active/public flags, parent_rule_id, and nostr_pubkey (display metadata,
   not payout economics).

2. Order the "targets" array by the tuple
   (order, label, identity-or-empty-string, percentage-string), ascending.
   Sorting here (rather than trusting caller order) makes the digest
   independent of DB row order; changing a target's stored ``order`` value
   still changes the digest because ``order`` is serialized.

3. Serialize each percentage as a decimal string with exactly two fraction
   digits, rounding half-up to 0.01 — the same NUMERIC(5,2) precision the
   database stores and payouts use (see app.core.percentages). Never a JSON
   number: float formatting is not portable across languages.
   Examples: 25 → "25.00", 33.335 → "33.34", 0.1 → "0.10".

4. Encode the document as JSON with: object keys sorted lexicographically
   (byte order of their UTF-8 encoding), separators "," and ":" with no
   whitespace, and non-ASCII characters emitted as raw UTF-8 (no \\uXXXX
   escaping beyond JSON's mandatory escapes: ", \\, and control chars).
   Equivalent to Python: json.dumps(doc, sort_keys=True,
   separators=(",", ":"), ensure_ascii=False).

5. The fingerprint is the lowercase hex SHA-256 digest of the UTF-8 bytes
   of that string.

EXPOSURE
========
The fingerprint is served on the authenticated proof endpoint only. It is a
hash of rule structure (labels, LN addresses, percentages) that tenants may
consider private; although the digest itself reveals nothing, publishing it
lets anyone with a guessed rule confirm the guess. Public exposure is
deferred until that trade-off is decided explicitly.
"""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Protocol

from app.core.percentages import CENT


class _RuleLike(Protocol):
    name: str
    version: int


def _canonical_percentage(value: object) -> str:
    return str(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def canonical_rule_json(rule: _RuleLike, targets: Iterable[object]) -> str:
    """The canonical JSON string hashed by ``rule_fingerprint`` (step 1–4)."""
    entries = []
    for t in targets:
        identity = getattr(t, "ln_address", None) or getattr(t, "lnbits_wallet_id", None) or None
        entries.append(
            {
                "identity": identity,
                "label": t.label,
                "order": int(t.order),
                "percentage": _canonical_percentage(t.percentage),
            }
        )
    entries.sort(key=lambda e: (e["order"], e["label"], e["identity"] or "", e["percentage"]))
    doc = {"name": rule.name, "targets": entries, "version": int(rule.version)}
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rule_fingerprint(rule: _RuleLike, targets: Iterable[object]) -> str:
    """Hex SHA-256 fingerprint of a frozen rule. Pure: no DB, no clock."""
    return hashlib.sha256(canonical_rule_json(rule, targets).encode("utf-8")).hexdigest()
