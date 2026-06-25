#!/usr/bin/env bash
# =====================================================================
# fund-lnd.sh - Mine initial blocks and fund the LND wallet on signet
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
set -a; source ./.env; set +a

GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[fund]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

bcli() {
  docker exec bitcoind bitcoin-cli \
    -signet \
    -rpcuser="${BITCOIN_RPC_USER}" \
    -rpcpassword="${BITCOIN_RPC_PASSWORD}" "$@"
}

lncli() {
  docker exec lnd lncli --network=signet "$@"
}

# -- Make sure containers are up ----------------------------------
for c in bitcoind lnd; do
  if ! docker ps --format '{{.Names}}' | grep -q "^${c}$"; then
    err "Container '$c' is not running. Run ./scripts/setup.sh first."
    exit 1
  fi
done

# -- Make sure bitcoind has a wallet loaded -----------------------
log "Ensuring a default wallet exists in bitcoind…"
if ! bcli listwallets | grep -q '"default"'; then
  bcli createwallet "default" >/dev/null 2>&1 || \
    bcli loadwallet  "default" >/dev/null 2>&1 || true
fi
ok "Wallet ready."

# -- Mine 101 blocks to a bitcoind address (matures coinbase) ----
log "Mining 101 blocks to a bitcoind address (coinbase maturity)…"
MINER_ADDR=$(bcli -rpcwallet=default getnewaddress "miner" "bech32")
bcli generatetoaddress 101 "$MINER_ADDR" >/dev/null
ok "Mined 101 blocks. Miner: $MINER_ADDR"

# -- Get an LND p2wkh address ------------------------------------
log "Generating a new p2wkh address from LND…"
LND_ADDR=$(lncli newaddress p2wkh | grep -oE '"address": *"[^"]+"' | head -n1 | cut -d'"' -f4)
if [[ -z "${LND_ADDR}" ]]; then
  err "Could not parse LND address."
  exit 1
fi
ok "LND address: $LND_ADDR"

# -- Send 10 BTC from bitcoind to LND ----------------------------
log "Sending 10 BTC from bitcoind -> LND…"
TXID=$(bcli -rpcwallet=default sendtoaddress "$LND_ADDR" 10)
ok "Broadcast TXID: $TXID"

# -- Confirm with 6 blocks ---------------------------------------
log "Mining 6 confirmation blocks…"
bcli generatetoaddress 6 "$MINER_ADDR" >/dev/null
ok "Confirmed."

# -- Show LND balance --------------------------------------------
log "LND on-chain wallet balance:"
lncli walletbalance

log "LND channel balance (should still be 0 - no channels yet):"
lncli channelbalance

cat <<EOF

$(echo -e "${GREEN}=========================================================${NC}")
 LND is funded with 10 BTC on signet.
 You can now open Lightning channels or use LNBits to issue invoices.
$(echo -e "${GREEN}=========================================================${NC}")

EOF
