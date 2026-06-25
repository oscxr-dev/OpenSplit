#!/usr/bin/env bash
# =====================================================================
# test-lnbits.sh — End-to-end: crea invoice en LNBits y la paga desde lnd2
#
# Idempotente: crea una invoice nueva cada vez. Si falla el pago,
# reporta el error sin romper el entorno.
#
# Requirements: stack up, LND funded, canal lnd↔lnd2 activo.
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
set -a; source ./.env; set +a

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[test]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

LNBITS_URL="${LNBITS_URL:-http://localhost:5000}"
AMOUNT_SATS=10000
MEMO="Coffee Split test invoice (10,000 sats)"

lncli_lnd2() { docker exec lnd2 lncli --network=signet "$@"; }

# -- jq required -------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  err "jq is required. Install it: sudo apt install jq"
  exit 1
fi

# -- 1) Get super-user key ---------------------------------------
log "Leyendo super-user key de LNBits…"
SUPER_USER_ID="$(docker exec lnbits sh -c 'cat /app/data/.super_user 2>/dev/null' | tr -d '\r\n')"

if [[ -z "${SUPER_USER_ID}" ]]; then
  err "No se pudo leer /app/data/.super_user. ¿Está lnbits corriendo?"
  exit 1
fi
ok "Super-user: ${SUPER_USER_ID:0:8}…"

# -- 2) Find wallet admin key ------------------------------------
log "Buscando wallet del super-user…"
WALLETS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/wallets?usr=${SUPER_USER_ID}" || true)
ADMIN_KEY=""

if [[ -n "${WALLETS_JSON}" && "${WALLETS_JSON}" != "[]" ]]; then
  ADMIN_KEY=$(echo "${WALLETS_JSON}" | jq -r '.[0].adminkey // empty')
fi

if [[ -z "${ADMIN_KEY}" ]]; then
  log "Creando wallet 'Coffee Wallet'…"
  CREATE_JSON=$(curl -fsS -X POST \
    "${LNBITS_URL}/api/v1/account?usr=${SUPER_USER_ID}" \
    -H "Content-Type: application/json" \
    -d '{"name": "Coffee Wallet"}')
  ADMIN_KEY=$(echo "${CREATE_JSON}" | jq -r '.adminkey // empty')
fi

if [[ -z "${ADMIN_KEY}" ]]; then
  err "No se pudo obtener admin key de LNBits."
  exit 1
fi
ok "Admin key: ${ADMIN_KEY:0:8}…"

# -- 3) Balance BEFORE --------------------------------------------
BAL_BEFORE=$(curl -fsS "${LNBITS_URL}/api/v1/wallet" \
  -H "X-Api-Key: ${ADMIN_KEY}" | jq -r '.balance // 0')
log "Balance antes: ${BAL_BEFORE} msats (${BAL_BEFORE%000} sats)"

# -- 4) Create invoice --------------------------------------------
log "Creando invoice de ${AMOUNT_SATS} sats…"
INVOICE_JSON=$(curl -fsS -X POST "${LNBITS_URL}/api/v1/payments" \
  -H "X-Api-Key: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"out\": false, \"amount\": ${AMOUNT_SATS}, \"memo\": \"${MEMO}\", \"unit\": \"sat\"}")

PAYMENT_REQUEST=$(echo "$INVOICE_JSON" | jq -r '.payment_request // empty')
PAYMENT_HASH=$(echo "$INVOICE_JSON" | jq -r '.payment_hash // empty')

if [[ -z "${PAYMENT_REQUEST}" ]]; then
  err "Fallo al crear invoice. Respuesta:"
  echo "$INVOICE_JSON"
  exit 1
fi
ok "Invoice creada — hash: ${PAYMENT_HASH:0:16}…"

# -- 5) Check channel exists before paying -----------------------
log "Verificando canal lnd→lnd2…"
LND2_PUBKEY="$(lncli_lnd2 getinfo | jq -r .identity_pubkey)"
ACTIVE_CHANS=$(docker exec lnd lncli --network=signet listchannels \
  | jq --arg pk "$LND2_PUBKEY" '[.channels[] | select(.remote_pubkey == $pk and .active == true)] | length')

if [[ "$ACTIVE_CHANS" -eq 0 ]]; then
  err "No hay canal activo lnd→lnd2. Corré primero: ./scripts/open-channel.sh"
  exit 1
fi
ok "Canal activo detectado."

# -- 6) Pay invoice from lnd2 ------------------------------------
log "Pagando invoice desde lnd2…"
PAY_RESULT=$(lncli_lnd2 payinvoice --force --pay_req "$PAYMENT_REQUEST" 2>&1) || {
  err "Pago falló. Salida de lnd2:"
  echo "$PAY_RESULT"
  echo ""
  warn "La invoice fue creada. Podés pagarla manualmente."
  exit 1
}

# lncli payinvoice outputs a live-updating table, not JSON.
# We check for SUCCEEDED in the final output.
if echo "$PAY_RESULT" | grep -q "SUCCEEDED"; then
  PAY_PREIMAGE=$(echo "$PAY_RESULT" | grep -oP 'preimage: \K[0-9a-f]+' || echo "N/A")
  ok "¡Pago exitoso! Preimage: ${PAY_PREIMAGE:0:16}…"
else
  err "Pago no se completó. Salida:"
  echo "$PAY_RESULT" | tail -10
  exit 1
fi

# -- 7) Verify payment settled in LNBits --------------------------
sleep 2
PAYMENTS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/payments" \
  -H "X-Api-Key: ${ADMIN_KEY}")
SETTLED=$(echo "$PAYMENTS_JSON" | jq --arg ph "$PAYMENT_HASH" \
  '[.[] | select(.payment_hash == $ph and .pending == false)] | length')

# -- 8) Balance AFTER ---------------------------------------------
BAL_AFTER=$(curl -fsS "${LNBITS_URL}/api/v1/wallet" \
  -H "X-Api-Key: ${ADMIN_KEY}" | jq -r '.balance // 0')
log "Balance después: ${BAL_AFTER} msats (${BAL_AFTER%000} sats)"

# -- 9) Summary ---------------------------------------------------
DIFF_MSAT=$(( BAL_AFTER - BAL_BEFORE ))
DIFF_SAT=$(( DIFF_MSAT / 1000 ))

echo ""
echo -e "${GREEN}=========================================================${NC}"
if [[ "$SETTLED" -gt 0 ]]; then
  echo -e "${GREEN} Test End-to-End — COMPLETADO${NC}"
else
  echo -e "${YELLOW} Test End-to-End — PAGO ENVIADO (verificar settlement)${NC}"
fi
echo -e "${GREEN}=========================================================${NC}"
echo ""
echo "  Invoice amount : ${AMOUNT_SATS} sats"
echo "  Payment hash   : ${PAYMENT_HASH}"
echo "  Settled in API : $([ "$SETTLED" -gt 0 ] && echo '✅ YES' || echo '⚠️  NO (check LNBits UI)')"
echo "  Balance antes  : ${BAL_BEFORE} msats"
echo "  Balance después: ${BAL_AFTER} msats"
echo "  Diferencia     : +${DIFF_MSAT} msats (+${DIFF_SAT} sats)"
echo ""
echo "  BOLT11:"
echo "  $(echo "$PAYMENT_REQUEST" | head -c 80)…"
echo ""

if [[ "$SETTLED" -gt 0 ]]; then
  ok "Pago registrado como settled en LNBits."
elif [[ "$DIFF_SAT" -ge "$AMOUNT_SATS" ]]; then
  ok "Balance subió correctamente (+${DIFF_SAT} sats)."
else
  warn "Verificar settlement en LNBits UI: http://localhost:5000"
fi

echo ""
echo "  Próximo paso: configurar splitpayments en LNBits"
echo "    → http://localhost:5000/extensions/splitpayments"
echo ""
