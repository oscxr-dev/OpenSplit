#!/bin/bash
# =====================================================================
# open-channel.sh — Abre canal Lightning bidireccional lnd ↔ lnd2
#
# Idempotente: si el canal ya existe y está activo, solo reporta.
# =====================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[chan]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
lncli_lnd()  { docker exec lnd  lncli --network=signet "$@"; }
lncli_lnd2() { docker exec lnd2 lncli --network=signet "$@"; }
btc_cli()    { docker exec bitcoind bitcoin-cli -signet -rpcuser=admin -rpcpassword=coffeeshop123 "$@"; }

# -------------------------------------------------------------------
# 1. Check existing channels
# -------------------------------------------------------------------
log "Checking existing channels from lnd → lnd2…"

LND2_PUBKEY="$(lncli_lnd2 getinfo | jq -r .identity_pubkey)"
EXISTING=$(lncli_lnd listchannels | jq --arg pk "$LND2_PUBKEY" \
  '[.channels[] | select(.remote_pubkey == $pk and .active == true)]')

ACTIVE_COUNT=$(echo "$EXISTING" | jq 'length')

if [[ "$ACTIVE_COUNT" -gt 0 ]]; then
  ok "Ya hay $ACTIVE_COUNT canal(es) activo(s) entre lnd y lnd2:"
  echo "$EXISTING" | jq -r '.[] | "  chan_id=\(.chan_id)  capacity=\(.capacity)  local=\(.local_balance)  remote=\(.remote_balance)"'
  echo ""
  log "Idempotente: no se abre nuevo canal. Para forzar, cerrá los existentes primero."
  exit 0
fi

log "No se detectaron canales activos. Procediendo a abrir uno nuevo…"

# -------------------------------------------------------------------
# 2. Fund lnd2 on-chain (si no tiene balance)
# -------------------------------------------------------------------
ONCHAIN_BAL=$(lncli_lnd2 walletbalance | jq -r '.confirmed_balance // "0"')
MIN_FUND=500000  # 0.005 BTC mínimo para fees de apertura

if [[ "$ONCHAIN_BAL" -lt "$MIN_FUND" ]]; then
  log "lnd2 tiene ${ONCHAIN_BAL} sats on-chain. Enviando fondos…"
  ADDR=$(lncli_lnd2 newaddress p2wkh | jq -r .address)
  TXID=$(btc_cli sendtoaddress "$ADDR" 5)
  log "Enviados 5 BTC → $ADDR (txid: ${TXID:0:16}…)"
  btc_cli generatetoaddress 6 "$(btc_cli getnewaddress)" > /dev/null
  ok "6 bloques minados. Balance lnd2 confirmado."
else
  ok "lnd2 ya tiene ${ONCHAIN_BAL} sats on-chain."
fi

# -------------------------------------------------------------------
# 3. Connect peers
# -------------------------------------------------------------------
log "Conectando lnd → lnd2…"
lncli_lnd connect "${LND2_PUBKEY}@lnd2:9735" 2>/dev/null && ok "Peers conectados." || warn "Ya estaban conectados (o falló connect, continuando)."

# -------------------------------------------------------------------
# 4. Open channel: 1M local, 500k push al peer (bidireccional)
# -------------------------------------------------------------------
log "Abriendo canal: 1,000,000 sats local + 500,000 sats push → lnd2…"
FUNDING_TX=$(lncli_lnd openchannel --node_key "$LND2_PUBKEY" \
  --local_amt 1000000 --push_amt 500000 --sat_per_vbyte 1 \
  | jq -r '.funding_txid // .txid')

ok "Funding tx: ${FUNDING_TX:0:16}…"

# -------------------------------------------------------------------
# 5. Mine blocks to confirm
# -------------------------------------------------------------------
btc_cli generatetoaddress 6 "$(btc_cli getnewaddress)" > /dev/null
ok "6 bloques minados. Esperando confirmación del canal…"

# -------------------------------------------------------------------
# 6. Verify
# -------------------------------------------------------------------
sleep 2
FINAL=$(lncli_lnd listchannels | jq --arg pk "$LND2_PUBKEY" \
  '[.channels[] | select(.remote_pubkey == $pk and .active == true)]')

if [[ "$(echo "$FINAL" | jq 'length')" -gt 0 ]]; then
  ok "¡Canal abierto y activo!"
  echo "$FINAL" | jq -r '.[] | "  chan_id=\(.chan_id)  capacity=\(.capacity)  local=\(.local_balance)  remote=\(.remote_balance)"'
else
  err "El canal no aparece como activo. Revisá:"
  err "  docker exec lnd lncli --network=signet pendingchannels"
  exit 1
fi

# -------------------------------------------------------------------
# 7. Summary
# -------------------------------------------------------------------
echo ""
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN} Canal Lightning lnd ↔ lnd2 — ACTIVO${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo ""
echo "  lnd2 pubkey : ${LND2_PUBKEY}"
echo "  lnd balance : $(lncli_lnd channelbalance | jq -r .balance) sats"
echo "  lnd2 balance: $(lncli_lnd2 channelbalance | jq -r .balance) sats"
echo ""
echo "  Listar canales:"
echo "    docker exec lnd lncli --network=signet listchannels"
echo ""
