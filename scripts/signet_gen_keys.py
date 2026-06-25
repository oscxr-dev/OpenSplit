#!/usr/bin/env python3
"""Generate signet signing keys for OpenSplit custom signet."""
import os
import json
import hashlib
from bitcoin.core.key import CECKey
from bitcoin.core.script import CScript, OP_CHECKSIG
from bitcoin.wallet import CBitcoinSecret, P2PKHBitcoinAddress

SIGNET_DIR = os.path.join(os.path.dirname(__file__), "..", "signet")

def generate():
    os.makedirs(SIGNET_DIR, exist_ok=True)

    priv = CECKey()
    priv.set_secretbytes(os.urandom(32))
    priv_bytes = priv.get_privkey()
    priv.set_compressed(True)
    pub_compressed = priv.get_pubkey().hex()

    # Compressed pubkey is 33 bytes (starts with 02 or 03)
    assert len(bytes.fromhex(pub_compressed)) == 33, f"Expected 33 bytes, got {len(bytes.fromhex(pub_compressed))}"
    assert pub_compressed.startswith("02") or pub_compressed.startswith("03")

    # Signet challenge: <pubkey> OP_CHECKSIG
    challenge_script = CScript([bytes.fromhex(pub_compressed), OP_CHECKSIG])
    challenge_hex = challenge_script.hex()

    wif = str(CBitcoinSecret.from_secret_bytes(priv_bytes, compressed=True))

    # Save
    keys = {
        "private_key_hex": priv_bytes.hex(),
        "public_key_hex": pub_compressed,
        "challenge_script_hex": challenge_hex,
        "wif": wif,
    }
    with open(os.path.join(SIGNET_DIR, "signet_keys.json"), "w") as f:
        json.dump(keys, f, indent=2)

    print(f"✅ Signet keys generated")
    print(f"   Challenge: {challenge_hex}")
    print(f"   WIF:       {wif}")
    print(f"   Saved to:  {SIGNET_DIR}/signet_keys.json")

if __name__ == "__main__":
    generate()
