"""Nostr key handling: NIP-19 npub/nsec codecs and key normalization.

KEY CUSTODY CONTRACT
====================
The team's Nostr PRIVATE key never touches the database. The only private-key
material this codebase ever handles is the value of the ORCHESTRATOR_NOSTR_SECKEY
environment variable, decoded in memory at signing time by
``seckey_bytes_from_env_value``. Nothing here (or anywhere) may log, store,
serialize, or echo it — including inside error messages.

Public keys are stored and compared as lowercase 64-char hex of the x-only
(BIP-340) public key — the same form Nostr events carry in their ``pubkey``
field. npub (NIP-19) is treated purely as an input/display encoding.

Schnorr operations are delegated to coincurve (libsecp256k1 bindings) —
imported lazily so importing this module (e.g. via app.models for the npub
display property) does not require the native library.
"""
from __future__ import annotations

from app.core.bech32 import bech32_decode, bech32_encode, convertbits

_HEX_CHARS = set("0123456789abcdef")


def _decode_nip19(value: str, expected_hrp: str) -> bytes | None:
    """Decode a NIP-19 bech32 string to its 32-byte payload, or None."""
    hrp, data = bech32_decode(value)
    if hrp != expected_hrp or data is None:
        return None
    payload = convertbits(data, 5, 8, pad=False)
    if payload is None or len(payload) != 32:
        return None
    return bytes(payload)


def _is_hex_key(value: str) -> bool:
    return len(value) == 64 and all(c in _HEX_CHARS for c in value.lower())


def npub_from_hex(pubkey_hex: str) -> str:
    """Encode a 64-hex x-only pubkey as a NIP-19 npub string."""
    data = convertbits(bytes.fromhex(pubkey_hex), 8, 5)
    assert data is not None  # 32 bytes always convert cleanly to 5-bit groups
    return bech32_encode("npub", data)


def note_from_hex(event_id_hex: str) -> str:
    """Encode a 64-hex event id as its NIP-19 ``note`` display form.

    Same codec as npub with a different prefix — used to hand users an
    identifier that njump-style lookup services and clients accept directly.
    """
    data = convertbits(bytes.fromhex(event_id_hex), 8, 5)
    assert data is not None  # 32 bytes always convert cleanly to 5-bit groups
    return bech32_encode("note", data)


def normalize_nostr_pubkey(value: str) -> str:
    """Validate an npub or 64-hex public key; return lowercase hex.

    Rejects private keys loudly: pasting an nsec where a public key belongs is
    the single most dangerous user mistake this feature enables, so it gets a
    dedicated error instead of a generic "invalid" one. The key must also be a
    valid x-only secp256k1 point (an off-curve x could never verify anything).
    Raises ValueError with a user-safe message otherwise.
    """
    candidate = value.strip()
    if candidate.lower().startswith("nsec1"):
        raise ValueError(
            "That looks like a PRIVATE key (nsec). Never paste it here — "
            "enter the public key (npub or hex) instead, and rotate the key "
            "if it was exposed."
        )
    if candidate.lower().startswith("npub1"):
        payload = _decode_nip19(candidate, "npub")
        if payload is None:
            raise ValueError("Invalid npub (bad bech32 checksum or length)")
        pubkey_hex = payload.hex()
    elif _is_hex_key(candidate):
        pubkey_hex = candidate.lower()
    else:
        raise ValueError("Nostr public key must be an npub or 64 hex characters")

    from coincurve import PublicKeyXOnly

    try:
        PublicKeyXOnly(bytes.fromhex(pubkey_hex))
    except Exception:
        raise ValueError("Not a valid Nostr public key (not a point on the curve)")
    return pubkey_hex


def seckey_bytes_from_env_value(value: str) -> bytes:
    """Decode the operator-supplied signing key (nsec or 64-hex) to 32 bytes.

    For the ORCHESTRATOR_NOSTR_SECKEY environment variable ONLY. The error
    messages deliberately never include any part of the input value.
    """
    candidate = value.strip()
    if candidate.lower().startswith("nsec1"):
        payload = _decode_nip19(candidate, "nsec")
        if payload is None:
            raise ValueError("ORCHESTRATOR_NOSTR_SECKEY is not a valid nsec")
    elif _is_hex_key(candidate):
        payload = bytes.fromhex(candidate.lower())
    else:
        raise ValueError(
            "ORCHESTRATOR_NOSTR_SECKEY must be an nsec or 64 hex characters"
        )

    from coincurve import PrivateKey

    try:
        PrivateKey(payload)
    except Exception:
        raise ValueError("ORCHESTRATOR_NOSTR_SECKEY is not a valid secp256k1 key")
    return payload


def pubkey_hex_from_seckey(seckey: bytes) -> str:
    """Derive the x-only (Nostr) public key hex for a 32-byte private key.

    The compressed SEC1 encoding is a parity byte followed by the 32-byte x
    coordinate; dropping the parity byte IS the BIP-340 x-only key (signing
    handles odd-Y keys internally, so signatures verify against the bare x).
    """
    from coincurve import PrivateKey

    return PrivateKey(seckey).public_key.format(compressed=True)[1:].hex()
