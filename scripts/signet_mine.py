#!/usr/bin/env python3
"""
Signet block miner for OpenSplit custom signet.
"""

import sys, os, json, time, struct, hashlib, argparse, requests
from bitcoin.core import (
    CBlock, CTransaction, CTxIn, CTxOut,
    CScript, COutPoint, b2x, lx, x
)
from bitcoin.core.script import OP_RETURN
from bitcoin.core.key import CECKey
from bitcoin.core.serialize import VarIntSerializer

KEYS_PATH = os.path.join(os.path.dirname(__file__), "..", "signet", "signet_keys.json")


class RPC:
    def __init__(self, url="http://127.0.0.1:38332", user="admin", passwd="coffeeshop123"):
        self.url = url
        self.auth = (user, passwd)

    def call(self, method, params=None):
        data = {"jsonrpc": "1.0", "id": "m", "method": method, "params": params or []}
        r = requests.post(self.url, json=data, headers={"content-type": "application/json"}, auth=self.auth)
        r.raise_for_status()
        resp = r.json()
        if resp.get("error"):
            raise Exception(f"RPC {method}: {resp['error']}")
        return resp["result"]


def compute_merkle_root(tx_hashes):
    """Compute merkle root from list of tx hashes (32 bytes each, internal order)."""
    h = list(tx_hashes)
    while len(h) > 1:
        if len(h) % 2:
            h.append(h[-1])
        nh = []
        for i in range(0, len(h), 2):
            combined = bytes(h[i]) + bytes(h[i+1])
            nh.append(hashlib.sha256(hashlib.sha256(combined).digest()).digest())
        h = nh
    return h[0]


def mine(rpc, privkey_bytes, miner_spk_hex):
    """Mine one signet block."""
    tmpl = rpc.call("getblocktemplate", [{"rules": ["segwit", "signet"]}])
    height = tmpl["height"]
    bits_u32 = struct.unpack("<I", x(tmpl["bits"]))[0]

    # Parse regular transactions
    reg_txs = []
    for txd in tmpl.get("transactions", []):
        reg_txs.append(CTransaction.deserialize(x(txd["data"])))

    # --- Build coinbase ---
    # Output 0: segwit commitment
    out0 = CTxOut(nValue=0, scriptPubKey=CScript([OP_RETURN, bytes.fromhex(tmpl["default_witness_commitment"])]))
    # Output 1: block reward
    out1 = CTxOut(nValue=tmpl["coinbasevalue"], scriptPubKey=CScript(bytes.fromhex(miner_spk_hex)))

    # Coinbase input: prevout null, scriptSig height
    cb_txin = CTxIn(prevout=COutPoint(hash=b"\x00" * 32, n=0xffffffff),
                    scriptSig=bytes(CScript([height])))
    cb_tx = CTransaction(vin=[cb_txin], vout=[out0, out1], nVersion=1, nLockTime=0)

    # --- Build the block ---
    all_txs = [cb_tx] + reg_txs
    tx_hashes = [tx.GetHash() for tx in all_txs]
    merkle_root = compute_merkle_root(tx_hashes)

    block = CBlock(
        nVersion=tmpl["version"],
        hashPrevBlock=lx(tmpl["previousblockhash"]),
        hashMerkleRoot=merkle_root,
        nTime=tmpl["curtime"],
        nBits=bits_u32,
        nNonce=0,
        vtx=all_txs
    )

    # --- Compute sighash (block hash) and sign ---
    # Serialize header without witness
    header = struct.pack("<i", block.nVersion)
    header += bytes(block.hashPrevBlock)
    header += bytes(block.hashMerkleRoot)
    header += struct.pack("<I", block.nTime)
    header += struct.pack("<I", block.nBits)
    header += struct.pack("<I", block.nNonce)
    sighash = hashlib.sha256(hashlib.sha256(header).digest()).digest()

    key = CECKey()
    key.set_secretbytes(privkey_bytes)
    key.set_compressed(True)
    sig = key.sign(sighash)

    # --- Add signet witness to coinbase ---
    sig_data = sig + b"\x01"
    # CScriptWitness serialization: VarInt(stack_count) + for each: VarInt(len) + data
    sw_bytes = b""
    sw_bytes += VarIntSerializer.serialize(1)  # 1 stack element
    sw_bytes += VarIntSerializer.serialize(len(sig_data))
    sw_bytes += sig_data
    # Inject witness marker+flag after version, wit data before locktime
    cb_raw = cb_tx.serialize()
    cb_with_wit = cb_raw[:4] + b"\x00\x01" + cb_raw[4:-4] + sw_bytes + cb_raw[-4:]
    cb_signed = CTransaction.deserialize(cb_with_wit)

    # Rebuild block with signed coinbase
    all_txs_final = [cb_signed] + reg_txs
    # Merkle root is same (witness doesn't affect txid)
    block_final = CBlock(
        nVersion=block.nVersion,
        hashPrevBlock=block.hashPrevBlock,
        hashMerkleRoot=block.hashMerkleRoot,
        nTime=block.nTime,
        nBits=block.nBits,
        nNonce=block.nNonce,
        vtx=all_txs_final
    )

    # --- Submit ---
    block_hex = b2x(block_final.serialize())
    result = rpc.call("submitblock", [block_hex])

    if result is None:
        info = rpc.call("getblockchaininfo")
        print(f"  ✅ Block {height} — height {info['blocks']}")
        return True
    else:
        print(f"  ❌ Block {height}: {result}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", "-1", action="store_true")
    parser.add_argument("--continuous", "-c", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:38332")
    parser.add_argument("--rpc-user", default="admin")
    parser.add_argument("--rpc-pass", default="coffeeshop123")
    args = parser.parse_args()

    with open(KEYS_PATH) as f:
        keys = json.load(f)
    privkey = bytes.fromhex(keys["private_key_hex"])

    rpc = RPC(args.rpc_url, args.rpc_user, args.rpc_pass)
    info = rpc.call("getblockchaininfo")
    print(f"🌐 {info['chain']} — height {info['blocks']}")

    # Setup miner wallet
    wallets = rpc.call("listwallets")
    if "miner" not in wallets:
        rpc.call("createwallet", ["miner"])
    addr = rpc.call("getnewaddress", ["miner", "bech32m"])
    addr_info = rpc.call("validateaddress", [addr])
    miner_spk_hex = addr_info["scriptPubKey"]
    print(f"  Miner: {addr}")

    if args.check:
        tmpl = rpc.call("getblocktemplate", [{"rules": ["segwit", "signet"]}])
        print(f"  Next block: {tmpl['height']}")
        ch = tmpl.get("signet_challenge", "")
        print(f"  Challenge:   {ch[:50]}...")
        print(f"  Expected:    {keys['challenge_script_hex'][:50]}...")
        print(f"  Match: {'✅' if ch == keys['challenge_script_hex'] else '❌'}")
        return

    if args.continuous:
        print("⛏️  Continuous (Ctrl+C to stop)")
        while True:
            try:
                mine(rpc, privkey, miner_spk_hex)
                time.sleep(10)
            except KeyboardInterrupt:
                print("\n🛑 Stopped")
                break
            except Exception as e:
                import traceback; traceback.print_exc()
                time.sleep(5)
    else:
        ok = mine(rpc, privkey, miner_spk_hex)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
