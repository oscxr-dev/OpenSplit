#!/usr/bin/env bash
# =====================================================================
# test-split.sh — End-to-end: pago → split automático → verifica balances
# Idempotente: crea una invoice nueva cada vez.
# =====================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[test]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

LNBITS_URL="${LNBITS_URL:-http://localhost:5000}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
set -a; source ./.env; set +a

AMOUNT_SATS=50000
lncli_lnd2() { docker exec lnd2 lncli --network=signet "$@"; }
db_query() { docker exec postgres psql -U lnbits -d lnbits -t -A -c "$1" 2>/dev/null | tr -d '[:space:]'; }

# -- 1) Source wallet --------------------------------------------------
SUPER_USER_ID=$(docker exec lnbits sh -c 'cat /app/data/.super_user 2>/dev/null' | tr -d '\r\n')
WALLETS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/wallets?usr=${SUPER_USER_ID}")
SOURCE_ID=$(echo "$WALLETS_JSON" | jq -r '.[0].id')
SOURCE_ADMIN=$(echo "$WALLETS_JSON" | jq -r '.[0].adminkey')
SOURCE_NAME=$(echo "$WALLETS_JSON" | jq -r '.[0].name')

# -- 2) Get targets from API -------------------------------------------
TARGETS_JSON=$(curl -fsS "${LNBITS_URL}/splitpayments/api/v1/targets" \
  -H "X-Api-Key: ${SOURCE_ADMIN}" 2>/dev/null || echo "[]")

if [[ "$TARGETS_JSON" == "[]" || -z "$TARGETS_JSON" ]]; then
  err "No hay targets de splitpayments configurados."
  exit 1
fi

# -- 3) Balance lookup helper ------------------------------------------
get_bal() {
  local wid="$1"
  local wkey
  wkey=$(db_query "SELECT adminkey FROM lnbits.wallets WHERE id='${wid}' LIMIT 1;")
  curl -fsS "${LNBITS_URL}/api/v1/wallet" -H "X-Api-Key: ${wkey}" | jq -r '.balance // 0'
}

# -- 4) Balances BEFORE ------------------------------------------------
log "Balances antes del split…"
SRC_BEFORE=$(get_bal "$SOURCE_ID")
echo "$TARGETS_JSON" | jq -r '.[] | "\(.alias)|\(.wallet)"' > /tmp/targets.txt

declare -A BAL_BEFORE
while IFS='|' read -r alias wid; do
  BAL_BEFORE["$alias"]=$(get_bal "$wid")
  log "  ${alias}: ${BAL_BEFORE[$alias]} msats"
done < /tmp/targets.txt

log "  ${SOURCE_NAME}: ${SRC_BEFORE} msats"

# -- 5) Create and pay invoice -----------------------------------------
log "Creando invoice de ${AMOUNT_SATS} sats…"
INVOICE_JSON=$(curl -fsS -X POST "${LNBITS_URL}/api/v1/payments" \
  -H "X-Api-Key: ${SOURCE_ADMIN}" \
  -H "Content-Type: application/json" \
  -d "{\"out\": false, \"amount\": ${AMOUNT_SATS}, \"memo\": \"Split test - café\", \"unit\": \"sat\"}")

BOLT11=$(echo "$INVOICE_JSON" | jq -r '.payment_request // empty')
PAY_HASH=$(echo "$INVOICE_JSON" | jq -r '.payment_hash // empty')
[[ -z "$BOLT11" ]] && { err "Fallo al crear invoice"; exit 1; }
ok "Invoice creada: ${AMOUNT_SATS} sats (hash: ${PAY_HASH:0:10}…)"

log "Pagando desde lnd2…"
PAY_OUT=$(lncli_lnd2 payinvoice --force --pay_req "$BOLT11" 2>&1)
if echo "$PAY_OUT" | grep -q "SUCCEEDED"; then
  PREIMAGE=$(echo "$PAY_OUT" | grep -oP 'preimage: \K[0-9a-f]+' || echo "N/A")
  ok "Pago exitoso (preimage: ${PREIMAGE:0:10}…)"
else
  err "Pago falló"
  exit 1
fi

# -- 6) Wait for split to process --------------------------------------
log "Esperando procesamiento del split…"
sleep 4

# -- 7) Balances AFTER -------------------------------------------------
log "Balances después del split…"
SRC_AFTER=$(get_bal "$SOURCE_ID")

echo ""
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN} Test Split — ${AMOUNT_SATS} sats${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo ""
printf "  %-15s %12s %12s %12s\n" "Wallet" "Antes" "Después" "Δ"
printf "  %-15s %12s %12s %12s\n" "──────────────" "──────────" "──────────" "──────────"

DIFF_SRC=$(( SRC_AFTER - SRC_BEFORE ))
printf "  %-15s %12s %12s %+12s\n" "${SOURCE_NAME}" "${SRC_BEFORE}" "${SRC_AFTER}" "${DIFF_SRC}"

while IFS='|' read -r alias wid; do
  AFTER=$(get_bal "$wid")
  BEFORE="${BAL_BEFORE[$alias]:-0}"
  DIFF=$(( AFTER - BEFORE ))
  printf "  %-15s %12s %12s %+12s\n" "${alias}" "${BEFORE}" "${AFTER}" "${DIFF}"
done < /tmp/targets.txt

echo ""
ok "Split completado."
echo "  Próximo paso: conectar POS (Tiaaki vía LNDHub)"
echo ""
