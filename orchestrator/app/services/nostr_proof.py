"""Nostr-signed Split Proof: canonical bundle + NIP-01 event signing.

The third proof pillar. A payout preimage proves settlement happened
(migration 016), the rule fingerprint proves what terms were agreed
(migration 017, services/proof_hash.py) — this module proves WHO says so:
the team signs a compact bundle of both with their Nostr key, producing a
standard Nostr event that anyone can verify with off-the-shelf Nostr tooling,
no trust in this server or its database required.

CANONICAL PROOF BUNDLE CONTRACT (opensplit-split-proof/v1)
==========================================================
Like services/proof_hash.py, this is a compatibility contract: once events
are signed, the bundle for a given payment must be reproducible byte for
byte in any language. Do not change any step without bumping the ``spec``
version string.

1. Build this JSON document (types are JSON types):

   {
     "amount_sats": <payment amount in sats, integer>,
     "payment_id": <payment UUID as lowercase hyphenated string>,
     "rule_fingerprint": <64-hex rule fingerprint (proof_hash.py) or null>,
     "spec": "opensplit-split-proof/v1",
     "splits": [
       {
         "amount_sats": <split amount in sats, integer>,
         "ln_payment_hash": <hex payment hash or null>,
         "ln_preimage": <hex settlement preimage or null>,
         "member": <target label if set, else its Lightning address, else null>
       },
       ...
     ],
     "timestamp": <unix seconds the payment settled (paid_at), integer>
   }

   Nulls are honest, not errors: payments settled before the preimage /
   fingerprint columns existed (or payouts that produced none) sign with
   explicit nulls. The signature then attests exactly what the team can
   claim — authorship and amounts — and visibly not more. Rejecting such
   payments would permanently exclude all pre-pillar history from signing.

   ``member`` prefers the label over the Lightning address: labels are the
   identity the team already shows publicly, while payout addresses are
   private-ish routing detail — and a signed event is made to travel.

2. Order the "splits" array by the tuple
   (member-or-empty-string, ln_payment_hash-or-empty-string, amount_sats),
   ascending — the digest must not depend on database row order.

3. Encode exactly like the fingerprint contract (proof_hash.py step 4):
   keys sorted lexicographically, separators "," and ":" with no whitespace,
   non-ASCII as raw UTF-8. Python: json.dumps(doc, sort_keys=True,
   separators=(",", ":"), ensure_ascii=False).

NOSTR EVENT
===========
The bundle string is the ``content`` of a NIP-01 event:

  kind        2718  (regular-event range 1000–9999: relays store it and can
                    never replace it — a proof must be immutable, which rules
                    out addressable/replaceable kinds; 2718 is unassigned in
                    the NIPs registry as of 2026-07)
  created_at  the bundle's ``timestamp`` (pinned to paid_at, NOT signing
              time, so the same payment always yields the same event id —
              re-signing is naturally idempotent and relays would dedupe)
  tags        [["t", "opensplit-proof"]]
  pubkey      the team's x-only key, hex

id/signature follow NIP-01/BIP-340 exactly: the id is the SHA-256 of
``[0, pubkey, created_at, kind, tags, content]`` serialized with the same
compact-JSON rules as above, and ``sig`` is the schnorr signature of the id
bytes. Any Nostr library verifies it; nothing here is OpenSplit-specific.

Signing uses coincurve (libsecp256k1 bindings) — never hand-rolled. The
private key arrives as bytes from the environment (see core/nostr_keys.py
for the custody contract) and never leaves this process.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Iterable, Protocol

OPENSPLIT_PROOF_KIND = 2718
PROOF_SPEC = "opensplit-split-proof/v1"
PROOF_TAGS: list[list[str]] = [["t", "opensplit-proof"]]


class _SplitLike(Protocol):
    label: str | None
    ln_address: str | None
    amount_sats: int
    ln_payment_hash: str | None
    ln_preimage: str | None


def _canonical_json(doc: object) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_proof_bundle(
    *,
    payment_id: uuid.UUID,
    amount_sats: int,
    rule_fingerprint: str | None,
    splits: Iterable[_SplitLike],
    timestamp: int,
) -> str:
    """The canonical bundle JSON string (contract steps 1–3). Pure."""
    entries = []
    for s in splits:
        member = getattr(s, "label", None) or getattr(s, "ln_address", None) or None
        entries.append(
            {
                "amount_sats": int(s.amount_sats),
                "ln_payment_hash": s.ln_payment_hash,
                "ln_preimage": s.ln_preimage,
                "member": member,
            }
        )
    entries.sort(
        key=lambda e: (e["member"] or "", e["ln_payment_hash"] or "", e["amount_sats"])
    )
    doc = {
        "amount_sats": int(amount_sats),
        "payment_id": str(payment_id),
        "rule_fingerprint": rule_fingerprint,
        "spec": PROOF_SPEC,
        "splits": entries,
        "timestamp": int(timestamp),
    }
    return _canonical_json(doc)


def nostr_event_id(event: dict) -> str:
    """NIP-01 event id: SHA-256 hex of the canonical serialization."""
    payload = [
        0,
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    ]
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def sign_proof_event(seckey: bytes, bundle_json: str, created_at: int) -> dict:
    """Build and schnorr-sign the kind-2718 event carrying ``bundle_json``."""
    from coincurve import PrivateKey

    from app.core.nostr_keys import pubkey_hex_from_seckey

    event = {
        "pubkey": pubkey_hex_from_seckey(seckey),
        "created_at": int(created_at),
        "kind": OPENSPLIT_PROOF_KIND,
        "tags": [list(tag) for tag in PROOF_TAGS],
        "content": bundle_json,
    }
    event["id"] = nostr_event_id(event)
    event["sig"] = PrivateKey(seckey).sign_schnorr(bytes.fromhex(event["id"])).hex()
    return event


def verify_proof_event(event: dict) -> bool:
    """Standard Nostr verification: id recomputes AND sig verifies.

    Used as the sanity check after signing (before anything is persisted)
    — but it is exactly what any external Nostr library does, so it also
    documents how third parties verify a copied event.
    """
    from coincurve import PublicKeyXOnly

    try:
        if nostr_event_id(event) != event["id"]:
            return False
        return bool(
            PublicKeyXOnly(bytes.fromhex(event["pubkey"])).verify(
                bytes.fromhex(event["sig"]), bytes.fromhex(event["id"])
            )
        )
    except Exception:
        return False
