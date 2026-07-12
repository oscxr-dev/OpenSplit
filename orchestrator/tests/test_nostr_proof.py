"""Nostr proof signing — pure logic, no DB.

The verification half of these tests is deliberately INDEPENDENT of the
production code: NIP-01 event ids are recomputed from the spec inline, and
schnorr signatures are checked with a pure-Python BIP-340 verifier (ported
from the BIP-340 reference implementation) instead of coincurve. Production
signs with libsecp256k1; the tests verify with unrelated math. If the two
implementations agree, the event verifies for any third-party Nostr tooling.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.core.nostr_keys import (
    normalize_nostr_pubkey,
    npub_from_hex,
    pubkey_hex_from_seckey,
    seckey_bytes_from_env_value,
)
from app.schemas import TenantUpdate
from app.services.nostr_proof import (
    OPENSPLIT_PROOF_KIND,
    canonical_proof_bundle,
    nostr_event_id,
    sign_proof_event,
    verify_proof_event,
)

# ── Independent BIP-340 verifier (BIP-340 reference implementation port) ──
# https://github.com/bitcoin/bips/blob/master/bip-0340/reference.py
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _tagged_hash(tag: str, msg: bytes) -> bytes:
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()


def _lift_x(x: int):
    if x >= P:
        return None
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq:
        return None
    return (x, y if y % 2 == 0 else P - y)


def _point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    if p1[0] == p2[0] and p1[1] != p2[1]:
        return None
    if p1 == p2:
        lam = (3 * p1[0] * p1[0] * pow(2 * p1[1], P - 2, P)) % P
    else:
        lam = ((p2[1] - p1[1]) * pow(p2[0] - p1[0], P - 2, P)) % P
    x3 = (lam * lam - p1[0] - p2[0]) % P
    return (x3, (lam * (p1[0] - x3) - p1[1]) % P)


def _point_mul(point, k: int):
    result = None
    for i in range(256):
        if (k >> i) & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
    return result


def schnorr_verify(msg32: bytes, pubkey32: bytes, sig64: bytes) -> bool:
    """BIP-340 Verify(pk, m, sig), straight from the reference pseudocode."""
    pub = _lift_x(int.from_bytes(pubkey32, "big"))
    r = int.from_bytes(sig64[:32], "big")
    s = int.from_bytes(sig64[32:], "big")
    if pub is None or r >= P or s >= N:
        return False
    e = (
        int.from_bytes(
            _tagged_hash("BIP0340/challenge", sig64[:32] + pubkey32 + msg32), "big"
        )
        % N
    )
    rp = _point_add(_point_mul(G, s), _point_mul(pub, N - e))
    return rp is not None and rp[1] % 2 == 0 and rp[0] == r


def independent_event_id(event: dict) -> str:
    """NIP-01 id recomputed from the spec, without touching app code."""
    serialized = json.dumps(
        [0, event["pubkey"], event["created_at"], event["kind"], event["tags"], event["content"]],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ── Fixed test identities ──────────────────────────────────────────────────
# Deterministic but obviously-test key material (never a real key).
SECKEY = hashlib.sha256(b"opensplit-nostr-proof-test-key").digest()
PUBKEY_HEX = pubkey_hex_from_seckey(SECKEY)

# NIP-19 official test vectors.
NIP19_PUB_HEX = "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d"
NIP19_NPUB = "npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6"
NIP19_NSEC = "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe5"
NIP19_SEC_HEX = "67dea2ed018072d675f5415ecfaed7d2597555e202d85b3d65ea4e58d2d92ffa"


@dataclass
class Row:
    label: str | None
    ln_address: str | None
    amount_sats: int
    ln_payment_hash: str | None
    ln_preimage: str | None


PAYMENT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
FINGERPRINT = "bc0c49b1591b2d47dbaf19324e09fdf78517114e314b4346ed39cb5397b322aa"
ROWS = [
    Row("Carol", "carol@ln.test", 14001, "aa" * 32, "bb" * 32),
    Row("Dave", "dave@ln.test", 7000, None, None),
]


def _bundle(rows=None, fingerprint=FINGERPRINT) -> str:
    return canonical_proof_bundle(
        payment_id=PAYMENT_ID,
        amount_sats=21001,
        rule_fingerprint=fingerprint,
        splits=rows if rows is not None else ROWS,
        timestamp=1780000000,
    )


# ── NIP-19 codecs and key normalization ────────────────────────────────────
def test_npub_encoding_matches_nip19_vector():
    assert npub_from_hex(NIP19_PUB_HEX) == NIP19_NPUB


def test_normalize_accepts_npub_and_hex_equivalently():
    assert normalize_nostr_pubkey(NIP19_NPUB) == NIP19_PUB_HEX
    assert normalize_nostr_pubkey(NIP19_PUB_HEX) == NIP19_PUB_HEX
    assert normalize_nostr_pubkey(f"  {NIP19_PUB_HEX.upper()}  ") == NIP19_PUB_HEX


def test_normalize_rejects_nsec_loudly():
    with pytest.raises(ValueError, match="PRIVATE"):
        normalize_nostr_pubkey(NIP19_NSEC)


def test_normalize_rejects_garbage():
    for bad in ["", "npub1qqqqq", "abc123", "zz" * 32, "npub" + "1" * 60]:
        with pytest.raises(ValueError):
            normalize_nostr_pubkey(bad)


def test_normalize_rejects_off_curve_x():
    # Find a deterministic x that is not on the curve (about half of all x are).
    x = 1
    while _lift_x(x) is not None:
        x += 1
    off_curve = x.to_bytes(32, "big").hex()
    with pytest.raises(ValueError, match="curve"):
        normalize_nostr_pubkey(off_curve)


def test_seckey_env_accepts_nsec_and_hex():
    assert seckey_bytes_from_env_value(NIP19_NSEC).hex() == NIP19_SEC_HEX
    assert seckey_bytes_from_env_value(NIP19_SEC_HEX) == bytes.fromhex(NIP19_SEC_HEX)
    with pytest.raises(ValueError):
        seckey_bytes_from_env_value("not-a-key")
    with pytest.raises(ValueError):
        seckey_bytes_from_env_value("00" * 32)  # zero is not a valid secret


def test_seckey_error_messages_never_echo_the_value():
    secret_ish = "deadbeef" * 8
    try:
        seckey_bytes_from_env_value(secret_ish[:-1])  # 63 chars -> invalid
    except ValueError as exc:
        assert "deadbeef" not in str(exc)


def test_tenant_update_schema_normalizes_and_rejects_nsec():
    assert TenantUpdate(nostr_pubkey=NIP19_NPUB).nostr_pubkey == NIP19_PUB_HEX
    assert TenantUpdate(nostr_pubkey="   ").nostr_pubkey is None
    assert "nostr_pubkey" not in TenantUpdate().model_fields_set
    with pytest.raises(ValidationError, match="PRIVATE"):
        TenantUpdate(nostr_pubkey=NIP19_NSEC)


# ── Canonical bundle ───────────────────────────────────────────────────────
def test_bundle_golden_vector_documents_the_contract():
    """Byte-exact expected output — any change to this string is a breaking
    change to the opensplit-split-proof/v1 contract and needs a version bump."""
    expected = (
        '{"amount_sats":21001,'
        '"payment_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",'
        f'"rule_fingerprint":"{FINGERPRINT}",'
        '"spec":"opensplit-split-proof/v1",'
        '"splits":['
        '{"amount_sats":14001,"ln_payment_hash":"' + "aa" * 32 + '",'
        '"ln_preimage":"' + "bb" * 32 + '","member":"Carol"},'
        '{"amount_sats":7000,"ln_payment_hash":null,"ln_preimage":null,"member":"Dave"}'
        "],"
        '"timestamp":1780000000}'
    )
    assert _bundle() == expected


def test_bundle_is_deterministic_and_row_order_independent():
    assert _bundle() == _bundle()
    assert _bundle(rows=list(reversed(ROWS))) == _bundle()


def test_bundle_includes_missing_proof_fields_as_honest_nulls():
    bundle = json.loads(_bundle(fingerprint=None))
    assert bundle["rule_fingerprint"] is None
    dave = [s for s in bundle["splits"] if s["member"] == "Dave"][0]
    assert dave["ln_payment_hash"] is None
    assert dave["ln_preimage"] is None


def test_bundle_member_prefers_label_then_address_then_null():
    rows = [
        Row("Carol", "carol@ln.test", 1, None, None),
        Row(None, "dave@ln.test", 2, None, None),
        Row(None, None, 3, None, None),
    ]
    members = [s["member"] for s in json.loads(_bundle(rows=rows))["splits"]]
    assert members == [None, "Carol", "dave@ln.test"]  # sorted: "" < "Carol" < "dave"


# ── Sign → independently verify ────────────────────────────────────────────
def test_signed_event_verifies_with_independent_implementations():
    event = sign_proof_event(SECKEY, _bundle(), 1780000000)

    assert event["kind"] == OPENSPLIT_PROOF_KIND
    assert event["created_at"] == 1780000000
    assert event["content"] == _bundle()
    assert event["pubkey"] == PUBKEY_HEX
    assert event["tags"] == [["t", "opensplit-proof"]]

    # Independent NIP-01 id (spec reimplementation, not app code).
    assert independent_event_id(event) == event["id"]
    # Independent BIP-340 verify (pure Python, not coincurve).
    assert schnorr_verify(
        bytes.fromhex(event["id"]),
        bytes.fromhex(event["pubkey"]),
        bytes.fromhex(event["sig"]),
    )
    # And the production-side verifier agrees.
    assert verify_proof_event(event)


def test_event_id_is_deterministic_for_the_same_payment():
    a = sign_proof_event(SECKEY, _bundle(), 1780000000)
    b = sign_proof_event(SECKEY, _bundle(), 1780000000)
    assert a["id"] == b["id"]  # sig may differ (fresh aux randomness); id must not


def test_any_bundle_or_event_mutation_invalidates_the_proof():
    event = sign_proof_event(SECKEY, _bundle(), 1780000000)

    mutations: list[dict] = [
        {**event, "content": event["content"].replace("21001", "21002")},
        {**event, "created_at": event["created_at"] + 1},
        {**event, "kind": 1},
        {**event, "tags": [["t", "opensplit-proof"], ["extra", "tag"]]},
        {**event, "pubkey": NIP19_PUB_HEX},
    ]
    for mutated in mutations:
        # The id no longer matches the mutated fields...
        assert independent_event_id(mutated) != mutated["id"]
        # ...and standard verification fails.
        assert not verify_proof_event(mutated)

    # Recomputing the id over mutated content does not help: the signature
    # then fails against the honest key.
    tampered = {**event, "content": event["content"].replace("Carol", "Mallory")}
    tampered["id"] = independent_event_id(tampered)
    assert not schnorr_verify(
        bytes.fromhex(tampered["id"]),
        bytes.fromhex(tampered["pubkey"]),
        bytes.fromhex(tampered["sig"]),
    )
    assert not verify_proof_event(tampered)

    # A corrupted signature byte fails too.
    bad_sig = bytearray(bytes.fromhex(event["sig"]))
    bad_sig[7] ^= 0x01
    assert not schnorr_verify(
        bytes.fromhex(event["id"]), bytes.fromhex(event["pubkey"]), bytes(bad_sig)
    )


def test_verify_rejects_event_signed_by_a_different_key():
    other_seckey = hashlib.sha256(b"some-other-key").digest()
    event = sign_proof_event(other_seckey, _bundle(), 1780000000)
    forged = {**event, "pubkey": PUBKEY_HEX}
    forged["id"] = independent_event_id(forged)
    # Signature was made by the other key, so it must not verify against ours.
    assert not schnorr_verify(
        bytes.fromhex(forged["id"]), bytes.fromhex(forged["pubkey"]), bytes.fromhex(forged["sig"])
    )
    assert not verify_proof_event(forged)


def test_nostr_event_id_matches_spec_reimplementation_on_unicode_content():
    # ensure_ascii=False + UTF-8: non-ASCII content must hash identically in
    # both implementations (NIP-01 requires raw UTF-8, not \\uXXXX escapes).
    event = {
        "pubkey": PUBKEY_HEX,
        "created_at": 1780000000,
        "kind": OPENSPLIT_PROOF_KIND,
        "tags": [["t", "opensplit-proof"]],
        "content": '{"member":"Café ☕ — niño"}',
    }
    assert nostr_event_id(event) == independent_event_id(event)
